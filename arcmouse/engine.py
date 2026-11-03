"""Workflow runner. All waits are cancellable; native I/O is behind one API."""
from __future__ import annotations

import random
import time
from .model import MIN_DELAY_MS, WorkflowError, bezier, expression, number, safe_interval, validate


class Cancelled(Exception):
    pass


class Engine:
    def __init__(self, flow, guard, backend, cancel, pause_until, emit,
                 dry_run=True, coordinates="dip", allow_scripts=False, max_steps=100_000, max_seconds=1800):
        self.nodes, self.current = validate(flow)
        self.guard, self.backend = guard, backend
        self.cancel, self.pause_until, self.emit = cancel, pause_until, emit
        self.dry_run, self.coordinates, self.allow_scripts = dry_run, coordinates, allow_scripts
        self.max_steps, self.deadline = max_steps, time.monotonic() + max_seconds
        self.variables, self.loops = {}, {}
        self.steps, self.clicks = 0, 0
        self.last_emit = 0
        self.last_log = 0
        self.rng = random.Random()
        self.virtual_cursor = None

    def checkpoint(self):
        if self.cancel.is_set():
            raise Cancelled()
        if time.monotonic() >= self.deadline:
            raise WorkflowError("세션 시간 한도에 도달했습니다.")
        self.guard.check()
        paused = False
        while time.monotonic() < self.pause_until.value:
            if not paused:
                self.emit({"type": "paused", "reason": "사용자 입력 · 제어권 양보"})
                paused = True
            if self.cancel.wait(0.005):
                raise Cancelled()
            self.guard.check()
            if time.monotonic() >= self.deadline:
                raise WorkflowError("세션 시간 한도에 도달했습니다.")
        if paused:
            self.emit({"type": "running"})

    def wait(self, ms):
        duration = max(MIN_DELAY_MS, number(ms, 0, 3_600_000)) / 1000
        end = time.monotonic() + duration
        while True:
            self.checkpoint()
            remaining = end - time.monotonic()
            if remaining <= 0:
                return
            if self.cancel.wait(min(remaining, 0.01)):
                raise Cancelled()

    def position(self):
        if self.dry_run and self.virtual_cursor is not None:
            return self.virtual_cursor
        return self.guard.cursor()

    def move(self, x, y, duration_ms=350, noise_px=0):
        self.checkpoint()
        x, y = number(x), number(y)
        duration_ms = number(duration_ms, 5, 60_000)
        noise = number(noise_px, 0, 100)
        ox, oy, width, height, scale = self.guard.geometry()
        cx, cy = self.position()
        # Curve is in client-relative units so moving a window won't leave stale endpoints.
        sx = min(max(cx - ox, 0), width - 1)
        sy = min(max(cy - oy, 0), height - 1)
        if self.coordinates == "ratio":
            start = (sx / max(1, width - 1), sy / max(1, height - 1))
            nx, ny = max(1, width - 1), max(1, height - 1)
        else:
            start, nx, ny = (sx / scale, sy / scale), scale, scale
        end = (x + max(-3*noise, min(3*noise, self.rng.gauss(0, noise))) / nx,
               y + max(-3*noise, min(3*noise, self.rng.gauss(0, noise))) / ny)
        self.guard.resolve(*end, self.coordinates)
        steps = max(1, min(1200, int(duration_ms / 8)))
        for px, py in bezier(start, end, steps, bend=self.rng.uniform(-0.18, 0.18)):
            self.checkpoint()
            point = self.guard.resolve(px, py, self.coordinates)
            if self.dry_run:
                self.virtual_cursor = point
            else:
                self.backend.move(*point)
            self.wait(duration_ms / steps)

    def click(self, button="left", interval_ms=150, jitter_ms=0):
        if button not in ("left", "right", "middle"):
            raise WorkflowError("지원하지 않는 마우스 버튼")
        # Even script API calls must wait before every click, including the first.
        self.wait(safe_interval(interval_ms, jitter_ms, self.rng))
        self.checkpoint()
        self.guard.check_point(self.position())
        if not self.dry_run:
            self.backend.click(button)
        self.clicks += 1
        self.progress()

    def log(self, text):
        self.checkpoint()
        now = time.monotonic()
        if now - self.last_log >= 0.1:
            self.emit({"type": "log", "message": str(text)[:500]})
            self.last_log = now

    def set_var(self, name, value):
        if not isinstance(name, str) or not name.isidentifier() or name.startswith("_"):
            raise WorkflowError("잘못된 변수 이름")
        self.variables[name] = number(value)

    def get_var(self, name, default=0):
        return self.variables.get(name, default)

    def progress(self, force=False):
        now = time.monotonic()
        if force or now - self.last_emit >= 0.1:
            self.emit({"type": "progress", "node": self.current, "steps": self.steps,
                       "clicks": self.clicks, "variables": dict(self.variables)})
            self.last_emit = now

    def run(self):
        while True:
            self.checkpoint()
            if self.steps >= self.max_steps:
                raise WorkflowError("최대 노드 실행 수에 도달했습니다. 순환 연결을 확인하세요.")
            node = self.nodes[self.current]
            kind, p, edges = node["type"], node.get("params", {}), node.get("edges", {})
            self.steps += 1
            self.progress()
            port = "next"
            if kind == "end":
                self.progress(True)
                return
            if kind == "move":
                self.move(expression(p["x"], self.variables), expression(p["y"], self.variables),
                          p["duration_ms"], p["noise_px"])
            elif kind == "click":
                self.click(p["button"], p["interval_ms"], p["jitter_ms"])
            elif kind == "wait":
                self.wait(p["ms"])
            elif kind == "set":
                self.set_var(p["name"], expression(p["value"], self.variables))
            elif kind == "if":
                port = "true" if expression(p["condition"], self.variables) else "false"
            elif kind == "repeat":
                if self.current not in self.loops:
                    raw_count = number(expression(p["count"], self.variables), 0, 100_000)
                    if raw_count != int(raw_count):
                        raise WorkflowError("반복 횟수는 정수여야 합니다.")
                    self.loops[self.current] = int(raw_count)
                remaining = self.loops[self.current]
                port = "body" if remaining else "done"
                if remaining:
                    self.loops[self.current] -= 1
                else:
                    del self.loops[self.current]
            elif kind == "script":
                if not self.allow_scripts:
                    raise WorkflowError("Python 스크립트는 신뢰 허용을 켠 경우에만 실행됩니다.")
                # Deliberately not a security sandbox: runs trusted local Python.
                exec(compile(p["code"], f"<node:{self.current}>", "exec"), {"api": self})
            self.wait(MIN_DELAY_MS)  # Covers pure logic cycles too.
            self.current = edges[port]


