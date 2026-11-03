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
            if "stop" in requests: stop("중단했습니다")
            elif "start" in requests and not worker and configured:
                send({"type":"hotkey_start","epoch":epoch})
            if worker and now>=deadline: stop("30분 실행 한도에 도달했습니다")
            if now-last_gui>2.5:
                stop("앱 응답이 없어 중단했습니다")
                break
            for _ in range(32):
                if not pipe.poll(): break
                command=pipe.recv()
                kind=command.get("type")
                if kind=="heartbeat": last_gui=now
                elif kind=="shutdown":
                    stop("앱 종료")
                    return
                elif kind=="stop": stop("중단했습니다")
                elif kind=="hotkeys":
                    if worker:
                        send({"type":"hotkey_error","message":"실행을 중단한 뒤 단축키를 변경하세요."})
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
                        if not configured: raise ValueError("시작·중단 단축키를 먼저 적용하세요.")
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
                    send(terminal_event or {"type":"error","message":"클릭 엔진이 종료됐습니다."})
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
