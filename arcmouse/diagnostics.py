"""Opt-in packaging check: exercise the frozen UI and child processes without input."""
import json
from pathlib import Path
import platform
import sys
import time
import traceback


def self_test(report_path):
    from . import __version__, win32
    from .model import action
    from .ui import AutoClicker
    import tkinter as tk
    import serial

    report = {"version": __version__, "frozen": bool(getattr(sys, "frozen", False)),
              "python": platform.python_version(), "serial": serial.VERSION, "checks": []}
    root = app = None
    try:
        win32.dpi_aware()
        root = tk.Tk()
        root.withdraw()
        app = AutoClicker(root)
        # Avoid taking the normal user shortcuts during build verification.
        app.start_key.set("F22")
        app.stop_key.set("F23")
        app.extra["dry_run"] = True

        def wait_until(predicate, timeout=15):
            deadline = time.monotonic() + timeout
            while not predicate():
                root.update()
                if time.monotonic() >= deadline:
                    raise RuntimeError(f"Self-test timed out: {app.state.get()}")
                time.sleep(.01)

        wait_until(lambda: app.ready)
        assert app.registered == ("F22", "F23")
        report["checks"].append("Tk UI and independent hotkey process")
        app.repeat_mode.set("Fixed count")
        app.count.set("3")
        app.interval.set("5")

        def run_and_check(expected):
            app.run()
            assert app.busy, app.state.get()
            wait_until(lambda: not app.busy)
            assert app.state.get() == "Completed", app.state.get()
            assert app.stats.get() == f"Actions: {expected}", app.stats.get()

        run_and_check(3)
        report["checks"].append("Frozen worker spawn, Job Object, IPC and finite cursor dry run")
        app.actions = [action({"type": kind, "x": 10, "y": 10, "end_x": 20,
                               "end_y": 20, "duration_ms": 5, "wait_ms": 5})
                       for kind in ("click", "hold", "slide")]
        app.switch_mode("points")
        app.refresh_list(0)
        app.count.set("1")
        run_and_check(3)
        report["checks"].append("Click, hold and slide sequence dry run")
        app.actions = [action({"type": "hold", "x": 10, "y": 10,
                               "duration_ms": 60000, "wait_ms": 5})]
        app.refresh_list(0)
        app.run()
        wait_until(lambda: app.state.get() == "Dry run · Mouse input off")
        app.stop()
        wait_until(lambda: not app.busy)
        assert app.state.get() == "Stopped", app.state.get()
        assert app.held.value == 0
        report["checks"].append("Stop during a 60-second hold dry run")
        report["ok"] = True
    except Exception:
        report.update(ok=False, error=traceback.format_exc())
    finally:
        try:
            if app:
                app.close()
                assert not app.supervisor.is_alive(), "Supervisor did not exit"
            elif root:
                root.destroy()
        except Exception:
            report.update(ok=False, cleanup_error=traceback.format_exc())
        Path(report_path).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if report.get("ok") else 1
