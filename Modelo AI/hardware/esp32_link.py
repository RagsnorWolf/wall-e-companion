"""Puente con el ESP32 de Agus.

Protocolo real (el que ya funciona): texto plano ASCII a 9600 bauds.
    M:<izq>,<der>\\n      velocidades -255..255
    D:0\\n                detener

Funciona sin hardware: si no hay puerto, entra en modo simulación y registra
lo que habría enviado. Eso permite desarrollar todo el cerebro en la PC.
"""

from __future__ import annotations

import glob
import os
import time
from typing import Any

try:
    import serial  # pyserial
    from serial.tools import list_ports
except ImportError:  # pragma: no cover
    serial = None
    list_ports = None

BAUDRATE = 9600
SPEED_LIMIT = 255


def _candidate_ports() -> list[str]:
    if list_ports is not None:
        ports = [p.device for p in list_ports.comports()]
        if ports:
            return ports
    # Fallback por si pyserial no enumera nada
    candidates = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
    candidates += [f"COM{i}" for i in range(1, 10)]
    return candidates


class Esp32Link:
    def __init__(
        self,
        port: str | None = None,
        baudrate: int = BAUDRATE,
        autoconnect: bool = False,
    ) -> None:
        self.port = port or os.environ.get("WALLE_PORT")
        self.baudrate = baudrate
        self.autoconnect = autoconnect
        self.serial = None
        self.connected = False
        self.last_command: tuple[int, int] | None = None
        self.last_command_at: float = 0.0
        self._simulation_reason: str | None = None
        self._connect()

    # ------------------------------------------------------------- conexión
    def _connect(self) -> None:
        if serial is None:
            self._simulation_reason = "pyserial no instalado"
            return

        # Seguridad: nunca abrimos un puerto al azar. Escribir en un COM
        # equivocado puede romper otro dispositivo. Solo con puerto explícito.
        if not self.port:
            if not self.autoconnect:
                self._simulation_reason = "sin puerto configurado (usá --port COM3)"
                return
            ports = _candidate_ports()
        else:
            ports = [self.port]

        for candidate in ports:
            if not candidate:
                continue
            try:
                self.serial = serial.Serial(candidate, self.baudrate, timeout=1)
                time.sleep(1.5)  # el ESP32 se resetea al abrir el puerto
                self.port = candidate
                self.connected = True
                self._simulation_reason = None
                return
            except Exception as exc:  # puerto ocupado o inexistente
                self._simulation_reason = f"{candidate}: {exc}"

        self.serial = None
        self.connected = False

    def reconnect(self) -> bool:
        self.close()
        self._connect()
        return self.connected

    # ------------------------------------------------------------- comandos
    def _write(self, line: str) -> bool:
        if self.serial is None:
            return False
        try:
            self.serial.write(line.encode("utf-8"))
            self.serial.flush()
            return True
        except Exception as exc:
            self.connected = False
            self._simulation_reason = f"escritura falló: {exc}"
            return False

    def move(self, left: int, right: int) -> bool:
        left = max(-SPEED_LIMIT, min(SPEED_LIMIT, int(left)))
        right = max(-SPEED_LIMIT, min(SPEED_LIMIT, int(right)))
        self.last_command = (left, right)
        self.last_command_at = time.time()
        return self._write(f"M:{left},{right}\n")

    def stop(self) -> bool:
        self.last_command = (0, 0)
        self.last_command_at = time.time()
        return self._write("D:0\n")

    def timed_move(self, left: int, right: int, seconds: float) -> None:
        """Mueve y frena solo. Bloqueante y acotado: nunca se escapa."""
        seconds = max(0.0, min(float(seconds), 3.0))
        self.move(left, right)
        try:
            time.sleep(seconds)
        finally:
            self.stop()

    # ------------------------------------------------------------- estado
    def status(self) -> dict[str, Any]:
        moving = bool(
            self.last_command and self.last_command != (0, 0) and self.connected
        )
        return {
            "connected": self.connected,
            "port": self.port,
            "baudrate": self.baudrate,
            "mode": "hardware" if self.connected else "simulacion",
            "reason": None if self.connected else self._simulation_reason,
            "moving": moving,
            "last_command": self.last_command,
        }

    def close(self) -> None:
        if self.serial is not None:
            try:
                self.serial.close()
            except Exception:
                pass
        self.serial = None
        self.connected = False

    def __enter__(self) -> "Esp32Link":
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()
        self.close()
