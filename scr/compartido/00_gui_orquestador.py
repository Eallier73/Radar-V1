#!/usr/bin/env python3
"""Interfaz gráfica para el orquestador de etapas de Radar."""

from __future__ import annotations

import importlib.util
import os
from queue import Empty, Queue
import signal
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk


REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_DIR = Path(__file__).resolve().parent
ORCHESTRATOR_PATH = SHARED_DIR / "00_orquestador_general.py"


def load_orchestrator_module():
    module_name = "radar_orquestador_general"
    spec = importlib.util.spec_from_file_location(module_name, ORCHESTRATOR_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"No se pudo cargar el orquestador: {ORCHESTRATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


ORQUESTADOR = load_orchestrator_module()
PIPELINES = ORQUESTADOR.PIPELINES


class OrquestadorGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Radar - Orquestador de etapas")
        self.root.geometry("920x760")
        self.root.minsize(780, 650)

        self.venv_python = self.detect_venv_python()
        self.log_queue: Queue[tuple[str, str]] = Queue()
        self.running_process: subprocess.Popen[str] | None = None
        self.worker: threading.Thread | None = None
        self.stop_requested = False

        self.week_var = tk.StringVar(value=ORQUESTADOR.DEFAULT_GLOBAL_ISO_WEEK)
        default_since, default_before = ORQUESTADOR.iso_week_to_range(self.week_var.get())
        self.since_var = tk.StringVar(value=default_since)
        self.before_var = tk.StringVar(value=default_before)
        self.continue_on_error_var = tk.BooleanVar(value=False)
        self.stage_vars = {
            stage.code: tk.BooleanVar(value=True)
            for stage in PIPELINES
        }
        self.status_labels: dict[str, ttk.Label] = {}

        self.build_ui()
        self.refresh_stage_status()
        self.root.after(100, self.process_log_queue)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def detect_venv_python(self) -> str:
        return str(ORQUESTADOR.PYTHON_EXECUTABLE)

    def build_ui(self) -> None:
        container = ttk.Frame(self.root, padding=12)
        container.pack(fill=tk.BOTH, expand=True)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(4, weight=1)

        title = ttk.Label(
            container,
            text="Pipeline Radar",
            font=("TkDefaultFont", 16, "bold"),
        )
        title.grid(row=0, column=0, sticky="w")
        ttk.Label(
            container,
            text=f"Repositorio: {REPO_ROOT}",
        ).grid(row=1, column=0, sticky="w", pady=(2, 10))

        config_frame = ttk.LabelFrame(container, text="Periodo semanal", padding=10)
        config_frame.grid(row=2, column=0, sticky="ew")
        config_frame.columnconfigure(5, weight=1)

        ttk.Label(config_frame, text="Semana ISO:").grid(row=0, column=0, sticky="w")
        ttk.Entry(config_frame, textvariable=self.week_var, width=12).grid(
            row=0, column=1, padx=(6, 12)
        )
        ttk.Button(config_frame, text="Aplicar semana", command=self.apply_week).grid(
            row=0, column=2, padx=(0, 18)
        )
        ttk.Label(config_frame, text="Desde:").grid(row=0, column=3, sticky="w")
        ttk.Entry(config_frame, textvariable=self.since_var, width=12).grid(
            row=0, column=4, padx=(6, 12)
        )
        ttk.Label(config_frame, text="Hasta:").grid(row=0, column=5, sticky="e")
        ttk.Entry(config_frame, textvariable=self.before_var, width=12).grid(
            row=0, column=6, padx=(6, 0)
        )

        stages_frame = ttk.LabelFrame(container, text="Etapas", padding=10)
        stages_frame.grid(row=3, column=0, sticky="ew", pady=10)
        stages_frame.columnconfigure(1, weight=1)

        for row, stage in enumerate(PIPELINES):
            check = ttk.Checkbutton(
                stages_frame,
                text=f"{stage.code}. {stage.label}",
                variable=self.stage_vars[stage.code],
            )
            check.grid(row=row, column=0, sticky="w", pady=2)
            ttk.Label(stages_frame, text=stage.description).grid(
                row=row, column=1, sticky="w", padx=(12, 8)
            )
            status = ttk.Label(stages_frame, text="")
            status.grid(row=row, column=2, sticky="e")
            self.status_labels[stage.code] = status

        stage_actions = ttk.Frame(stages_frame)
        stage_actions.grid(row=len(PIPELINES), column=0, columnspan=3, sticky="ew", pady=(8, 0))
        ttk.Button(stage_actions, text="Seleccionar todas", command=self.select_all).pack(
            side=tk.LEFT
        )
        ttk.Button(stage_actions, text="Limpiar", command=self.select_none).pack(
            side=tk.LEFT, padx=6
        )
        ttk.Button(stage_actions, text="Revalidar", command=self.refresh_stage_status).pack(
            side=tk.LEFT
        )
        ttk.Checkbutton(
            stage_actions,
            text="Continuar si una etapa falla",
            variable=self.continue_on_error_var,
        ).pack(side=tk.RIGHT)

        log_frame = ttk.LabelFrame(container, text="Ejecución", padding=8)
        log_frame.grid(row=4, column=0, sticky="nsew")
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.log = scrolledtext.ScrolledText(
            log_frame,
            wrap=tk.WORD,
            height=16,
            state=tk.DISABLED,
            font=("TkFixedFont", 10),
        )
        self.log.grid(row=0, column=0, sticky="nsew")
        self.log.tag_configure("error", foreground="#b00020")
        self.log.tag_configure("success", foreground="#087f23")
        self.log.tag_configure("command", foreground="#2457a6")

        actions = ttk.Frame(container)
        actions.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(actions, text="Mostrar comandos", command=self.show_commands).pack(side=tk.LEFT)
        self.run_button = ttk.Button(actions, text="Ejecutar", command=self.start_execution)
        self.run_button.pack(side=tk.LEFT, padx=6)
        self.stop_button = ttk.Button(
            actions,
            text="Detener",
            command=self.stop_execution,
            state=tk.DISABLED,
        )
        self.stop_button.pack(side=tk.LEFT)
        ttk.Button(actions, text="Limpiar registro", command=self.clear_log).pack(side=tk.RIGHT)

        interpreter = Path(self.venv_python)
        ttk.Label(
            actions,
            text=f"Python: {interpreter}",
        ).pack(side=tk.RIGHT, padx=12)

    def apply_week(self) -> None:
        try:
            since, before = ORQUESTADOR.iso_week_to_range(self.week_var.get())
        except ValueError as exc:
            messagebox.showerror("Semana inválida", str(exc))
            return
        self.since_var.set(since)
        self.before_var.set(before)

    def select_all(self) -> None:
        for variable in self.stage_vars.values():
            variable.set(True)

    def select_none(self) -> None:
        for variable in self.stage_vars.values():
            variable.set(False)

    def selected_stages(self):
        return [
            stage
            for stage in PIPELINES
            if self.stage_vars[stage.code].get()
        ]

    def validated_period(self) -> tuple[str, str]:
        return ORQUESTADOR.validate_date_range(
            self.since_var.get().strip(),
            self.before_var.get().strip(),
        )

    def refresh_stage_status(self) -> None:
        for stage in PIPELINES:
            available, message = ORQUESTADOR.stage_status(stage)
            label = self.status_labels[stage.code]
            label.configure(
                text="Disponible" if available else "Runner pendiente",
                foreground="#087f23" if available else "#9a6700",
            )
            label.bind("<Enter>", lambda _event, text=message: self.root.title(text))
            label.bind(
                "<Leave>",
                lambda _event: self.root.title("Radar - Orquestador de etapas"),
            )

    def validate_selection(self, *, require_runners: bool) -> tuple[list, str, str] | None:
        stages = self.selected_stages()
        if not stages:
            messagebox.showwarning("Sin etapas", "Selecciona al menos una etapa.")
            return None
        try:
            since, before = self.validated_period()
        except ValueError as exc:
            messagebox.showerror("Periodo inválido", str(exc))
            return None

        if require_runners:
            missing = [stage for stage in stages if not stage.runner.is_file()]
            if missing:
                details = "\n".join(
                    f"- {stage.label}: {stage.relative_runner}"
                    for stage in missing
                )
                messagebox.showerror(
                    "Etapas todavía no ejecutables",
                    "Faltan los runners de estas etapas:\n\n" + details,
                )
                return None
        return stages, since, before

    def prepare_command(self, cmd: list[str]) -> list[str]:
        prepared = list(cmd)
        if prepared:
            prepared[0] = self.venv_python
        return prepared

    def show_commands(self) -> None:
        validated = self.validate_selection(require_runners=False)
        if validated is None:
            return
        stages, since, before = validated
        self.append_log(f"Periodo: {since} -> {before}\n")
        for stage in stages:
            self.append_log(f"\n[{stage.code}/6] {stage.label}\n")
            plans = ORQUESTADOR.build_stage_commands(
                stage,
                since,
                before,
                require_runner=False,
            )
            for cmd, _env in plans:
                self.append_log(
                    "$ " + ORQUESTADOR.render_command(self.prepare_command(cmd)) + "\n",
                    "command",
                )

    def start_execution(self) -> None:
        validated = self.validate_selection(require_runners=True)
        if validated is None:
            return
        stages, since, before = validated
        self.stop_requested = False
        continue_on_error = self.continue_on_error_var.get()
        self.run_button.configure(state=tk.DISABLED)
        self.stop_button.configure(state=tk.NORMAL)
        self.worker = threading.Thread(
            target=self.run_stages,
            args=(stages, since, before, continue_on_error),
            daemon=True,
        )
        self.worker.start()

    def run_stages(
        self,
        stages,
        since: str,
        before: str,
        continue_on_error: bool,
    ) -> None:
        failures = 0
        self.log_queue.put(("normal", f"Periodo: {since} -> {before}\n"))
        for stage in stages:
            if self.stop_requested:
                break
            self.log_queue.put(("normal", f"\n[{stage.code}/6] {stage.label}\n"))
            try:
                plans = ORQUESTADOR.build_stage_commands(stage, since, before)
            except Exception as exc:
                failures += 1
                self.log_queue.put(("error", f"ERROR: {exc}\n"))
                if not continue_on_error:
                    break
                continue

            for cmd, env_updates in plans:
                prepared = self.prepare_command(cmd)
                self.log_queue.put(
                    ("command", "$ " + ORQUESTADOR.render_command(prepared) + "\n")
                )
                env = os.environ.copy()
                env.update(env_updates)
                try:
                    self.running_process = subprocess.Popen(
                        prepared,
                        cwd=REPO_ROOT,
                        env=env,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        bufsize=1,
                        start_new_session=True,
                    )
                    assert self.running_process.stdout is not None
                    for line in self.running_process.stdout:
                        self.log_queue.put(("normal", line))
                    return_code = self.running_process.wait()
                except Exception as exc:
                    return_code = 1
                    self.log_queue.put(("error", f"ERROR al iniciar: {exc}\n"))
                finally:
                    self.running_process = None

                if return_code != 0:
                    failures += 1
                    self.log_queue.put(
                        ("error", f"{stage.label} terminó con código {return_code}.\n")
                    )
                    if not continue_on_error:
                        break
            if failures and not continue_on_error:
                break

        if self.stop_requested:
            self.log_queue.put(("error", "\nEjecución detenida por el usuario.\n"))
        elif failures:
            self.log_queue.put(("error", f"\nEjecución terminada con {failures} error(es).\n"))
        else:
            self.log_queue.put(("success", "\nTodas las etapas seleccionadas finalizaron.\n"))
        self.log_queue.put(("finished", ""))

    def stop_execution(self) -> None:
        self.stop_requested = True
        process = self.running_process
        if process is not None and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                process.terminate()
        self.stop_button.configure(state=tk.DISABLED)

    def process_log_queue(self) -> None:
        try:
            while True:
                tag, text = self.log_queue.get_nowait()
                if tag == "finished":
                    self.run_button.configure(state=tk.NORMAL)
                    self.stop_button.configure(state=tk.DISABLED)
                else:
                    self.append_log(text, tag)
        except Empty:
            pass
        self.root.after(100, self.process_log_queue)

    def append_log(self, text: str, tag: str = "normal") -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, text, tag)
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def clear_log(self) -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.delete("1.0", tk.END)
        self.log.configure(state=tk.DISABLED)

    def on_close(self) -> None:
        if self.running_process is not None and self.running_process.poll() is None:
            if not messagebox.askyesno(
                "Cerrar",
                "Hay una etapa ejecutándose. ¿Deseas detenerla y cerrar?",
            ):
                return
            self.stop_execution()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    OrquestadorGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
