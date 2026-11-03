import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from arcmouse.hardware import SerialMouse


class FakeSerial:
    def __init__(self,*a,**kw):
        self.is_open=True
        self.sent=[]
        self.reply=bytearray()
        self.bad=False

    def write(self,data):
        self.sent.append(data.decode().strip())
        seq,command,*_=data.decode().split()
        suffix="ARCMOUSE/2" if command=="HELLO" else "OK"
        self.reply.extend(f"{seq} {'ERR' if self.bad else suffix}\n".encode())

    def read(self,n):
        answer=self.reply[:n]
        del self.reply[:n]
        return bytes(answer)

    def reset_input_buffer(self): self.reply.clear()
    def close(self): self.is_open=False


class HardwareTests(unittest.TestCase):
    def setUp(self):
        self.serial=FakeSerial()
        self.mouse=SerialMouse.__new__(SerialMouse)
        self.mouse.serial=self.serial
        self.mouse.sequence=0
        self.mouse.last_ping=0
        self.mouse.checkpoint=lambda:None
        self.mouse.before_click=lambda:None
        self.mouse.position=lambda:(10,10)

    def test_rearms_before_click_and_ack_matches(self):
        self.mouse.click("right")
        self.assertEqual(self.serial.sent,["1 ARM","2 CLICK 2"])

    def test_bad_ack_is_error_and_no_click(self):
        self.serial.bad=True
        with self.assertRaises(OSError): self.mouse.click("left")
        self.assertEqual(self.serial.sent,["1 ARM"])

    def test_final_cancellation_check_before_click(self):
        def lost(): raise OSError("lost")
        self.mouse.before_click=lost
        with self.assertRaises(OSError): self.mouse.click("left")
        self.assertEqual(self.serial.sent,["1 ARM"])

    def test_stop_on_close(self):
        self.mouse.close()
        self.assertEqual(self.serial.sent,["0 STOP"])
        self.assertFalse(self.serial.is_open)

    def test_cancelled_hold_can_still_release(self):
        self.mouse.press("left")
        def cancelled(): raise RuntimeError("cancelled")
        self.mouse.checkpoint=cancelled
        self.mouse.release("left")
        self.assertEqual(self.serial.sent,["1 ARM","2 PRESS 1","3 RELEASE 1"])

    def test_keep_alive_refreshes_hold_watchdog(self):
        self.mouse.keep_alive()
        self.mouse.keep_alive()
        self.assertEqual(self.serial.sent,["1 ARM"])

    def test_handshake_requires_protocol_two(self):
        self.mouse._request("HELLO",handshake=True)
        self.assertEqual(self.serial.sent,["1 HELLO"])

    def test_no_move_if_already_on_target(self):
        self.mouse.move(10,10)
        self.assertEqual(self.serial.sent,[])

    def test_move_fails_if_cursor_cannot_converge(self):
        with patch("arcmouse.hardware.time.sleep"):
            with self.assertRaisesRegex(OSError,"수렴"):
                self.mouse.move(100,100)
        self.assertEqual(len(self.serial.sent),200)


if __name__=="__main__": unittest.main()