def worker_main(flow, settings, target, cancel, pause_until, gate, events):
    from . import win32
    win32.dpi_aware()
    backend = guard = None

    def emit(event):
        try:
            events.put_nowait(event)
        except Exception:
            pass  # Bounded logging must never block input cancellation.

    try:
        while not gate.wait(0.01):
            if cancel.is_set():
                raise Cancelled()
        guard = win32.TargetGuard(target)
        guard.cursor = win32.cursor
        backend = win32.SoftwareMouse()
        engine = Engine(flow, guard, backend, cancel, pause_until, emit,
                        dry_run=settings["dry_run"], coordinates=settings["coordinates"],
                        allow_scripts=settings["allow_scripts"])
        if settings["backend"] == "hardware" and not settings["dry_run"]:
            from .hardware import SerialMouse
            backend = SerialMouse(settings["port"], engine.checkpoint, win32.cursor,
                                  lambda: guard.check_point(win32.cursor()))
            engine.backend = backend
        emit({"type": "running"})
        engine.run()
        emit({"type": "completed"})
    except Cancelled:
        emit({"type": "stopped"})
    except BaseException as exc:
        emit({"type": "error", "message": str(exc) or type(exc).__name__})
    finally:
        if backend:
            backend.close()
        if guard:
            guard.close()
        events.close()
        events.join_thread()
