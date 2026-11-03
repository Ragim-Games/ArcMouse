# USB hardware setup

Both firmware implementations receive serial commands and send USB HID mouse reports. The MCU does not store or autonomously repeat macros. Without another command from the PC, it does not generate another click. The firmware is a draft implementation and still requires compilation, upload, and input validation on physical boards.

## Arduino Leonardo / Micro

1. In Arduino IDE, select an ATmega32u4-based Leonardo or Micro. This sketch is not for a standard Uno.
2. Open `firmware/ArcMouseLeonardo/ArcMouseLeonardo.ino`. It uses Arduino's `Mouse` library.
3. Optionally connect a push button between **D2 and GND**. The internal pull-up is enabled; ARM and input commands are rejected while the button is held.
4. Upload the sketch and reconnect the USB cable.
5. Find the CDC COM port in Device Manager.

See the [Arduino Mouse documentation](https://docs.arduino.cc/language-reference/en/functions/usb/Mouse/) for the USB mouse API.

## Raspberry Pi Pico

1. Install CircuitPython for your board. This differs from standard MicroPython firmware.
2. Copy the `adafruit_hid` folder from the Adafruit library bundle matching your CircuitPython version into `CIRCUITPY/lib`.
3. Copy `firmware/pico/boot.py` and `code.py` to the root of `CIRCUITPY`, then reconnect power.
4. Optionally connect a push button between **GP2 and GND**.
5. Use the **CDC data port** in ArcMouse. Selecting the console port causes the handshake to fail. Do not assume the two ports have consecutive numbers.

Windows exposes the console and data streams as separate COM ports; see the [CircuitPython usb_cdc documentation](https://docs.circuitpython.org/en/latest/shared-bindings/usb_cdc/). See the [Adafruit HID documentation](https://docs.circuitpython.org/projects/hid/en/latest/api.html#adafruit_hid.mouse.Mouse) for the mouse API.

## App settings

```powershell
python -m pip install -r requirements-hardware.txt
python main.py
```

1. Select **Settings → USB board** and enter the board's COM port.
2. **Dry run (no mouse input)** does not open the serial port. Turn it off for physical board validation.
3. Start by testing three clicks in a dedicated blank test window.
4. Check holds, slides, your configured Stop hotkey, and the physical stop button.

No separate HID device path is needed. An incorrect COM port or a board running an older protocol is rejected during HELLO. Use the bundled ARCMOUSE/2 firmware with the 0.3 app series.

## ARCMOUSE/2 protocol

115200 baud, ASCII, at most 63 bytes per line, terminated by LF. The host waits for the response with the correct sequence number before sending the next command. A response timeout of 150 ms stops execution with an error. After opening the port, the host waits for two seconds to allow a board reset; this wait can be canceled.

| Command | Response | Meaning |
|---|---|---|
| `1 HELLO` | `1 ARCMOUSE/2` | Identify the board, release buttons, and disarm |
| `2 ARM` | `2 OK` | Allow input; rejected while the stop button is held |
| `3 MOVE 10 -5` | `3 OK` | Relative HID movement; each axis is -127 to 127 |
| `4 CLICK 1` | `4 OK` | Left click; 2 is right and 4 is middle |
| `5 PRESS 1` | `5 OK` | Press a button to begin a hold or slide |
| `6 RELEASE 1` | `6 OK` | Release the specified button |
| `0 STOP` | `0 OK` | Release all buttons and disarm |

The host sends ARM before each MOVE, CLICK, or PRESS. This allows the next intended action after a long wait has caused the watchdog to disarm. During a hold, the host refreshes the watchdog with ARM roughly every 50 ms. RELEASE and STOP can still be sent after cancellation. The MCU releases all buttons and disarms 150 ms after the last valid input or ARM. CLICK presses for 5 ms, releases, and then acknowledges the command. An event already submitted to the USB stack cannot necessarily be recalled.

The physical stop pin and watchdog are handled by firmware logic. If the firmware loop itself hangs, the 150 ms deadline is not guaranteed. Validate USB behavior, disconnection and reconnection, button faults, and CPU load on each supported board before distributing tested firmware.

## Relative HID coordinates

Standard USB mouse reports contain relative movement. Windows pointer acceleration affects that movement, so the host reads the actual cursor position and sends small corrections. It stops if it cannot converge to within one pixel on each axis in 100 attempts. Applications that lock the pointer to the center, use exclusive Raw Input, or restrict it through ClipCursor may not work. Serial round trips can make MCU movement slower than software input.

## Physical validation checklist

- [ ] Firmware compiles and uploads successfully
- [ ] USB HID mouse and CDC port appear correctly
- [ ] HELLO, ARM, and STOP work; invalid commands are rejected
- [ ] Relative movement direction, magnitude, and all mouse buttons work
- [ ] No additional clicks after USB disconnection or forced host termination
- [ ] No input while the physical stop button is held
- [ ] Missing acknowledgements stop the host
- [ ] Stopping or terminating the host during a hold or slide releases the button
- [ ] Coordinates converge across DPI, monitor, and pointer acceleration settings
