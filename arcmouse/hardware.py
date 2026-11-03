"""Ack-per-command transport. MCU never stores a macro or queues future clicks."""
import time


class SerialMouse:
    def __init__(self, port, checkpoint, position, before_click):
        try:
            import serial
        except ImportError as exc:
            raise RuntimeError("하드웨어 모드는 pip install -r requirements-hardware.txt가 필요합니다.") from exc
        self.checkpoint, self.position = checkpoint, position
        self.before_click = before_click
        self.sequence = 0
        self.last_ping = 0
        self.serial = serial.Serial(port, 115200, timeout=0.02, write_timeout=0.1)
        try:
            # Opening CDC may reset some boards. Cancellable boot wait.
            until = time.monotonic() + 2
            while time.monotonic() < until:
                checkpoint()
                time.sleep(0.01)
            self.serial.reset_input_buffer()
            self._request("HELLO", handshake=True)
            self._request("ARM")
        except BaseException:
            self.close()
            raise

    def _request(self, command, handshake=False, check_cancel=True):
        if command.startswith(("MOVE ", "CLICK ", "PRESS ")):
            self._request("ARM")  # Watchdog may have disarmed during a long wait/pause.
        self.sequence += 1
        seq = self.sequence
        if check_cancel:
            self.checkpoint()
        if command.startswith("CLICK "):
            self.before_click()
        self.serial.write(f"{seq} {command}\n".encode("ascii"))
        deadline = time.monotonic() + 0.15
        expected = f"{seq} ARCMOUSE/2" if handshake else f"{seq} OK"
        response = bytearray()
        while time.monotonic() < deadline:
            if check_cancel:
                self.checkpoint()
            chunk = self.serial.read(1)
            if chunk == b"\n":
                line = response.decode("ascii", errors="replace").strip()
                if line == expected:
                    return
                raise OSError(f"MCU 응답 오류: {line}")
            response.extend(chunk)
            if len(response) > 96:
                raise OSError("MCU 응답 길이 초과")
        raise OSError("MCU 응답 시간 초과: 입력을 중단했습니다.")

    def move(self, x, y):
        # Relative HID is affected by OS acceleration. Closed-loop cursor feedback
        # converges with small corrections; fails closed if clipped/unreachable.
        for _ in range(100):
            self.checkpoint()
            cx, cy = self.position()
            dx, dy = round(x - cx), round(y - cy)
            if abs(dx) <= 1 and abs(dy) <= 1:
                return
            dx = max(-20, min(20, round(dx / 2) or (1 if dx > 0 else -1))) if dx else 0
            dy = max(-20, min(20, round(dy / 2) or (1 if dy > 0 else -1))) if dy else 0
            self._request(f"MOVE {dx} {dy}")
            time.sleep(0.005)
        raise OSError("HID 상대 이동이 목표 좌표에 수렴하지 않았습니다.")

    def click(self, button):
        code = {"left": 1, "right": 2, "middle": 4}[button]
        self._request(f"CLICK {code}")

    def press(self, button):
        code = {"left": 1, "right": 2, "middle": 4}[button]
        self._request(f"PRESS {code}")
        self.last_ping = time.monotonic()

    def release(self, button):
        code = {"left": 1, "right": 2, "middle": 4}[button]
        self._request(f"RELEASE {code}", check_cancel=False)

    def release_all(self):
        self._request("STOP", check_cancel=False)

    def keep_alive(self):
        if time.monotonic() - self.last_ping >= 0.05:
            self._request("ARM")
            self.last_ping = time.monotonic()

    def close(self):
        if getattr(self, "serial", None) and self.serial.is_open:
            try:
                self.serial.write(b"0 STOP\n")
            except Exception:
                pass
            self.serial.close()
