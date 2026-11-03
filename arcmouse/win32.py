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


class RAWDEVICE(C.Structure):
    _fields_ = [("usagePage", W.USHORT), ("usage", W.USHORT),
                ("flags", W.DWORD), ("target", W.HWND)]


class RAWDEVLIST(C.Structure):
    _fields_ = [("handle", W.HANDLE), ("kind", W.DWORD)]


class RAWHEADER(C.Structure):
    _fields_ = [("kind", W.DWORD), ("size", W.DWORD), ("device", W.HANDLE), ("param", W.WPARAM)]


class RAWMOUSE(C.Structure):
    _fields_ = [("flags", W.USHORT), ("buttons", W.ULONG), ("rawButtons", W.ULONG),
                ("dx", W.LONG), ("dy", W.LONG), ("extra", W.ULONG)]


class RAWKEYBOARD(C.Structure):
    _fields_ = [("makeCode", W.USHORT), ("flags", W.USHORT), ("reserved", W.USHORT),
                ("vkey", W.USHORT), ("message", W.UINT), ("extra", W.ULONG)]


bind(user, "EnumWindows", W.BOOL, ENUMPROC, W.LPARAM)
bind(user, "IsWindow", W.BOOL, W.HWND)
bind(user, "IsWindowVisible", W.BOOL, W.HWND)
bind(user, "IsIconic", W.BOOL, W.HWND)
bind(user, "GetWindowTextW", C.c_int, W.HWND, W.LPWSTR, C.c_int)
bind(user, "GetWindowThreadProcessId", W.DWORD, W.HWND, C.POINTER(W.DWORD))
bind(user, "GetClientRect", W.BOOL, W.HWND, C.POINTER(W.RECT))
bind(user, "ClientToScreen", W.BOOL, W.HWND, C.POINTER(W.POINT))
bind(user, "GetDpiForWindow", W.UINT, W.HWND)
bind(user, "GetForegroundWindow", W.HWND)
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
bind(user, "RegisterRawInputDevices", W.BOOL, C.POINTER(RAWDEVICE), W.UINT, W.UINT)
bind(user, "GetRawInputData", W.UINT, W.HANDLE, W.UINT, W.LPVOID, C.POINTER(W.UINT), W.UINT)
bind(user, "GetRawInputDeviceList", W.UINT, C.POINTER(RAWDEVLIST), C.POINTER(W.UINT), W.UINT)
bind(user, "GetRawInputDeviceInfoW", W.UINT, W.HANDLE, W.UINT, W.LPVOID, C.POINTER(W.UINT))
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


def creation_time(handle):
    a, b, c, d = W.FILETIME(), W.FILETIME(), W.FILETIME(), W.FILETIME()
    if not kernel.GetProcessTimes(handle, C.byref(a), C.byref(b), C.byref(c), C.byref(d)):
        raise OSError("프로세스 생성 시각을 확인할 수 없습니다.")
    return (a.dwHighDateTime << 32) | a.dwLowDateTime


def identity(hwnd):
    pid = W.DWORD()
    user.GetWindowThreadProcessId(hwnd, C.byref(pid))
    handle = kernel.OpenProcess(0x100000 | 0x1000, False, pid.value)
    if not handle:
        raise OSError("대상 프로세스를 열 수 없습니다.")
    try:
        return {"hwnd": int(hwnd), "pid": pid.value, "created": creation_time(handle)}
    finally:
        kernel.CloseHandle(handle)


def windows():
    found = []

    @ENUMPROC
    def callback(hwnd, _):
        title = C.create_unicode_buffer(512)
        user.GetWindowTextW(hwnd, title, len(title))
        if user.IsWindowVisible(hwnd) and title.value:
            try:
                item = identity(hwnd)
                if item["pid"] != os.getpid():
                    item["title"] = title.value
                    found.append(item)
            except OSError:
                pass
        return True

    user.EnumWindows(callback, 0)
    return found


def cursor():
    point = W.POINT()
    if not user.GetCursorPos(C.byref(point)):
        raise OSError("커서 위치를 읽을 수 없습니다.")
    return point.x, point.y


