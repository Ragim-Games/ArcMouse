import copy
import json
from pathlib import Path
import random
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace

from arcmouse.engine import Cancelled, Engine
from arcmouse.model import WorkflowError, bezier, demo, expression, load, safe_interval, validate


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


def make_engine(flow=None, **kw):
    guard = Guard()
    backend = Backend(guard)
    engine = Engine(flow or demo(),guard,backend,threading.Event(),SimpleNamespace(value=0),lambda _:None,**kw)
    return engine,guard,backend


class ModelTests(unittest.TestCase):
    def test_demo_valid(self):
        self.assertEqual(validate(demo())[1], "start")

    def test_bad_graphs_rejected(self):
        for change in (lambda f: f["nodes"][0]["edges"].update(next="missing"),
                       lambda f: f["nodes"].append(copy.deepcopy(f["nodes"][0])),
                       lambda f: f["nodes"][3]["params"].update(noise_px=float("nan")),
                       lambda f: f["nodes"][0].update(x=-1)):
            f=demo()
            change(f)
            with self.assertRaises(WorkflowError):
                validate(f)

    def test_expressions(self):
        self.assertEqual(expression("(counter + 3) * 2", {"counter":4}),14)
        self.assertTrue(expression("1 < counter <= 9 and not counter == 8",{"counter":4}))
        for source in ("__import__('os')", "x.__class__", "2 ** 999999999", "[0] * 999", "1e999", "missing", "1 / 0"):
            with self.subTest(source=source),self.assertRaises(WorkflowError):
                expression(source,{})

    def test_randomization_never_undercuts_floor(self):
        rng=random.Random(42)
        values=[safe_interval(0,100,rng) for _ in range(10000)]
        self.assertGreaterEqual(min(values),5)
        self.assertLessEqual(max(values),300)

    def test_curve_endpoint_and_easing(self):
        path=list(bezier((0,0),(100,50),100))
        self.assertEqual(path[-1],(100,50))
        self.assertLess(path[0][0],path[50][0]-path[49][0])
        self.assertTrue(all(-20 < y < 80 for x,y in path))

    def test_draft_roundtrip_and_execution_validation(self):
        flow=demo()
        flow["nodes"][0]["edges"]={}
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"draft.json"
            path.write_text(json.dumps(flow),encoding="utf-8")
            self.assertEqual(load(path),flow)
        with self.assertRaises(WorkflowError):
            validate(flow)


class EngineTests(unittest.TestCase):
    def test_dry_run_never_calls_backend(self):
        flow=demo()
        for node in flow["nodes"]:
            if node["type"]=="move": node["params"]["duration_ms"]=5
            if node["type"]=="wait": node["params"]["ms"]=5
            if node["type"]=="click": node["params"].update(interval_ms=0,jitter_ms=0)
        engine,guard,backend=make_engine(flow)
        engine.run()
        self.assertEqual(engine.clicks,5)
        self.assertEqual(engine.variables["counter"],5)
        self.assertEqual((backend.clicks,backend.moves),([],[]))
        self.assertGreater(guard.checks,20)

    def test_click_floor_including_scripts_api(self):
        engine,_,backend=make_engine(dry_run=False)
        start=time.monotonic()
        for _ in range(5): engine.click(interval_ms=0)
        gaps=[b-a for a,b in zip([start]+backend.times,backend.times)]
        self.assertTrue(all(g >= 0.0045 for g in gaps))

    def test_cancel_long_wait(self):
        engine,_,_=make_engine()
        timer=threading.Timer(0.025,engine.cancel.set)
        timer.start()
        start=time.monotonic()
        with self.assertRaises(Cancelled): engine.wait(100000)
        timer.join()
        self.assertLess(time.monotonic()-start,0.3)

    def test_target_loss_before_click(self):
        engine,guard,backend=make_engine(dry_run=False)
        guard.alive=False
        with self.assertRaises(OSError): engine.click(interval_ms=0)
        self.assertEqual(backend.clicks,[])

    def test_occlusion_before_click(self):
        engine,guard,backend=make_engine(dry_run=False)
        guard.covered=True
        with self.assertRaises(OSError): engine.click(interval_ms=0)
        self.assertEqual(backend.clicks,[])

    def test_human_input_delays_click(self):
        engine,_,backend=make_engine(dry_run=False)
        engine.pause_until.value=time.monotonic()+0.06
        start=time.monotonic()
        engine.click(interval_ms=0)
        self.assertGreaterEqual(backend.times[0]-start,0.055)

    def test_cancel_while_human_paused(self):
        engine,_,_=make_engine()
        engine.pause_until.value=time.monotonic()+20
        engine.cancel.set()
        with self.assertRaises(Cancelled): engine.checkpoint()

    def test_dpi_and_moved_window(self):
        engine,guard,backend=make_engine(dry_run=False)
        guard.origin=(-800,100)
        engine.move(100,100,duration_ms=5)
        self.assertEqual(backend.moves[-1],(-650,250))

    def test_ratio_coordinates(self):
        engine,guard,backend=make_engine(dry_run=False,coordinates="ratio")
        engine.move(0.5,0.5,duration_ms=5)
        self.assertEqual(backend.moves[-1],(600,400))

    def test_out_of_bounds_does_not_move(self):
        engine,_,backend=make_engine(dry_run=False)
        with self.assertRaises(OSError): engine.move(20000,0,5)
        self.assertEqual(backend.moves,[])

    def test_step_limit_stops_graph_cycle(self):
        flow=demo()
        flow["nodes"][1]["edges"]["next"]="init"
        # Keep an end reachable structurally using an IF with a never-taken branch.
        flow["nodes"][1].update(type="if",params={"condition":"True"},edges={"true":"init","false":"end"})
        engine,_,_=make_engine(flow,max_steps=5)
        with self.assertRaisesRegex(WorkflowError,"최대 노드"): engine.run()

    def test_script_requires_opt_in(self):
        flow=demo()
        flow["nodes"][0]["edges"]["next"]="python"
        flow["nodes"].append({"id":"python","type":"script","params":{"code":"api.set_var('answer', 42)"},"edges":{"next":"end"}})
        engine,_,_=make_engine(flow)
        with self.assertRaisesRegex(WorkflowError,"신뢰 허용"): engine.run()
        engine,_,_=make_engine(flow,allow_scripts=True)
        engine.run()
        self.assertEqual(engine.variables["answer"],42)

    def test_if_both_branches(self):
        for condition,wanted in (("True",10),("False",20)):
            flow={"version":1,"nodes":[
                {"id":"start","type":"start","params":{},"edges":{"next":"branch"}},
                {"id":"branch","type":"if","params":{"condition":condition},"edges":{"true":"a","false":"b"}},
                {"id":"a","type":"set","params":{"name":"result","value":"10"},"edges":{"next":"end"}},
                {"id":"b","type":"set","params":{"name":"result","value":"20"},"edges":{"next":"end"}},
                {"id":"end","type":"end","params":{},"edges":{}}]}
            engine,_,_=make_engine(flow)
            engine.run()
            self.assertEqual(engine.variables["result"],wanted)


if __name__=="__main__":
    unittest.main()
