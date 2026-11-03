"""Typed Win32 boundary. Import only on Windows."""
from __future__ import annotations

import ctypes as C
from ctypes import wintypes as W
import os
import time

user = C.WinDLL("user32", use_last_error=True)
kernel = C.WinDLL("kernel32", use_last_error=True)
ULONG_PTR = C.c_size_t
LRESULT = C.c_ssize_t
WNDPROC = C.WINFUNCTYPE(LRESULT, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
ENUMPROC = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
MARKER = 0x4152434D


def bind(dll, name, restype, *args):
    fn = getattr(dll, name)
    fn.restype, fn.argtypes = restype, list(args)
    return fn


class MOUSEINPUT(C.Structure):
    _fields_ = [("dx", W.LONG), ("dy", W.LONG), ("mouseData", W.DWORD),
                ("dwFlags", W.DWORD), ("time", W.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(C.Structure):
    _fields_ = [("wVk", W.WORD), ("wScan", W.WORD), ("dwFlags", W.DWORD),
                ("time", W.DWORD), ("dwExtraInfo", ULONG_PTR)]


class INPUTUNION(C.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(C.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", W.DWORD), ("u", INPUTUNION)]


class WNDCLASS(C.Structure):
    _fields_ = [("style", W.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", C.c_int),
                ("cbWndExtra", C.c_int), ("hInstance", W.HINSTANCE), ("hIcon", W.HICON),
                ("hCursor", W.HANDLE), ("hbrBackground", W.HBRUSH),
                ("lpszMenuName", W.LPCWSTR), ("lpszClassName", W.LPCWSTR)]


bind(user, "IsWindow", W.BOOL, W.HWND)
bind(user, "IsWindowVisible", W.BOOL, W.HWND)
bind(user, "IsIconic", W.BOOL, W.HWND)
bind(user, "GetWindowTextW", C.c_int, W.HWND, W.LPWSTR, C.c_int)
bind(user, "GetWindowThreadProcessId", W.DWORD, W.HWND, C.POINTER(W.DWORD))
bind(user, "GetClientRect", W.BOOL, W.HWND, C.POINTER(W.RECT))
bind(user, "ClientToScreen", W.BOOL, W.HWND, C.POINTER(W.POINT))
bind(user, "GetDpiForWindow", W.UINT, W.HWND)
bind(user, "GetForegroundWindow", W.HWND)
bind(user, "GetClassNameW", C.c_int, W.HWND, W.LPWSTR, C.c_int)
bind(user, "GetAncestor", W.HWND, W.HWND, W.UINT)
bind(user, "WindowFromPoint", W.HWND, W.POINT)
bind(user, "GetCursorPos", W.BOOL, C.POINTER(W.POINT))
bind(user, "GetSystemMetrics", C.c_int, C.c_int)
bind(user, "SendInput", W.UINT, W.UINT, C.POINTER(INPUT), C.c_int)
bind(user, "SetProcessDpiAwarenessContext", W.BOOL, W.HANDLE)
bind(user, "RegisterHotKey", W.BOOL, W.HWND, C.c_int, W.UINT, W.UINT)
bind(user, "UnregisterHotKey", W.BOOL, W.HWND, C.c_int)
bind(user, "RegisterClassW", W.ATOM, C.POINTER(WNDCLASS))
bind(user, "CreateWindowExW", W.HWND, W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD,
     C.c_int, C.c_int, C.c_int, C.c_int, W.HWND, W.HMENU, W.HINSTANCE, W.LPVOID)
bind(user, "DefWindowProcW", LRESULT, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
bind(user, "DestroyWindow", W.BOOL, W.HWND)
bind(user, "PeekMessageW", W.BOOL, C.POINTER(W.MSG), W.HWND, W.UINT, W.UINT, W.UINT)
bind(user, "TranslateMessage", W.BOOL, C.POINTER(W.MSG))
bind(user, "DispatchMessageW", LRESULT, C.POINTER(W.MSG))
bind(kernel, "OpenProcess", W.HANDLE, W.DWORD, W.BOOL, W.DWORD)
bind(kernel, "CloseHandle", W.BOOL, W.HANDLE)
bind(kernel, "GetProcessTimes", W.BOOL, W.HANDLE, C.POINTER(W.FILETIME), C.POINTER(W.FILETIME),
     C.POINTER(W.FILETIME), C.POINTER(W.FILETIME))
bind(kernel, "WaitForSingleObject", W.DWORD, W.HANDLE, W.DWORD)
bind(kernel, "GetModuleHandleW", W.HMODULE, W.LPCWSTR)
bind(kernel, "CreateJobObjectW", W.HANDLE, W.LPVOID, W.LPCWSTR)
bind(kernel, "SetInformationJobObject", W.BOOL, W.HANDLE, C.c_int, W.LPVOID, W.DWORD)
bind(kernel, "AssignProcessToJobObject", W.BOOL, W.HANDLE, W.HANDLE)


def dpi_aware():
    user.SetProcessDpiAwarenessContext(W.HANDLE(-4))  # Per monitor v2, before creating any HWND.


def cursor():
    point = W.POINT()
    if not user.GetCursorPos(C.byref(point)):
        raise OSError("Cannot read the cursor position.")
    return point.x, point.y


def mouse_input(flags, x=0, y=0):
    return INPUT(type=0, mi=MOUSEINPUT(x, y, 0, flags, 0, MARKER))


def send_inputs(*items):
    array = (INPUT * len(items))(*items)
    if user.SendInput(len(items), array, C.sizeof(INPUT)) != len(items):
        raise OSError("Windows blocked input. Check the receiving app's permissions.")


class SoftwareMouse:
    def move(self, x, y):
        left, top = user.GetSystemMetrics(76), user.GetSystemMetrics(77)
        width, height = user.GetSystemMetrics(78), user.GetSystemMetrics(79)
        ax = round((x - left) * 65535 / max(1, width - 1))
        ay = round((y - top) * 65535 / max(1, height - 1))
        if not (0 <= ax <= 65535 and 0 <= ay <= 65535):
            raise OSError("The coordinates are outside the virtual desktop.")
        send_inputs(mouse_input(0x8000 | 0x4000 | 0x0001, ax, ay))

    def click(self, button):
        down, up = {"left": (2, 4), "right": (8, 16), "middle": (32, 64)}[button]
        # One atomic batch: no cancellable sleep between down and up.
        try:
            send_inputs(mouse_input(down), mouse_input(up))
        except OSError:
            # Best-effort release if Windows reports a partially inserted batch.
            releases = (INPUT * 3)(mouse_input(4),mouse_input(16),mouse_input(64))
            user.SendInput(3,releases,C.sizeof(INPUT))
            raise

    def press(self,button):
        send_inputs(mouse_input({"left":2,"right":8,"middle":32}[button]))

    def release(self,button):
        send_inputs(mouse_input({"left":4,"right":16,"middle":64}[button]))

    def release_all(self):
        release_buttons(7)

    def keep_alive(self):
        pass

    def close(self):
        pass


def release_buttons(mask):
    inputs=[mouse_input(flag) for bit,flag in ((1,4),(2,16),(4,64)) if mask&bit]
    if inputs: send_inputs(*inputs)


def screen_bounds():
    return tuple(user.GetSystemMetrics(n) for n in (76,77,78,79))


def check_screen_point(x,y):
    left,top,width,height=screen_bounds()
    if not (left<=x<left+width and top<=y<top+height):
        raise OSError("A saved point is outside the current screen. Pick that point again.")


class HotkeyMonitor:
    """Message-only HWND. Rebinding is transactional and does not watch the mouse."""
    def __init__(self):
        self.requests=[]
        self.bindings={}
        self.roles={1:"stop"}
        self.next_id=10
        self.proc=WNDPROC(self._proc)
        self.class_name=f"ArcMouseHotkeys{os.getpid()}_{id(self)}"
        wc=WNDCLASS(lpfnWndProc=self.proc,hInstance=kernel.GetModuleHandleW(None),lpszClassName=self.class_name)
        if not user.RegisterClassW(C.byref(wc)): raise C.WinError(C.get_last_error())
        self.hwnd=user.CreateWindowExW(0,self.class_name,"",0,0,0,0,0,W.HWND(-3),None,wc.hInstance,None)
        if not self.hwnd: raise C.WinError(C.get_last_error())
        self.emergency=bool(user.RegisterHotKey(self.hwnd,1,0x4000|1|2|4,ord("K")))

    def configure(self,start,stop):
        from .model import hotkey_pair
        a,b=hotkey_pair(start,stop)
        next_bindings={}
        newly_registered=[]
        try:
            for flags,vk,name in (a,b):
                key=(flags,vk)
                if key in self.bindings:
                    next_bindings[key]=self.bindings[key]
                    continue
                identifier=self.next_id
                self.next_id+=1
                if not user.RegisterHotKey(self.hwnd,identifier,flags|0x4000,vk):
                    error=C.get_last_error()
                    if error==1409:
                        raise OSError(f"{name} is already used by another app. Choose another hotkey.")
                    raise OSError(f"Cannot register {name} (Windows error {error}). Check input permissions in this environment.")
                next_bindings[key]=identifier
                newly_registered.append(identifier)
        except Exception:
            for identifier in newly_registered: user.UnregisterHotKey(self.hwnd,identifier)
            raise
        for key,identifier in self.bindings.items():
            if key not in next_bindings: user.UnregisterHotKey(self.hwnd,identifier)
        self.bindings=next_bindings
        self.roles={1:"stop",next_bindings[a[:2]]:"start",next_bindings[b[:2]]:"stop"}
        return a[2],b[2]

    def _proc(self,hwnd,msg,wp,lp):
        if msg==0x312 and wp in self.roles:
            self.requests.append(self.roles[wp])
        return user.DefWindowProcW(hwnd,msg,wp,lp)

    def pump(self):
        msg=W.MSG()
        for _ in range(256):
            if not user.PeekMessageW(C.byref(msg),None,0,0,1): break
            user.TranslateMessage(C.byref(msg))
            user.DispatchMessageW(C.byref(msg))

    def close(self):
        for identifier in (1,*self.bindings.values()): user.UnregisterHotKey(self.hwnd,identifier)
        user.DestroyWindow(self.hwnd)


class BASIC_LIMIT(C.Structure):
    _fields_ = [("perProcess", C.c_int64), ("perJob", C.c_int64), ("flags", W.DWORD),
                ("minWS", C.c_size_t), ("maxWS", C.c_size_t), ("active", W.DWORD),
                ("affinity", ULONG_PTR), ("priority", W.DWORD), ("scheduling", W.DWORD)]


class IO_COUNTERS(C.Structure):
    _fields_ = [(name, C.c_uint64) for name in ("r", "w", "o", "rb", "wb", "ob")]


class EXTENDED_LIMIT(C.Structure):
    _fields_ = [("basic", BASIC_LIMIT), ("io", IO_COUNTERS), ("processMemory", C.c_size_t),
                ("jobMemory", C.c_size_t), ("peakProcess", C.c_size_t), ("peakJob", C.c_size_t)]


class KillJob:
    def __init__(self, process_handle):
        self.handle = kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise C.WinError(C.get_last_error())
        limits = EXTENDED_LIMIT()
        limits.basic.flags = 0x2000  # KILL_ON_JOB_CLOSE; applies to child processes too.
        if (not kernel.SetInformationJobObject(self.handle, 9, C.byref(limits), C.sizeof(limits)) or
                not kernel.AssignProcessToJobObject(self.handle, int(process_handle))):
            self.close()
            raise OSError("Cannot configure process termination protection (Windows Job Object).")

    def close(self):
        if self.handle:
            kernel.CloseHandle(self.handle)
            self.handle = None
