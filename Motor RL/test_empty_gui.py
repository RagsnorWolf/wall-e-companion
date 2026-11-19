"""Captura una GUI de PyBullet vacia para ver si el demo por defecto agrega objetos."""

from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes

import numpy as np
import pybullet as p
from PIL import Image

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32


def find_window_by_pid(pid: int):
    found = None

    def cb(hwnd, _):
        nonlocal found
        n = user32.GetWindowTextLengthW(hwnd)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if "ExampleBrowser" in buf.value or "Bullet" in buf.value:
                wpid = ctypes.c_ulong()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
                if wpid.value == pid:
                    found = hwnd
        return True

    proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    user32.EnumWindows(proc(cb), 0)
    return found


def capture(hwnd, out_path: str) -> bool:
    rect = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    dc = user32.GetWindowDC(hwnd)
    mem = gdi32.CreateCompatibleDC(dc)
    bmp = gdi32.CreateCompatibleBitmap(dc, w, h)
    gdi32.SelectObject(mem, bmp)
    ok = user32.PrintWindow(hwnd, mem, 3)

    class BMIH(ctypes.Structure):
        _fields_ = [
            ("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
            ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
            ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
            ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
            ("biYPelsPerMeter", ctypes.c_int32), ("biClrUsed", ctypes.c_uint32),
            ("biClrImportant", ctypes.c_uint32),
        ]

    bmi = BMIH()
    bmi.biSize = ctypes.sizeof(BMIH)
    bmi.biWidth = w
    bmi.biHeight = -h
    bmi.biPlanes = 1
    bmi.biBitCount = 32
    bmi.biCompression = 0
    buf = ctypes.create_string_buffer(w * h * 4)
    lines = gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bmi), 0)
    print("PrintWindow:", ok, "lineas:", lines)
    img = Image.frombuffer("RGBA", (w, h), buf.raw, "raw", "BGRA").convert("RGB")
    img.save(out_path)
    print("guardado:", out_path)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(hwnd, dc)
    return bool(ok)


def main() -> None:
    p.connect(p.GUI, options="--opengl2")
    print("conectado, esperando 4 s...")
    time.sleep(4.0)
    hwnd = find_window_by_pid(os.getpid())
    print("hwnd propio:", hwnd)
    if hwnd:
        out = str(
            (__file__.replace("\\", "/").rsplit("/", 1)[0])
            + "/models/_empty_gui.png"
        )
        capture(hwnd, out)
    p.disconnect()


if __name__ == "__main__":
    main()
