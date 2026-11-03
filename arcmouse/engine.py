"""Cursor clicking or a sequential list of point actions; no target window."""
import time
from .model import MIN_DELAY_MS, SettingsError, number, validate_settings

BUTTON_MASK={"left":1,"right":2,"middle":4}


class Cancelled(Exception):
    pass


class Engine:
    def __init__(self,settings,backend,cancel,emit,held_state,max_seconds=1800):
        self.settings=validate_settings(settings)
        self.backend,self.cancel,self.emit,self.held_state=backend,cancel,emit,held_state
        self.deadline=time.monotonic()+max_seconds
        self.clicks,self.cycles,self.index=0,0,0
        self.last_emit=0

    def checkpoint(self):
        if self.cancel.is_set(): raise Cancelled()
        if time.monotonic()>=self.deadline: raise SettingsError("The 30-minute session limit has been reached.")

    def wait(self,ms):
        end=time.monotonic()+max(MIN_DELAY_MS,number(ms,0,3600000))/1000
        while True:
            self.checkpoint()
            if self.held_state.value and not self.settings["dry_run"]:
                self.backend.keep_alive()
            remaining=end-time.monotonic()
            if remaining<=0: return
            if self.cancel.wait(min(remaining,.01)): raise Cancelled()

    def progress(self,force=False):
        now=time.monotonic()
        if force or now-self.last_emit>=.1:
            self.emit({"type":"progress","clicks":self.clicks,"cycles":self.cycles,"index":self.index})
            self.last_emit=now

    def move(self,x,y):
        self.checkpoint()
        if not self.settings["dry_run"]: self.backend.move(x,y)

    def click(self,button):
        self.checkpoint()
        if not self.settings["dry_run"]: self.backend.click(button)
        self.clicks+=1

    def execute(self,item):
        self.move(item["x"],item["y"])
        if item["type"]=="click":
            self.click(item["button"])
        else:
            button=item["button"]
            if not self.settings["dry_run"]:
                self.held_state.value=BUTTON_MASK[button]
            try:
                self.checkpoint()
                if not self.settings["dry_run"]: self.backend.press(button)
                if item["type"]=="hold":
                    self.wait(item["duration_ms"])
                else:
                    duration=item["duration_ms"]
                    start=time.monotonic()
                    steps=max(1,min(750,int(duration/8)))
                    for i in range(1,steps+1):
                        self.checkpoint()
                        # Smooth acceleration along the user-chosen swipe segment.
                        t=i/steps
                        t=t*t*(3-2*t)
                        x=item["x"]+(item["end_x"]-item["x"])*t
                        y=item["y"]+(item["end_y"]-item["y"])*t
                        self.move(round(x),round(y))
                        self.wait(max(0,(start+duration*i/steps/1000-time.monotonic())*1000))
            finally:
                if not self.settings["dry_run"]:
                    self.backend.release(button)
                    self.held_state.value=0
            self.clicks+=1
        self.progress()
        self.wait(item["wait_ms"])

    def run(self):
        settings=self.settings
        try:
            while settings["count"]==0 or self.cycles<settings["count"]:
                self.checkpoint()
                if settings["mode"]=="cursor":
                    self.wait(settings["interval_ms"])
                    self.click(settings["button"])
                else:
                    for self.index,item in enumerate(settings["actions"],1):
                        self.execute(item)
                self.cycles+=1
                self.progress()
            self.progress(True)
        finally:
            if self.held_state.value and not settings["dry_run"]:
                self.backend.release_all()
                self.held_state.value=0


def worker_main(settings,cancel,gate,events,held_state):
    from . import win32
    win32.dpi_aware()
    backend=None
    def emit(event):
        try: events.put_nowait(event)
        except Exception: pass
    try:
        while not gate.wait(.01):
            if cancel.is_set(): raise Cancelled()
        backend=win32.SoftwareMouse()
        engine=Engine(settings,backend,cancel,emit,held_state)
        if settings["backend"]=="hardware" and not settings["dry_run"]:
            from .hardware import SerialMouse
            backend=SerialMouse(settings["port"],engine.checkpoint,win32.cursor,engine.checkpoint)
            engine.backend=backend
        if settings["mode"]=="points" and not settings["dry_run"]:
            for item in settings["actions"]:
                win32.check_screen_point(item["x"],item["y"])
                if item["type"]=="slide": win32.check_screen_point(item["end_x"],item["end_y"])
        emit({"type":"running"})
        engine.run()
        emit({"type":"completed"})
    except Cancelled: emit({"type":"stopped"})
    except BaseException as exc: emit({"type":"error","message":str(exc) or type(exc).__name__})
    finally:
        if backend: backend.close()
        events.close()
        events.join_thread()