class TargetGuard:
    def __init__(self, target):
        self.hwnd, self.pid = target["hwnd"], target["pid"]
        self.handle = kernel.OpenProcess(0x100000 | 0x1000, False, self.pid)
        if not self.handle:
            raise OSError("대상 프로세스가 종료되었습니다.")
        if creation_time(self.handle) != target["created"]:
            self.close()
            raise OSError("대상 프로세스 ID가 재사용되었습니다.")

    def check(self, foreground=True):
        pid = W.DWORD()
        user.GetWindowThreadProcessId(self.hwnd, C.byref(pid))
        if (not user.IsWindow(self.hwnd) or pid.value != self.pid or
                kernel.WaitForSingleObject(self.handle, 0) != 258 or
                user.IsIconic(self.hwnd) or not user.IsWindowVisible(self.hwnd)):
            raise OSError("대상 창이 사라졌거나 최소화되었습니다. 입력을 중단했습니다.")
        if foreground and user.GetForegroundWindow() != self.hwnd:
            raise OSError("대상 창이 포커스를 잃었습니다. 입력을 중단했습니다.")

    def geometry(self):
        self.check()
        rect, origin = W.RECT(), W.POINT()
        if not user.GetClientRect(self.hwnd, C.byref(rect)) or not user.ClientToScreen(self.hwnd, C.byref(origin)):
            raise OSError("대상 창 좌표를 읽을 수 없습니다.")
        return origin.x, origin.y, rect.right, rect.bottom, (user.GetDpiForWindow(self.hwnd) or 96) / 96

    def resolve(self, x, y, mode="dip"):
        ox, oy, width, height, scale = self.geometry()
        if mode == "dip":
            px, py = round(x * scale), round(y * scale)
        elif mode == "ratio":
            px, py = round(x * (width - 1)), round(y * (height - 1))
        else:
            raise ValueError("알 수 없는 좌표 모드")
        if not (0 <= px < width and 0 <= py < height):
            raise OSError("좌표가 대상 창의 클라이언트 영역을 벗어났습니다.")
        return ox + px, oy + py

    def check_point(self, point):
        ox, oy, width, height, _ = self.geometry()
        x, y = point
        if not (ox <= x < ox + width and oy <= y < oy + height):
            raise OSError("커서가 대상 창 밖에 있어 클릭을 중단했습니다.")
        hit = user.WindowFromPoint(W.POINT(int(x), int(y)))
        if user.GetAncestor(hit, 2) != self.hwnd:
            raise OSError("다른 창이 클릭 위치를 가리고 있어 중단했습니다.")

    def close(self):
        if self.handle:
            kernel.CloseHandle(self.handle)
            self.handle = None


def mouse_input(flags, x=0, y=0):
    return INPUT(type=0, mi=MOUSEINPUT(x, y, 0, flags, 0, MARKER))


def send_inputs(*items):
    array = (INPUT * len(items))(*items)
    if user.SendInput(len(items), array, C.sizeof(INPUT)) != len(items):
        raise OSError("Windows가 입력을 차단했습니다. 대상 앱의 권한을 확인하세요.")


class SoftwareMouse:
    def move(self, x, y):
        left, top = user.GetSystemMetrics(76), user.GetSystemMetrics(77)
        width, height = user.GetSystemMetrics(78), user.GetSystemMetrics(79)
        ax = round((x - left) * 65535 / max(1, width - 1))
        ay = round((y - top) * 65535 / max(1, height - 1))
        if not (0 <= ax <= 65535 and 0 <= ay <= 65535):
            raise OSError("가상 디스플레이 밖의 좌표입니다.")
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

    def close(self):
        pass


def device_name(handle):
    size = W.UINT()
    user.GetRawInputDeviceInfoW(handle, 0x20000007, None, C.byref(size))
    if not size.value:
        return ""
    buf = C.create_unicode_buffer(size.value + 1)
    if user.GetRawInputDeviceInfoW(handle, 0x20000007, buf, C.byref(size)) == 0xFFFFFFFF:
        return ""
    return buf.value


def mouse_devices():
    count = W.UINT()
    if user.GetRawInputDeviceList(None, C.byref(count), C.sizeof(RAWDEVLIST)) == 0xFFFFFFFF:
        raise C.WinError(C.get_last_error())
    array = (RAWDEVLIST * count.value)()
    n = user.GetRawInputDeviceList(array, C.byref(count), C.sizeof(RAWDEVLIST))
    if n == 0xFFFFFFFF:
        raise C.WinError(C.get_last_error())
    return [device_name(d.handle) for d in array[:n] if d.kind == 0]


