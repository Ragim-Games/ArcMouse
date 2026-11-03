"""Independent configurable hotkeys, cancellation, and process containment."""
import multiprocessing as mp
import queue
import time
from .engine import worker_main
from .model import validate_settings


def supervisor_main(pipe,held_state=None):
    from . import win32
    win32.dpi_aware()
    ctx=mp.get_context("spawn")
    held_state=held_state if held_state is not None else ctx.Value("I",0,lock=False)
    monitor=worker=job=events=cancel=None
    last_gui,last_heartbeat=time.monotonic(),0
    deadline=0
    terminal_event=None
    epoch=0
    active_backend="software"
    configured=False

    def send(event): pipe.send(event)

    def release():
        if held_state.value and active_backend=="software":
            win32.release_buttons(held_state.value)
        held_state.value=0

    def dispose():
        nonlocal worker,job,events
        if worker:
            cancel.set()
            if worker.pid is not None:worker.join(.08)
            if job:
                job.close()
                job=None
            if worker.pid is not None:
                if worker.is_alive(): worker.terminate()
                worker.join(.5)
            worker.close()
            worker=None
        release()
        if events:
            events.close()
            events=None

    def stop(reason):
        nonlocal epoch
        epoch+=1
        dispose()
        send({"type":"stopped","reason":reason})

    try:
        monitor=win32.HotkeyMonitor()
        send({"type":"ready","emergency":monitor.emergency})
        while True:
            monitor.pump()
            now=time.monotonic()
            # Stop wins if both hotkeys arrive in one batch.
            requests=monitor.requests[:]
            monitor.requests.clear()
            if "stop" in requests: stop("Stopped")
            elif "start" in requests and not worker and configured:
                send({"type":"hotkey_start","epoch":epoch})
            if worker and now>=deadline: stop("The 30-minute session limit has been reached")
            if now-last_gui>2.5:
                stop("Stopped because the app stopped responding")
                break
            for _ in range(32):
                if not pipe.poll(): break
                command=pipe.recv()
                kind=command.get("type")
                if kind=="heartbeat": last_gui=now
                elif kind=="shutdown":
                    stop("App closed")
                    return
                elif kind=="stop": stop("Stopped")
                elif kind=="hotkeys":
                    if worker:
                        send({"type":"hotkey_error","message":"Stop execution before changing hotkeys."})
                        continue
                    try:
                        start,end=monitor.configure(command["start"],command["stop"])
                        configured=True
                        send({"type":"hotkeys","start":start,"stop":end})
                    except Exception as exc:
                        send({"type":"hotkey_error","message":str(exc)})
                elif kind=="start":
                    if worker: continue
                    if command.get("epoch",epoch)!=epoch: continue
                    try:
                        if not configured: raise ValueError("Apply the Start and Stop hotkeys first.")
                        settings=validate_settings(command["settings"])
                        active_backend=settings["backend"]
                        held_state.value=0
                        cancel,gate=ctx.Event(),ctx.Event()
                        events=ctx.Queue(maxsize=128)
                        terminal_event=None
                        worker=ctx.Process(target=worker_main,args=(settings,cancel,gate,events,held_state),name="ArcMouse-Clicker")
                        worker.start()
                        job=win32.KillJob(worker.sentinel)
                        gate.set()
                        deadline=now+1800
                    except Exception as exc:
                        dispose()
                        send({"type":"error","message":str(exc)})
            if worker:
                for _ in range(128):
                    try: event=events.get_nowait()
                    except queue.Empty: break
                    if event["type"] in ("completed","stopped","error"):terminal_event=event
                    else:send(event)
                if not worker.is_alive():
                    # The child's queue feeder is flushed before it exits.
                    for _ in range(128):
                        try: event=events.get_nowait()
                        except queue.Empty: break
                        if event["type"] in ("completed","stopped","error"):terminal_event=event
                        else:send(event)
                    dispose()
                    send(terminal_event or {"type":"error","message":"The input engine exited unexpectedly."})
                    send({"type":"idle"})
            if now-last_heartbeat>.3:
                send({"type":"heartbeat"})
                last_heartbeat=now
            time.sleep(.003)
    except (EOFError,BrokenPipeError): pass
    except BaseException as exc:
        try: send({"type":"fatal","message":str(exc)})
        except (EOFError,BrokenPipeError): pass
    finally:
        try: dispose()
        finally:
            if monitor: monitor.close()
            pipe.close()
