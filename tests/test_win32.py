"""Windows ABI and native process containment. Never injects desktop input."""
import ctypes
import multiprocessing as mp
import sys
import time
import unittest
from unittest.mock import patch


def idle_child(ready):
    ready.set()
    time.sleep(30)


@unittest.skipUnless(sys.platform == "win32", "Windows native boundary")
class Win32Tests(unittest.TestCase):
    def test_auto_target_captures_foreground_identity(self):
        from arcmouse import win32
        expected={"hwnd":42,"pid":200,"created":123}
        with patch.object(win32.user,"GetForegroundWindow",return_value=42), \
             patch.object(win32,"desktop_window",return_value=False), \
             patch.object(win32,"identity",return_value=expected):
            self.assertEqual(win32.foreground_target(100),expected)

    def test_auto_target_rejects_own_app(self):
        from arcmouse import win32
        with patch.object(win32.user,"GetForegroundWindow",return_value=42), \
             patch.object(win32,"desktop_window",return_value=False), \
             patch.object(win32,"identity",return_value={"hwnd":42,"pid":100,"created":123}):
            with self.assertRaisesRegex(OSError,"전환"):
                win32.foreground_target(100)

    def test_auto_target_rejects_desktop(self):
        from arcmouse import win32
        with patch.object(win32.user,"GetForegroundWindow",return_value=42), \
             patch.object(win32,"desktop_window",return_value=True):
            with self.assertRaisesRegex(OSError,"바탕화면"):
                win32.foreground_target(100)

    def test_abi_sizes(self):
        from arcmouse import win32
        x64 = ctypes.sizeof(ctypes.c_void_p) == 8
        self.assertEqual(ctypes.sizeof(win32.INPUT),40 if x64 else 28)
        self.assertEqual(ctypes.sizeof(win32.RAWHEADER),24 if x64 else 16)
        self.assertEqual(ctypes.sizeof(win32.RAWMOUSE),24)
        self.assertEqual(ctypes.sizeof(win32.RAWKEYBOARD),16)
        self.assertEqual(ctypes.sizeof(win32.EXTENDED_LIMIT),144 if x64 else 112)

    def test_job_close_terminates_uncooperative_worker(self):
        from arcmouse.win32 import KillJob
        ctx=mp.get_context("spawn")
        ready=ctx.Event()
        child=ctx.Process(target=idle_child,args=(ready,))
        child.start()
        job=None
        try:
            self.assertTrue(ready.wait(5))
            job=KillJob(child.sentinel)
            start=time.monotonic()
            job.close()
            child.join(2)
            self.assertFalse(child.is_alive())
            self.assertLess(time.monotonic()-start,2)
        finally:
            if job: job.close()
            if child.is_alive():
                child.terminate()
                child.join(2)
            child.close()


if __name__=="__main__": unittest.main()