class InputMonitor:
    """Physical input delivered to an independent process, including while UI hangs."""
    def __init__(self, pause_until, threshold=3):
        self.pause_until, self.threshold = pause_until, threshold
        self.excluded_device = ""
        self.kill_requested = False
        self.input_error = None
        self.distance, self.last_motion = 0, 0
        self.names = {}
        self.proc = WNDPROC(self._proc)
        self.class_name = f"ArcMouseSafety{os.getpid()}"
        wc = WNDCLASS(lpfnWndProc=self.proc, hInstance=kernel.GetModuleHandleW(None), lpszClassName=self.class_name)
        if not user.RegisterClassW(C.byref(wc)):
            raise C.WinError(C.get_last_error())
        self.hwnd = user.CreateWindowExW(0, self.class_name, "", 0, 0, 0, 0, 0,
                                          W.HWND(-3), None, wc.hInstance, None)
        if not self.hwnd:
            raise C.WinError(C.get_last_error())
        devices = (RAWDEVICE * 2)(RAWDEVICE(1, 2, 0x2100, self.hwnd), RAWDEVICE(1, 6, 0x2100, self.hwnd))
        if not user.RegisterRawInputDevices(devices, 2, C.sizeof(RAWDEVICE)):
            raise C.WinError(C.get_last_error())
        if not user.RegisterHotKey(self.hwnd, 1, 0x4000 | 1 | 2 | 4, ord("K")):
            raise OSError("Ctrl+Alt+Shift+K를 등록할 수 없습니다. 다른 앱의 단축키 설정을 확인하세요.")

    def _proc(self, hwnd, msg, wp, lp):
        try:
            if msg == 0x312:
                self.kill_requested = True
            elif msg == 0xFE:  # WM_INPUT_DEVICE_CHANGE
                self.names.clear()
                if wp == 2 and self.excluded_device and self.excluded_device not in mouse_devices():
                    self.input_error = "선택한 MCU HID 장치 연결이 끊겼습니다."
            elif msg == 0xFF:
                size = W.UINT()
                header_size = C.sizeof(RAWHEADER)
                if user.GetRawInputData(lp, 0x10000003, None, C.byref(size), header_size) == 0xFFFFFFFF:
                    raise OSError("Raw Input 크기 조회 실패")
                buf = C.create_string_buffer(size.value)
                if user.GetRawInputData(lp, 0x10000003, buf, C.byref(size), header_size) == 0xFFFFFFFF:
                    raise OSError("Raw Input 읽기 실패")
                header = RAWHEADER.from_buffer(buf)
                now = time.monotonic()
                if header.kind == 1:
                    key = RAWKEYBOARD.from_buffer(buf, header_size)
                    if key.vkey == 0x7B and not key.flags & 1:
                        self.kill_requested = True  # F12 is supplementary, not RegisterHotKey.
                    self.pause_until.value = now + 0.5
                elif header.kind == 0:
                    if header.device not in self.names:
                        self.names[header.device] = device_name(header.device)
                    name = self.names[header.device]
                    if self.excluded_device and name == self.excluded_device:
                        return user.DefWindowProcW(hwnd, msg, wp, lp)
                    mouse = RAWMOUSE.from_buffer(buf, header_size)
                    if now - self.last_motion > 0.15:
                        self.distance = 0
                    self.last_motion = now
                    self.distance += abs(mouse.dx) + abs(mouse.dy)
                    if mouse.buttons or self.distance >= self.threshold:
                        self.pause_until.value = now + 0.5
                        self.distance = 0
        except Exception as exc:
            self.input_error = str(exc)
        return user.DefWindowProcW(hwnd, msg, wp, lp)

    def pump(self):
        msg = W.MSG()
        # Bound work so a device flooding messages cannot starve the kill check.
        for _ in range(256):
            if not user.PeekMessageW(C.byref(msg), None, 0, 0, 1):
                break
            user.TranslateMessage(C.byref(msg))
            user.DispatchMessageW(C.byref(msg))

    def close(self):
        user.UnregisterHotKey(self.hwnd, 1)
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
            raise OSError("실행 프로세스의 종료 보호(Job Object)를 설정할 수 없습니다.")

    def close(self):
        if self.handle:
            kernel.CloseHandle(self.handle)
            self.handle = None
