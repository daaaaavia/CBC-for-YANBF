"""Accept files dragged from Explorer onto a Tk window (Windows only, ctypes).

Uses the classic WM_DROPFILES mechanism: DragAcceptFiles on the top-level
window, whose window procedure is subclassed to catch the drop. Windows
delivers drops over child widgets to the nearest ancestor that accepts files,
so one registration covers the whole window. The callback receives the
dropped paths and the drop point in screen coordinates; it runs inside the
window procedure, so it should only queue work for the Tk loop.
"""

import ctypes
import sys
from ctypes import wintypes

WM_DROPFILES = 0x0233
WM_COPYDATA = 0x004A
WM_COPYGLOBALDATA = 0x0049
MSGFLT_ALLOW = 1
GWLP_WNDPROC = -4

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

if sys.platform == "win32":
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _shell32 = ctypes.WinDLL("shell32", use_last_error=True)

    _user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
    _user32.SetWindowLongPtrW.restype = ctypes.c_void_p
    _user32.CallWindowProcW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT,
                                        wintypes.WPARAM, wintypes.LPARAM]
    _user32.CallWindowProcW.restype = LRESULT
    _user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    _user32.ChangeWindowMessageFilterEx.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.DWORD, ctypes.c_void_p]
    _shell32.DragAcceptFiles.argtypes = [wintypes.HWND, wintypes.BOOL]
    _shell32.DragQueryFileW.argtypes = [ctypes.c_void_p, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]
    _shell32.DragQueryFileW.restype = wintypes.UINT
    _shell32.DragQueryPoint.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.POINT)]
    _shell32.DragFinish.argtypes = [ctypes.c_void_p]


class FileDropTarget:
    """Make a Tk toplevel accept dropped files. callback(paths, x_root, y_root)."""

    def __init__(self, toplevel, callback):
        self.callback = callback
        self.enabled = False
        if sys.platform != "win32":
            return
        toplevel.update_idletasks()
        self.hwnd = int(toplevel.wm_frame(), 16)
        self._proc = WNDPROC(self._wndproc)  # keep a reference: Windows calls it
        self._old = _user32.SetWindowLongPtrW(self.hwnd, GWLP_WNDPROC,
                                              ctypes.cast(self._proc, ctypes.c_void_p).value)
        # let drops through even if this process runs elevated (UIPI)
        for msg in (WM_DROPFILES, WM_COPYDATA, WM_COPYGLOBALDATA):
            _user32.ChangeWindowMessageFilterEx(self.hwnd, msg, MSGFLT_ALLOW, None)
        _shell32.DragAcceptFiles(self.hwnd, True)
        self.enabled = True

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == WM_DROPFILES:
            try:
                hdrop = ctypes.c_void_p(wparam)
                count = _shell32.DragQueryFileW(hdrop, 0xFFFFFFFF, None, 0)
                paths = []
                for i in range(count):
                    n = _shell32.DragQueryFileW(hdrop, i, None, 0)
                    buf = ctypes.create_unicode_buffer(n + 1)
                    _shell32.DragQueryFileW(hdrop, i, buf, n + 1)
                    paths.append(buf.value)
                pt = wintypes.POINT()
                _shell32.DragQueryPoint(hdrop, ctypes.byref(pt))
                _user32.ClientToScreen(hwnd, ctypes.byref(pt))
                _shell32.DragFinish(hdrop)
                self.callback(paths, pt.x, pt.y)
            except Exception:
                pass  # never let an exception escape a window procedure
            return 0
        return _user32.CallWindowProcW(self._old, hwnd, msg, wparam, lparam)
