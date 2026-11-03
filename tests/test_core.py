import random
import threading
import time
import unittest
from types import SimpleNamespace

from arcmouse.engine import Cancelled, Engine
from arcmouse.model import SettingsError, bezier, safe_interval, validate_settings


class Guard:
    def __init__(self):
        self.alive = True
        self.point = (100, 100)
        self.covered = False
        self.origin = (0, 0)
        self.scale = 1.5
        self.checks = 0

    def check(self):
        self.checks += 1
        if not self.alive:
            raise OSError("target lost")

    def cursor(self):
        return self.point

    def geometry(self):
        self.check()
        return *self.origin, 1200, 800, self.scale

    def resolve(self, x, y, mode):
        self.check()
        px,py = (x*self.scale,y*self.scale) if mode == "dip" else (x*1199,y*799)
        if not (0 <= px < 1200 and 0 <= py < 800):
            raise OSError("outside")
        return self.origin[0]+round(px),self.origin[1]+round(py)

    def check_point(self, point):
        self.check()
        if self.covered:
            raise OSError("covered")


class Backend:
    def __init__(self, guard):
        self.guard = guard
        self.clicks, self.moves, self.times = [], [], []

    def move(self,x,y):
        self.moves.append((x,y))
        self.guard.point = (x,y)

    def click(self,button):
        self.clicks.append(button)
        self.times.append(time.monotonic())


def make_engine(settings=None, **kw):
    guard = Guard()
    backend = Backend(guard)
    engine = Engine({"count":3,"interval_ms":5,**(settings or {})},guard,backend,
                    threading.Event(),SimpleNamespace(value=0),lambda _:None,**kw)
    return engine,guard,backend


class SettingsTests(unittest.TestCase):
    def test_defaults_are_plain_clicks(self):
        settings=validate_settings({})
        self.assertEqual(settings["count"],0)
        self.assertFalse(settings["fixed_position"])
        self.assertFalse(settings["dry_run"])
        self.assertEqual(settings["interval_ms"],100)

    def test_bad_settings_rejected(self):
        for settings in ({"interval_ms":float("nan")},{"count":-1},{"count":1.5},
                         {"button":"invalid"},{"dry_run":"false"},{"count":True},
                         {"nodes":[]},{"fixed_position":True,"coordinates":"ratio","x":2},
                         {"backend":"hardware","device":""}):
            with self.subTest(settings=settings),self.assertRaises(SettingsError):
                validate_settings(settings)

    def test_numeric_strings_and_safe_floor(self):
        result=validate_settings({"interval_ms":"0","count":"12"})
        self.assertEqual(result["interval_ms"],5)
        self.assertEqual(result["count"],12)

    def test_randomization_never_undercuts_floor(self):
        rng=random.Random(42)
        values=[safe_interval(0,100,rng) for _ in range(10000)]
        self.assertGreaterEqual(min(values),5)
        self.assertLessEqual(max(values),300)

    def test_curve_endpoint_and_easing(self):
        path=list(bezier((0,0),(100,50),100))
        self.assertEqual(path[-1],(100,50))
        self.assertLess(path[0][0],path[50][0]-path[49][0])


class EngineTests(unittest.TestCase):
    def test_exact_repeat_count(self):
        engine,_,backend=make_engine({"count":7,"button":"right"})
        engine.run()
        self.assertEqual(backend.clicks,["right"]*7)
        self.assertEqual(engine.clicks,7)

    def test_default_position_does_not_move_mouse(self):
        engine,_,backend=make_engine()
        engine.run()
        self.assertEqual(backend.moves,[])

    def test_dry_run_never_emits_input(self):
        engine,_,backend=make_engine({"dry_run":True,"fixed_position":True,"x":100,"y":100,"duration_ms":5})
        engine.run()
        self.assertEqual(engine.clicks,3)
        self.assertEqual((backend.clicks,backend.moves),([],[]))

    def test_continuous_repeat_stops_on_cancel(self):
        engine,_,backend=make_engine({"count":0})
        original=backend.click
        def click(button):
            original(button)
            if len(backend.clicks)==4: engine.cancel.set()
        backend.click=click
        with self.assertRaises(Cancelled): engine.run()
        self.assertEqual(len(backend.clicks),4)

    def test_click_floor(self):
        engine,_,backend=make_engine({"interval_ms":0,"count":5})
        start=time.monotonic()
        engine.run()
        gaps=[b-a for a,b in zip([start]+backend.times,backend.times)]
        self.assertTrue(all(g>=0.0045 for g in gaps))

    def test_cancel_long_wait(self):
        engine,_,_=make_engine()
        timer=threading.Timer(0.025,engine.cancel.set)
        timer.start()
        start=time.monotonic()
        with self.assertRaises(Cancelled): engine.wait(100000)
        timer.join()
        self.assertLess(time.monotonic()-start,0.3)

    def test_target_loss_before_click(self):
        engine,guard,backend=make_engine()
        guard.alive=False
        with self.assertRaises(OSError): engine.run()
        self.assertEqual(backend.clicks,[])

    def test_occlusion_before_click(self):
        engine,guard,backend=make_engine()
        guard.covered=True
        with self.assertRaises(OSError): engine.run()
        self.assertEqual(backend.clicks,[])

    def test_human_input_delays_click(self):
        engine,_,backend=make_engine()
        engine.pause_until.value=time.monotonic()+0.06
        start=time.monotonic()
        engine.click(interval_ms=0)
        self.assertGreaterEqual(backend.times[0]-start,0.055)

    def test_cancel_while_human_paused(self):
        engine,_,_=make_engine()
        engine.pause_until.value=time.monotonic()+20
        engine.cancel.set()
        with self.assertRaises(Cancelled): engine.checkpoint()

    def test_fixed_position_dpi(self):
        engine,guard,backend=make_engine({"count":1,"fixed_position":True,"x":100,"y":100,"duration_ms":5})
        guard.origin=(-800,100)
        engine.run()
        self.assertEqual(backend.moves[-1],(-650,250))

    def test_window_moves_during_interval(self):
        engine,guard,backend=make_engine({"count":1,"interval_ms":40,"fixed_position":True,"x":100,"y":100,"duration_ms":5})
        timer=threading.Timer(0.01,lambda:setattr(guard,"origin",(250,300)))
        timer.start()
        engine.run()
        timer.join()
        self.assertEqual(backend.moves[-1],(400,450))

    def test_ratio_coordinates(self):
        engine,_,backend=make_engine({"coordinates":"ratio"})
        engine.move(0.5,0.5,duration_ms=5)
        self.assertEqual(backend.moves[-1],(600,400))

    def test_out_of_bounds_does_not_move(self):
        engine,_,backend=make_engine()
        with self.assertRaises(OSError): engine.move(20000,0,5)
        self.assertEqual(backend.moves,[])

    def test_session_deadline(self):
        engine,_,backend=make_engine({"count":0},max_seconds=0)
        with self.assertRaises(SettingsError): engine.run()
        self.assertEqual(backend.clicks,[])


if __name__=="__main__": unittest.main()
