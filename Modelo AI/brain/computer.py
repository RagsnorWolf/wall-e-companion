"""Acciones reales sobre la computadora, con guantes de seguridad.

WALL-E puede abrir programas, carpetas y webs, y crear carpetas o archivos
de texto. No puede borrar, ejecutar comandos arbitrarios ni tocar carpetas
del sistema. Todo queda registrado en la cabina.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

_APPS: dict[str, list[str] | str] = {
    "bloc de notas": ["notepad.exe"],
    "notepad": ["notepad.exe"],
    "calculadora": ["calc.exe"],
    "calculadora cientifica": ["calc.exe"],
    "paint": ["mspaint.exe"],
    "pintura": ["mspaint.exe"],
    "explorador": ["explorer.exe"],
    "archivos": ["explorer.exe"],
    "administrador de archivos": ["explorer.exe"],
    "navegador": "https://www.google.com",
    "google": "https://www.google.com",
    "chrome": "https://www.google.com",
    "edge": "microsoft-edge:https://www.google.com",
    "configuracion": "ms-settings:",
    "ajustes": "ms-settings:",
    "spotify": "spotify:",
    "whatsapp": "whatsapp:",
    "camara": "microsoft.windows.camera:",
}

_BLOCKED_PARTS = {
    "windows",
    "system32",
    "syswow64",
    "program files",
    "program files (x86)",
    "programdata",
    "$recycle.bin",
    "system volume information",
}

_SAFE_SUFFIXES = {".txt", ".md", ".json", ".csv", ".html", ".py", ".js", ".css", ".log"}
_MAX_FILE_CHARS = 20000


class Computer:
    """Acciones de escritorio con lista blanca. Sin shell, sin borrados."""

    def __init__(self) -> None:
        self.home = Path.home()
        self.desktop = self._first_dir(self.home / "Desktop", self.home / "Escritorio", self.home)
        self.started_at = time.time()

    # ------------------------------------------------------------- helpers
    @staticmethod
    def _first_dir(*candidates: Path) -> Path:
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[-1]

    def _resolve(self, raw: str, default_dir: Path | None = None) -> Path:
        text = (raw or "").strip().strip('"').strip("'")
        if not text:
            raise ValueError("falta la ruta")
        path = Path(os.path.expandvars(text)).expanduser()
        if not path.is_absolute():
            path = (default_dir or self.desktop) / path
        return path.resolve()

    def _guard(self, path: Path, writing: bool = False) -> None:
        parts = {part.lower() for part in path.parts}
        if parts & _BLOCKED_PARTS:
            raise ValueError("no puedo tocar carpetas del sistema")
        if writing:
            allowed = (
                _is_inside(path, self.home)
                or _is_inside(path, PROJECT_ROOT)
                or _is_inside(path, Path(os.environ.get("TEMP", self.home)))
            )
            if not allowed:
                raise ValueError(
                    "por seguridad solo creo cosas dentro de tu carpeta de usuario "
                    "o del proyecto"
                )

    # ------------------------------------------------------------- acciones
    def ejecutar(self, accion: str, destino: str = "", contenido: str = "") -> dict[str, Any]:
        accion = (accion or "").strip().lower()
        try:
            if accion in {"abrir_app", "abrir_programa", "abrir_aplicacion"}:
                return self.abrir_app(destino)
            if accion in {"abrir_carpeta", "abrir"}:
                return self.abrir_carpeta(destino)
            if accion in {"abrir_web", "navegar", "buscar_en_google"}:
                return self.abrir_web(destino)
            if accion in {"crear_carpeta", "crear_directorio"}:
                return self.crear_carpeta(destino)
            if accion in {"crear_archivo", "escribir_archivo"}:
                return self.crear_archivo(destino, contenido)
            if accion in {"listar_carpeta", "listar"}:
                return self.listar_carpeta(destino)
            if accion in {"info_sistema", "estado_pc"}:
                return self.info_sistema()
            return {
                "ok": False,
                "detail": f"no conozco la acción {accion}",
                "acciones": [
                    "abrir_app",
                    "abrir_carpeta",
                    "abrir_web",
                    "crear_carpeta",
                    "crear_archivo",
                    "listar_carpeta",
                    "info_sistema",
                ],
            }
        except ValueError as exc:
            return {"ok": False, "detail": str(exc)}
        except Exception as exc:
            return {"ok": False, "detail": f"no pude hacerlo: {exc}"}

    def abrir_app(self, nombre: str) -> dict[str, Any]:
        key = (nombre or "").strip().lower()
        if not key:
            return {
                "ok": False,
                "detail": "decime qué programa abrir",
                "apps": sorted(_APPS),
            }
        target = _APPS.get(key)
        if target is None:
            for alias, value in _APPS.items():
                if alias in key or key in alias:
                    target = value
                    key = alias
                    break
        if target is None:
            return {
                "ok": False,
                "detail": f"no tengo {nombre} en mi lista de programas",
                "apps": sorted(_APPS),
            }

        if isinstance(target, str):
            os.startfile(target)  # type: ignore[attr-defined]
            return {"ok": True, "detail": f"abriendo {key}", "app": key}

        if sys.platform != "win32":
            return {"ok": False, "detail": "abrir programas solo funciona en Windows"}
        subprocess.Popen(target, shell=False)  # noqa: S603
        return {"ok": True, "detail": f"abrí {key}", "app": key}

    def abrir_carpeta(self, ruta: str) -> dict[str, Any]:
        path = self._resolve(ruta)
        self._guard(path)
        if not path.exists():
            return {"ok": False, "detail": f"no existe la carpeta {path}"}
        if not path.is_dir():
            return {"ok": False, "detail": f"{path.name} es un archivo, no una carpeta"}
        os.startfile(str(path))  # type: ignore[attr-defined]
        return {"ok": True, "detail": f"abriendo {path.name}", "path": str(path)}

    def abrir_web(self, url: str) -> dict[str, Any]:
        raw = (url or "").strip()
        if not raw:
            return {"ok": False, "detail": "decime qué página abrir"}
        if " " in raw and "." not in raw:
            raw = "https://www.google.com/search?q=" + raw.replace(" ", "+")
        if not raw.lower().startswith(("http://", "https://")):
            raw = "https://" + raw
        parsed = urlparse(raw)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return {"ok": False, "detail": "esa dirección no es una web válida"}
        webbrowser.open(raw)
        return {"ok": True, "detail": f"abriendo {parsed.netloc}", "url": raw}

    def crear_carpeta(self, ruta: str) -> dict[str, Any]:
        path = self._resolve(ruta)
        self._guard(path, writing=True)
        if path.exists():
            if path.is_dir():
                return {"ok": True, "detail": f"la carpeta {path.name} ya existía", "path": str(path)}
            return {"ok": False, "detail": f"ya existe un archivo llamado {path.name}"}
        path.mkdir(parents=True, exist_ok=False)
        return {"ok": True, "detail": f"creé la carpeta {path.name}", "path": str(path)}

    def crear_archivo(self, ruta: str, contenido: str = "") -> dict[str, Any]:
        path = self._resolve(ruta)
        self._guard(path, writing=True)
        if path.suffix.lower() not in _SAFE_SUFFIXES:
            return {
                "ok": False,
                "detail": "solo escribo archivos de texto: " + ", ".join(sorted(_SAFE_SUFFIXES)),
            }
        if path.exists():
            return {"ok": False, "detail": f"ya existe {path.name}; no lo piso"}
        text = (contenido or "").strip()
        if len(text) > _MAX_FILE_CHARS:
            return {"ok": False, "detail": "el texto es demasiado largo"}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + ("\n" if text else ""), encoding="utf-8")
        return {"ok": True, "detail": f"creé {path.name}", "path": str(path)}

    def listar_carpeta(self, ruta: str = "") -> dict[str, Any]:
        path = self._resolve(ruta) if ruta else self.desktop
        self._guard(path)
        if not path.exists() or not path.is_dir():
            return {"ok": False, "detail": f"no encuentro la carpeta {path}"}
        items = []
        try:
            for child in sorted(path.iterdir(), key=lambda item: (item.is_file(), item.name.lower())):
                if child.name.startswith("."):
                    continue
                items.append(
                    {
                        "name": child.name,
                        "type": "carpeta" if child.is_dir() else "archivo",
                    }
                )
                if len(items) >= 40:
                    break
        except PermissionError:
            return {"ok": False, "detail": "no tengo permiso para leer esa carpeta"}
        return {
            "ok": True,
            "detail": f"{len(items)} cosas en {path.name}",
            "path": str(path),
            "items": items,
        }

    def info_sistema(self) -> dict[str, Any]:
        try:
            total, used, free = shutil.disk_usage(self.home)
            disk = f"{free // (1024 ** 3)} GB libres de {total // (1024 ** 3)} GB"
        except Exception:
            disk = "no pude leer el disco"
        data = {
            "sistema": f"{platform.system()} {platform.release()}",
            "equipo": platform.machine(),
            "procesador": platform.processor() or "desconocido",
            "nucleos": os.cpu_count(),
            "disco": disk,
            "python": platform.python_version(),
        }
        return {
            "ok": True,
            "detail": f"{data['sistema']}, {data['nucleos']} núcleos, {disk}",
            **data,
        }


def _is_inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False
