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
    def test_abi_sizes(self):
        from arcmouse import win32
        x64 = ctypes.sizeof(ctypes.c_void_p) == 8
        self.assertEqual(ctypes.sizeof(win32.INPUT),40 if x64 else 28)
        self.assertEqual(ctypes.sizeof(win32.EXTENDED_LIMIT),144 if x64 else 112)

    def test_hotkey_rebind_rolls_back_on_conflict(self):
        from arcmouse import win32
        monitor=win32.HotkeyMonitor.__new__(win32.HotkeyMonitor)
        monitor.hwnd=42;monitor.bindings={(0,117):10,(0,118):11};monitor.roles={10:'start',11:'stop'};monitor.next_id=12
        with patch.object(win32.user,'RegisterHotKey',side_effect=[True,False]), patch.object(win32.user,'UnregisterHotKey') as unregister:
            with self.assertRaises(OSError):monitor.configure('F8','F9')
            unregister.assert_called_once_with(42,12)
        self.assertEqual(monitor.bindings,{(0,117):10,(0,118):11})
        self.assertEqual(monitor.roles,{10:'start',11:'stop'})

    def test_hotkey_role_swap_preserves_registrations(self):
        from arcmouse import win32
        monitor=win32.HotkeyMonitor.__new__(win32.HotkeyMonitor)
        monitor.hwnd=42;monitor.bindings={(0,117):10,(0,118):11};monitor.roles={};monitor.next_id=12
        with patch.object(win32.user,'RegisterHotKey') as register,patch.object(win32.user,'UnregisterHotKey') as unregister:
            self.assertEqual(monitor.configure('F7','F6'),('F7','F6'))
            register.assert_not_called();unregister.assert_not_called()
        self.assertEqual(monitor.roles[11],'start');self.assertEqual(monitor.roles[10],'stop')

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
