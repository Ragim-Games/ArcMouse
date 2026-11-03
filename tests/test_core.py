import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from arcmouse.engine import Engine, Cancelled
from arcmouse.model import SettingsError, action, hotkey, hotkey_pair, validate_settings, save_profile, load_profile

class Backend:
    def __init__(self): self.events=[]; self.on_press=lambda:None; self.fail_move=False
    def record(self,*event): self.events.append((*event,time.monotonic()))
    def move(self,x,y):
        if self.fail_move and any(e[0]=='press' for e in self.events): raise OSError('move failed')
        self.record('move',x,y)
    def click(self,b): self.record('click',b)
    def press(self,b): self.record('press',b); self.on_press()
    def release(self,b): self.record('release',b)
    def release_all(self): self.record('release_all')
    def keep_alive(self): self.record('ping')

def make(settings=None,**kw):
    backend=Backend(); cancel=threading.Event(); held=SimpleNamespace(value=0); events=[]
    engine=Engine({'count':1,'interval_ms':5,**(settings or {})},backend,cancel,events.append,held,**kw)
    return engine,backend,cancel,held,events

def point(kind='click',**kw): return action({'type':kind,'x':10,'y':20,'wait_ms':5,**kw})

class SettingsTests(unittest.TestCase):
    def test_defaults_no_target(self):
        s=validate_settings({});self.assertEqual(s['mode'],'cursor');self.assertEqual(s['start_hotkey'],'F6');self.assertNotIn('target',s)
    def test_bad_settings(self):
        for s in ({'count':True},{'count':1.5},{'interval_ms':float('nan')},{'target':{}},{'button':'bad'},{'mode':'points'},{'dry_run':'false'},{'backend':'hardware','port':''}):
            with self.subTest(s=s),self.assertRaises(SettingsError):validate_settings(s)
    def test_safe_delay(self):
        self.assertEqual(validate_settings({'interval_ms':0})['interval_ms'],5)
        self.assertEqual(point(wait_ms=0)['wait_ms'],5)
    def test_points_validation(self):
        for p in ({'x':0},{'x':0,'y':0,'duration_ms':0},{'x':0,'y':float('inf')},{'type':'slide','x':0,'y':0}):
            with self.subTest(p=p),self.assertRaises(SettingsError):action(p)
        self.assertEqual(point(x=-100)['x'],-100)
    def test_hotkey_canonical(self):
        self.assertEqual(hotkey('alt + control + s'),(3,83,'Ctrl+Alt+S'))
        self.assertEqual(hotkey('F07')[2],'F7')
    def test_invalid_hotkeys(self):
        for k in ('F12','F25','A','Shift+A','Ctrl+Ctrl+A','Ctrl++A'):
            with self.subTest(k=k),self.assertRaises(SettingsError):hotkey(k)
        for a,b in [('F6','F6'),('Ctrl+Alt+Shift+K','F7')]:
            with self.assertRaises(SettingsError):hotkey_pair(a,b)
    def test_profile_roundtrip(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'points.json';s=validate_settings({'mode':'points','actions':[point(),point('slide',end_x=50,end_y=80)],'start_hotkey':'Ctrl+Alt+S'})
            save_profile(path,s);self.assertEqual(load_profile(path),s)
    def test_empty_editable_profile(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'empty.json';save_profile(path,{'mode':'points'});self.assertEqual(load_profile(path)['actions'],[])

class EngineTests(unittest.TestCase):
    def test_cursor_does_not_move(self):
        e,b,_,_,events=make({'count':3});e.run()
        self.assertEqual([x[0] for x in b.events],['click']*3);self.assertEqual(events[-1]['clicks'],3)
    def test_order_and_post_action_wait(self):
        e,b,_,_,_=make({'mode':'points','actions':[point(wait_ms=45),point('hold',duration_ms=50,wait_ms=35)],'count':2});e.run()
        events=[x for x in b.events if x[0]!='ping']
        self.assertEqual([x[0] for x in events],['move','click','move','press','release']*2)
        self.assertGreaterEqual(events[2][-1]-events[1][-1],.043)
        self.assertGreaterEqual(events[4][-1]-events[3][-1],.048)
        self.assertGreaterEqual(events[5][-1]-events[4][-1],.033)
    def test_last_action_wait_is_not_skipped(self):
        e,b,_,_,_=make({'mode':'points','actions':[point(wait_ms=35)]});e.run()
        self.assertGreaterEqual(time.monotonic()-b.events[-1][-1],.033)
    def test_slide_holds_button_through_endpoint(self):
        e,b,_,held,_=make({'mode':'points','actions':[point('slide',end_x=100,end_y=-20,duration_ms=40)]});e.run()
        events=[x for x in b.events if x[0]!='ping']
        self.assertEqual(events[1][:2],('press','left'));self.assertEqual(events[-2][:3],('move',100,-20));self.assertEqual(events[-1][:2],('release','left'));self.assertEqual(held.value,0)
    def test_cancel_hold_releases_promptly(self):
        e,b,c,held,_=make({'mode':'points','actions':[point('hold',duration_ms=60000)]})
        b.on_press=c.set;start=time.monotonic()
        with self.assertRaises(Cancelled):e.run()
        self.assertLess(time.monotonic()-start,.2);self.assertEqual(b.events[-1][:2],('release','left'));self.assertEqual(held.value,0)
    def test_failed_slide_releases(self):
        e,b,_,held,_=make({'mode':'points','actions':[point('slide',end_x=100,end_y=100)]});b.fail_move=True
        with self.assertRaises(OSError):e.run()
        self.assertEqual(b.events[-1][:2],('release','left'));self.assertEqual(held.value,0)
    def test_cancel_wait_produces_no_click(self):
        e,b,c,_,_=make();c.set()
        with self.assertRaises(Cancelled):e.run()
        self.assertEqual(b.events,[])
    def test_dry_run_no_input(self):
        e,b,_,_,events=make({'mode':'points','dry_run':True,'actions':[point(),point('hold',duration_ms=5),point('slide',end_x=50,end_y=50,duration_ms=5)]});e.run()
        self.assertEqual(b.events,[]);self.assertEqual(events[-1]['clicks'],3)
    def test_time_limit(self):
        e,b,_,_,_=make(max_seconds=-1)
        with self.assertRaises(SettingsError):e.run()
        self.assertEqual(b.events,[])

if __name__=='__main__':unittest.main()
