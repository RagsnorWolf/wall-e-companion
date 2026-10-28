"""Reflejos visuales: detección de color con OpenCV.

Esto NO es el cerebro. Es el reflejo rápido que corre sin LLM, para latencia
cero. El cerebro puede pedirle una medición puntual como herramienta.

La cámara puede ser la del celular (0 por defecto), una webcam USB o un stream.
"""

from __future__ import annotations

import threading
import time
from typing import Any

try:
    import cv2
    import numpy as np
except ImportError:  # pragma: no cover
    cv2 = None
    np = None

# Rangos HSV por color. El rojo necesita dos franjas por el wrap del matiz.
COLOR_RANGES: dict[str, list[tuple[tuple[int, int, int], tuple[int, int, int]]]] = {
    "rojo": [((0, 120, 70), (10, 255, 255)), ((170, 120, 70), (180, 255, 255))],
    "verde": [((35, 80, 50), (85, 255, 255))],
    "azul": [((90, 80, 50), (130, 255, 255))],
    "amarillo": [((20, 100, 100), (35, 255, 255))],
    "naranja": [((10, 120, 90), (20, 255, 255))],
}

MIN_AREA = 400


class Camera:
    """Wrapper con apertura perezosa. Si no hay cámara, lo dice y no explota."""

    def __init__(self, index: int = 0, width: int = 320, height: int = 240) -> None:
        self.index = index
        self.width = width
        self.height = height
        self._cap = None
        self._lock = threading.Lock()

    def read(self):
        if cv2 is None:
            return None
        with self._lock:
            if self._cap is None:
                cap = cv2.VideoCapture(self.index)
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                if not cap.isOpened():
                    cap.release()
                    return None
                self._cap = cap
            ok, frame = self._cap.read()
            return frame if ok else None

    def close(self) -> None:
        with self._lock:
            if self._cap is not None:
                self._cap.release()
                self._cap = None


def probe_color(camera: Camera, color: str = "rojo", samples: int = 8) -> dict[str, Any]:
    """Saca varias fotos y devuelve dónde está el color, si está."""
    if cv2 is None:
        return {"ok": False, "error": "OpenCV no instalado", "found": False}

    ranges = COLOR_RANGES.get(color.lower())
    if not ranges:
        return {
            "ok": False,
            "error": f"color desconocido: {color}",
            "valid_colors": list(COLOR_RANGES),
            "found": False,
        }

    best: dict[str, Any] = {"found": False, "area": 0.0}
    seen_any_frame = False

    for _ in range(max(1, samples)):
        frame = camera.read()
        if frame is None:
            time.sleep(0.05)
            continue
        seen_any_frame = True

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = None
        for low, high in ranges:
            band = cv2.inRange(hsv, np.array(low), np.array(high))
            mask = band if mask is None else cv2.bitwise_or(mask, band)

        mask = cv2.erode(mask, None, iterations=2)
        mask = cv2.dilate(mask, None, iterations=2)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if not contours:
            continue

        biggest = max(contours, key=cv2.contourArea)
        area = float(cv2.contourArea(biggest))
        if area < MIN_AREA:
            continue

        moments = cv2.moments(biggest)
        if moments["m00"] == 0:
            continue

        cx = int(moments["m10"] / moments["m00"])
        width = frame.shape[1]
        offset = (cx - width / 2) / (width / 2)  # -1 izquierda, +1 derecha

        if area > best.get("area", 0):
            if offset < -0.25:
                where = "izquierda"
            elif offset > 0.25:
                where = "derecha"
            else:
                where = "centro"
            best = {
                "found": True,
                "color": color,
                "area": round(area, 1),
                "offset": round(offset, 2),
                "where": where,
                # >0.15 del ancho de imagen = bastante cerca
                "closeness": round(min(1.0, area / (width * frame.shape[0] * 0.15)), 2),
            }

    if not seen_any_frame:
        return {"ok": False, "error": "no hay cámara disponible", "found": False}
    best["ok"] = True
    if not best.get("found"):
        best["color"] = color
    return best


class ColorTracker:
    """Seguimiento continuo en un hilo. Lo usa el modo reflejo, no el LLM."""

    def __init__(self, link, camera: Camera, color: str = "rojo", hz: float = 15.0) -> None:
        self.link = link
        self.camera = camera
        self.color = color
        self.period = 1.0 / hz
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last: dict[str, Any] = {}

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            result = probe_color(self.camera, self.color, samples=1)
            self.last = result
            if result.get("found"):
                offset = result.get("offset", 0.0)
                speed = 150
                if offset < -0.25:
                    self.link.move(-speed, speed)
                elif offset > 0.25:
                    self.link.move(speed, -speed)
                else:
                    self.link.move(speed, speed)
            else:
                self.link.stop()
            time.sleep(self.period)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        self.link.stop()
