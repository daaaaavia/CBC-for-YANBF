"""Accept files dragged from Explorer / Finder onto a Tk window.

Windows (ctypes, no extra packages) uses the classic WM_DROPFILES mechanism: DragAcceptFiles on the top-level
window, whose window procedure is subclassed to catch the drop. Windows
delivers drops over child widgets to the nearest ancestor that accepts files,
so one registration covers the whole window. The callback receives the
dropped paths and the drop point in screen coordinates; it runs inside the
window procedure, so it should only queue work for the Tk loop.

macOS (and Linux) use tkdnd through the tkinterdnd2 package, registered on the
top-level window too; tkdnd passes a drop over a child widget up to it. The
callback gets the same arguments. If tkinterdnd2 isn't installed, or has no tkdnd
build for this Mac (it has none for Intel Macs with Tk 9), drag and drop is simply
off (enabled stays False) and Browse still works.
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

if sys.platform == "win32":
    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
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
            self._enable_tkdnd(toplevel)
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

    def _enable_tkdnd(self, toplevel):
        try:
            from tkinterdnd2 import TkinterDnD
            TkinterDnD._require(toplevel)
            toplevel.tk.call("tkdnd::drop_target", "register", toplevel, ("DND_Files",))
        except Exception:
            return
        cmd = toplevel.register(lambda data, x, y: self._on_tkdnd_drop(toplevel, data, x, y))
        toplevel.tk.call("bind", toplevel, "<<Drop:DND_Files>>", f"{cmd} %D %X %Y")
        self.enabled = True

    def _on_tkdnd_drop(self, toplevel, data, x, y):
        try:
            self.callback(list(toplevel.tk.splitlist(data)), int(x), int(y))
        except Exception:
            pass
        return "copy"  # tells the source the drop was accepted
