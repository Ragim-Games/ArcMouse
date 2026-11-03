"""Raspberry Pi Pico + CircuitPython + adafruit_hid. GP2 to GND = physical stop."""
import time
import board
import digitalio
import usb_cdc
import usb_hid
from adafruit_hid.mouse import Mouse

mouse = Mouse(usb_hid.devices)
port = usb_cdc.data
kill = digitalio.DigitalInOut(board.GP2)
kill.switch_to_input(pull=digitalio.Pull.UP)
armed = False
last_command = 0.0
buffer = bytearray()
overflowed = False
port.timeout = 0
port.write_timeout = 0.02


def release_all():
    global armed
    mouse.release_all()
    armed = False


def respond(seq, text):
    port.write((str(seq) + " " + text + "\n").encode("ascii"))


def execute(raw):
    global armed, last_command
    seq = 0
    try:
        words = raw.decode("ascii").strip().split()
        seq, command = int(words[0]), words[1]
        if not 0 <= seq <= 2147483647:
            raise ValueError("sequence")
        if command == "STOP":
            release_all()
        elif command == "HELLO":
            release_all()
            respond(seq, "ARCMOUSE/2")
            return
        elif not kill.value:
            raise ValueError("KILL")
        elif command == "ARM":
            armed = True
            last_command = time.monotonic()
        elif not armed or time.monotonic() - last_command > 0.15:
            raise ValueError("DISARMED")
        elif command == "MOVE" and len(words) == 4:
            dx, dy = int(words[2]), int(words[3])
            if not -127 <= dx <= 127 or not -127 <= dy <= 127:
                raise ValueError("MOVE")
            mouse.move(x=dx, y=dy)
            last_command = time.monotonic()
        elif command in ("CLICK", "PRESS", "RELEASE") and len(words) == 3 and int(words[2]) in (1, 2, 4):
            if command == "RELEASE":
                mouse.release(int(words[2]))
            else:
                mouse.press(int(words[2]))
                if command == "CLICK":
                    time.sleep(0.005)
                    mouse.release_all()
            last_command = time.monotonic()
        else:
            raise ValueError("COMMAND")
        respond(seq, "OK")
    except (ValueError, IndexError, UnicodeError):
        release_all()
        respond(seq, "ERR COMMAND")


release_all()
while True:
    if not kill.value or not port.connected or (armed and time.monotonic() - last_command > 0.15):
        release_all()
    if port.in_waiting:
        # Bound work to keep physical stop/watchdog checks responsive.
        for value in port.read(min(port.in_waiting, 64)) or b"":
            if value == 10:
                if not overflowed:
                    execute(buffer)
                else:
                    release_all()
                buffer = bytearray()
                overflowed = False
            elif value != 13:
                if len(buffer) < 63 and not overflowed:
                    buffer.append(value)
                else:
                    overflowed = True
                    release_all()
    time.sleep(0.001)
