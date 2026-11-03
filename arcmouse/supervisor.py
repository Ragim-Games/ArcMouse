"""Safety process: global hotkey, Raw Input, UI heartbeat, worker Job Object."""
import multiprocessing as mp
import queue
import time

from .engine import worker_main
from .model import validate


def supervisor_main(pipe):
    from . import win32
    win32.dpi_aware()
    ctx = mp.get_context("spawn")
    pause_until = ctx.Value("d", 0.0, lock=False)
    monitor = worker = job = events = cancel = None
    pending = None
    last_gui, last_heartbeat = time.monotonic(), 0
    terminal_seen = False
    worker_deadline = 0

    def send(event):
        pipe.send(event)

    def stop(reason="중지됨"):
        nonlocal worker, job, events, pending
        pending = None
        if worker:
            cancel.set()
            worker.join(0.08)
            if job:
                job.close()  # Kills worker descendants as well, even for trusted scripts.
                job = None
            if worker.is_alive():
                worker.terminate()
            worker.join(0.5)
            worker.close()
            worker = None
        if events:
            events.close()
            events = None
        if monitor:
            monitor.excluded_device = ""
        send({"type": "stopped", "reason": reason})

    try:
        monitor = win32.InputMonitor(pause_until)
        send({"type": "ready"})
        while True:
            monitor.pump()
            now = time.monotonic()
            if monitor.kill_requested:
                monitor.kill_requested = False
                stop("비상 정지 · 입력 엔진 종료")
            if monitor.input_error:
                raise OSError(monitor.input_error)
            if worker and now >= worker_deadline:
                stop("30분 세션 한도 · 실행 엔진 종료")
            if now - last_gui > 2.5:
                stop("UI 응답 유실")
                break
            for _ in range(32):
                if not pipe.poll():
                    break
                command = pipe.recv()
                kind = command.get("type")
                if kind == "heartbeat":
                    last_gui = now
                elif kind == "shutdown":
                    stop("앱 종료")
                    return
                elif kind == "stop":
                    stop("사용자가 중지했습니다.")
                elif kind == "start":
                    if worker or pending:
                        send({"type": "error", "message": "이미 실행 중입니다."})
                        continue
                    try:
                        validate(command["flow"])
                        settings = command["settings"]
                        if settings["backend"] == "hardware" and not settings["dry_run"]:
                            device = settings.get("device", "")
                            if not device or device not in win32.mouse_devices():
                                raise ValueError("연결된 MCU의 HID 마우스 장치를 선택하세요.")
                            monitor.excluded_device = device
                        pending = (now + 3, command)
                        send({"type": "countdown", "seconds": 3})
                    except Exception as exc:
                        send({"type": "error", "message": str(exc)})
            if pending and now >= pending[0]:
                command = pending[1]
                pending = None
                cancel, gate = ctx.Event(), ctx.Event()
                events = ctx.Queue(maxsize=128)
                terminal_seen = False
                worker = ctx.Process(target=worker_main,
                    args=(command["flow"], command["settings"], command["target"],
                          cancel, pause_until, gate, events), name="ArcMouse-Engine")
                worker.start()
                worker_deadline = now + 1800
                try:
                    job = win32.KillJob(worker.sentinel)
                    gate.set()  # Worker cannot emit input until protected by Job Object.
                except Exception:
                    stop("실행 보호 초기화 실패")
                    raise
            if worker:
                for _ in range(24):
                    try:
                        event = events.get_nowait()
                    except queue.Empty:
                        break
                    terminal_seen |= event["type"] in ("completed", "stopped", "error")
                    send(event)
                if not worker.is_alive():
                    # Feeder flushed before child exit; collect its final status first.
                    for _ in range(128):
                        try:
                            event = events.get_nowait()
                        except queue.Empty:
                            break
                        terminal_seen |= event["type"] in ("completed", "stopped", "error")
                        send(event)
                    if not terminal_seen:
                        send({"type": "error", "message": f"실행 엔진이 예기치 않게 종료되었습니다 ({worker.exitcode})."})
                    if job:
                        job.close()
                        job = None
                    worker.join()
                    worker.close()
                    worker = None
                    events.close()
                    events = None
                    monitor.excluded_device = ""
                    send({"type": "idle"})
            if now - last_heartbeat > 0.3:
                send({"type": "heartbeat"})
                last_heartbeat = now
            time.sleep(0.003)
    except (EOFError, BrokenPipeError):
        pass
    except BaseException as exc:
        try:
            send({"type": "fatal", "message": str(exc)})
        except (BrokenPipeError, EOFError):
            pass
    finally:
        if cancel:
            cancel.set()
        if job:
            job.close()
        if worker:
            worker.join(0.1)
            if worker.is_alive():
                worker.terminate()
                worker.join(0.5)
        if monitor:
            monitor.close()
        pipe.close()
