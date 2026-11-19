"""
WALL-E · Lanzador de simulación y entrenamiento
===============================================

Ventana pequeña para:
- Ver la simulación con el modelo PPO entrenado.
- Seguir entrenando el cerebro motor (con o sin ventana de PyBullet).
- Abrir TensorBoard y las carpetas de modelos/feedback.

Se abre con el acceso directo "Ver simulación y entrenar".
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import messagebox
except ImportError:  # pragma: no cover
    tk = None
    messagebox = None

SCRIPT_DIR = Path(__file__).resolve().parent


def _console_python() -> Path:
    """python.exe aunque el lanzador se abra con pythonw.exe."""
    executable = Path(sys.executable)
    if os.name == "nt":
        candidate = executable.with_name("python.exe")
        if candidate.exists():
            return candidate
    return executable


PYTHON = _console_python()
# Cerebro vigente: 13D, física del robot físico.
MODEL = SCRIPT_DIR / "walle_ppo_model_physical.zip"
MODEL_50K = SCRIPT_DIR / "walle_ppo_model_50k.zip"
CHECKPOINTS = SCRIPT_DIR / "checkpoints"
TENSORBOARD_LOGS = SCRIPT_DIR / "tb_logs"
FEEDBACK = SCRIPT_DIR / "feedback_walle"
ICON_PNG = SCRIPT_DIR / "walle_icon.png"

BG = "#17130c"
PANEL = "#241c11"
PANEL_2 = "#2f2414"
BORDER = "#5a4527"
TEXT = "#f6efe0"
MUTED = "#b7a98e"
ACCENT = "#f2b705"
FONT = "Segoe UI"


def _creation_flags() -> int:
    if os.name == "nt":
        return subprocess.CREATE_NEW_CONSOLE
    return 0


def _count_checkpoints() -> int:
    if not CHECKPOINTS.exists():
        return 0
    return len(list(CHECKPOINTS.glob("*.zip")))


def _count_feedback() -> int:
    csv_path = FEEDBACK / "experiencias_walle.csv"
    if not csv_path.exists():
        return 0
    try:
        with csv_path.open("r", encoding="utf-8", errors="replace") as fh:
            return max(0, sum(1 for _line in fh) - 1)
    except OSError:
        return 0


class LauncherApp:
    def __init__(self) -> None:
        if tk is None:
            raise RuntimeError("Tkinter no está disponible.")

        self.root = tk.Tk()
        self.root.title("WALL-E · Simulación y entrenamiento")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        width, height = 560, 590
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        self.root.geometry(
            f"{width}x{height}+24+{max(0, (screen_h - height) // 2)}"
        )

        try:
            if ICON_PNG.exists():
                self._icon = tk.PhotoImage(file=str(ICON_PNG))
                self.root.iconphoto(True, self._icon)
        except Exception:
            self._icon = None

        self.process: subprocess.Popen | None = None
        self.process_name = ""
        self._tensorboard_started_at: float | None = None
        self._launch_buttons: list[tk.Button] = []

        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._poll()

    # ------------------------------------------------------------------ #
    # Interfaz
    # ------------------------------------------------------------------ #
    def _build(self) -> None:
        self.root.grid_columnconfigure(0, weight=1)

        header = tk.Frame(self.root, bg=BG, padx=20, pady=16)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(1, weight=1)

        if self._icon is not None:
            try:
                logo = self._icon.subsample(4, 4)
                self._logo = logo
                tk.Label(header, image=logo, bg=BG).grid(
                    row=0, column=0, rowspan=2, sticky="w", padx=(0, 12)
                )
            except Exception:
                pass

        tk.Label(
            header,
            text="WALL-E",
            bg=BG,
            fg=ACCENT,
            font=(FONT, 24, "bold"),
            anchor="w",
        ).grid(row=0, column=1, sticky="w")
        tk.Label(
            header,
            text="Simulación y entrenamiento · Fase 2 + Fase 3",
            bg=BG,
            fg=MUTED,
            font=(FONT, 9),
            anchor="w",
        ).grid(row=1, column=1, sticky="w")

        # Resumen de archivos ------------------------------------------- #
        info = tk.Frame(
            self.root,
            bg=PANEL,
            padx=16,
            pady=12,
            highlightthickness=1,
            highlightbackground=BORDER,
        )
        info.grid(row=1, column=0, sticky="ew", padx=16)
        info.grid_columnconfigure(1, weight=1)

        model_label = (
            f"{MODEL.name} (13D, física real)"
            if MODEL.exists()
            else "No encontrado (se puede entrenar desde cero)"
        )
        rows = [
            ("Modelo principal", model_label),
            ("Modelo 50k", "walle_ppo_model_50k.zip" if MODEL_50K.exists() else "—"),
            ("Checkpoints", f"{_count_checkpoints()} archivos en checkpoints/"),
            ("Feedback RLHF", f"{_count_feedback()} experiencias en feedback_walle/"),
        ]
        for index, (label, value) in enumerate(rows):
            tk.Label(
                info,
                text=label,
                bg=PANEL,
                fg=MUTED,
                font=(FONT, 8, "bold"),
                anchor="w",
            ).grid(row=index, column=0, sticky="w", padx=(0, 14), pady=1)
            tk.Label(
                info,
                text=value,
                bg=PANEL,
                fg=TEXT,
                font=("Consolas", 8),
                anchor="w",
            ).grid(row=index, column=1, sticky="w", pady=1)

        # Botones -------------------------------------------------------- #
        buttons = tk.Frame(self.root, bg=BG, padx=16, pady=14)
        buttons.grid(row=2, column=0, sticky="ew")
        buttons.grid_columnconfigure(0, weight=1)

        self._add_button(
            buttons,
            row=0,
            text="▶  Ver simulación entrenada\n    3 episodios con la política PPO",
            command=self._evaluate,
            bg="#1c7ed6",
            active="#339af0",
            fg="#ffffff",
        )
        self._add_button(
            buttons,
            row=1,
            text="🎓  Entrenar viendo la simulación\n     50.000 pasos más · ventana PyBullet",
            command=lambda: self._train(gui=True),
            bg=ACCENT,
            active="#ffd43b",
            fg="#241a08",
        )
        self._add_button(
            buttons,
            row=2,
            text="⚡  Entrenar sin ventana (más rápido)\n     50.000 pasos más · solo consola",
            command=lambda: self._train(gui=False),
            bg="#b8860b",
            active="#d4a017",
            fg="#ffffff",
        )

        utility = tk.Frame(buttons, bg=BG)
        utility.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        utility.grid_columnconfigure(0, weight=1)
        utility.grid_columnconfigure(1, weight=1)

        self._add_button(
            utility,
            row=0,
            column=0,
            text="📈 TensorBoard",
            command=self._tensorboard,
            bg=PANEL_2,
            active="#4a3820",
            fg=TEXT,
            small=True,
        )
        self._add_button(
            utility,
            row=0,
            column=1,
            text="📂 Carpeta de feedback",
            command=self._open_feedback,
            bg=PANEL_2,
            active="#4a3820",
            fg=TEXT,
            small=True,
        )

        # Estado / detener ---------------------------------------------- #
        footer = tk.Frame(self.root, bg=BG, padx=16)
        footer.grid(row=3, column=0, sticky="ew")
        footer.grid_columnconfigure(0, weight=1)

        self.status_var = tk.StringVar(
            value="Elegí una opción. El entrenamiento se guarda solo."
        )
        tk.Label(
            footer,
            textvariable=self.status_var,
            bg=BG,
            fg=MUTED,
            font=(FONT, 8),
            anchor="w",
            wraplength=400,
            justify="left",
        ).grid(row=0, column=0, sticky="w")

        self.stop_button = tk.Button(
            footer,
            text="Detener",
            command=self._stop,
            bg="#c92a2a",
            fg="#ffffff",
            activebackground="#e03131",
            activeforeground="#ffffff",
            disabledforeground="#8f6f6f",
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=14,
            pady=6,
            font=(FONT, 9, "bold"),
            state=tk.DISABLED,
            cursor="hand2",
        )
        self.stop_button.grid(row=0, column=1, sticky="e", padx=(12, 0))

        tk.Label(
            self.root,
            text="El modelo se guarda en walle_ppo_model.zip · "
            "checkpoints/ · tb_logs/",
            bg=BG,
            fg="#7d715e",
            font=(FONT, 7),
        ).grid(row=4, column=0, pady=(4, 12))

    def _add_button(
        self,
        parent: tk.Frame,
        row: int,
        text: str,
        command,
        bg: str,
        active: str,
        fg: str,
        column: int = 0,
        small: bool = False,
    ) -> None:
        button = tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=active,
            activeforeground=fg,
            disabledforeground="#8c7b58",
            relief="flat",
            bd=0,
            highlightthickness=0,
            anchor="w",
            justify="left",
            padx=16,
            pady=7 if small else 9,
            font=(FONT, 9, "bold") if small else (FONT, 10, "bold"),
            cursor="hand2",
        )
        if small:
            button.grid(
                row=row,
                column=column,
                sticky="ew",
                padx=(0, 4) if column == 0 else (4, 0),
            )
        else:
            button.grid(row=row, column=column, sticky="ew", pady=(0, 7))
        self._launch_buttons.append(button)

    # ------------------------------------------------------------------ #
    # Lanzamientos
    # ------------------------------------------------------------------ #
    def _launch(self, name: str, args: list[str]) -> None:
        if self.process is not None and self.process.poll() is None:
            messagebox.showwarning(
                "WALL-E",
                "Ya hay un proceso en ejecución. Esperá a que termine o "
                "usá el botón «Detener».",
            )
            return
        command = [str(PYTHON), *args]
        try:
            self.process = subprocess.Popen(
                command,
                cwd=str(SCRIPT_DIR),
                creationflags=_creation_flags(),
            )
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("WALL-E", f"No pude iniciar {name}:\n{exc}")
            return
        self.process_name = name
        self.status_var.set(
            f"{name} iniciado (PID {self.process.pid}). "
            "El resultado aparece en su propia consola."
        )
        self.stop_button.configure(state=tk.NORMAL)
        self._set_launch_enabled(False)

    def _evaluate(self) -> None:
        if not MODEL.exists():
            messagebox.showerror(
                "WALL-E",
                "No existe walle_ppo_model_physical.zip.\n"
                "Primero entrená el modelo con una de las opciones de abajo.",
            )
            return
        self._launch(
            "Ver simulación",
            [
                str(SCRIPT_DIR / "evaluate_walle.py"),
                "--episodes",
                "3",
                "--model",
                str(MODEL),
            ],
        )

    def _train(self, gui: bool) -> None:
        args = [str(SCRIPT_DIR / "train_walle.py"), "--timesteps", "50000"]
        if MODEL.exists():
            args.extend(["--resume", str(MODEL)])
        if gui:
            args.extend(["--gui", "--gui-eval", "--eval-episodes", "2"])
        self._launch("Entrenamiento", args)

    def _tensorboard(self) -> None:
        if not TENSORBOARD_LOGS.exists():
            messagebox.showerror(
                "WALL-E",
                "Todavía no hay tb_logs/. Entrená primero para generar curvas.",
            )
            return
        self._launch(
            "TensorBoard",
            [
                "-m",
                "tensorboard.main",
                "--logdir",
                str(TENSORBOARD_LOGS),
                "--port",
                "6006",
            ],
        )
        self._tensorboard_started_at = time.monotonic()
        self.root.after(2500, self._open_tensorboard_browser)

    def _open_tensorboard_browser(self) -> None:
        if self._tensorboard_started_at is None:
            return
        try:
            webbrowser.open("http://localhost:6006")
        except Exception:
            pass
        self.status_var.set(
            "TensorBoard: http://localhost:6006 (Ctrl+C en su consola para cerrar)."
        )

    def _open_feedback(self) -> None:
        FEEDBACK.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(FEEDBACK))  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("WALL-E", f"No pude abrir la carpeta:\n{exc}")

    # ------------------------------------------------------------------ #
    # Estado de procesos
    # ------------------------------------------------------------------ #
    def _set_launch_enabled(self, enabled: bool) -> None:
        state = tk.NORMAL if enabled else tk.DISABLED
        for button in self._launch_buttons:
            button.configure(state=state)

    def _stop(self) -> None:
        if self.process is None or self.process.poll() is not None:
            self.stop_button.configure(state=tk.DISABLED)
            return
        if not messagebox.askyesno(
            "Detener",
            f"¿Detener «{self.process_name}»?\n"
            "El modelo guardado hasta ahora no se pierde.",
        ):
            return
        try:
            self.process.terminate()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("WALL-E", f"No pude detener el proceso:\n{exc}")
            return
        self.status_var.set(f"Deteniendo {self.process_name}...")

    def _poll(self) -> None:
        if self.process is not None and self.process.poll() is not None:
            code = self.process.returncode
            name = self.process_name
            self.process = None
            self.process_name = ""
            self.status_var.set(
                f"{name} terminó (código {code}). "
                "Podés ver el resultado en su consola."
            )
            self.stop_button.configure(state=tk.DISABLED)
            self._set_launch_enabled(True)
        self.root.after(1000, self._poll)

    def _on_close(self) -> None:
        if self.process is not None and self.process.poll() is None:
            if not messagebox.askyesno(
                "Cerrar WALL-E",
                "Hay un proceso en ejecución. ¿Cerrarlo también?",
            ):
                return
            try:
                self.process.terminate()
            except Exception:
                pass
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    if tk is None:
        print("Tkinter no está disponible.", file=sys.stderr)
        return 2
    app = LauncherApp()
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
