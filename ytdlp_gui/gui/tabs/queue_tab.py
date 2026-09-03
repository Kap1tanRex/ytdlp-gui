"""Раздел «Очередь»: список загрузок, прогресс, управление."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

import customtkinter as ctk

from ...core.models import Job, JobStatus, ProgressInfo, format_eta, format_size, format_speed
from .. import theme
from ..widgets.design import (
    SEVERITY_TOKENS,
    Card,
    button,
    compact_button,
    muted_label,
    title_label,
)

#: Состояние задания -> уровень важности (цвет подписи статуса).
_STATUS_SEVERITY = {
    JobStatus.PENDING.value: "idle",
    JobStatus.RUNNING.value: "busy",
    JobStatus.POSTPROCESSING.value: "busy",
    JobStatus.COMPLETED.value: "ok",
    JobStatus.FAILED.value: "error",
    JobStatus.CANCELLED.value: "warning",
    JobStatus.SKIPPED.value: "idle",
}


def _progress_detail(job: Job, info: ProgressInfo | None) -> str:
    """Строка под названием задания: во время загрузки — живой прогресс
    (процент, скорость, оставшееся время), иначе — этап/ссылка."""
    if job.status == JobStatus.RUNNING.value and info is not None:
        percent = f"{info.fraction * 100:.1f}%" if info.total_bytes else "…"
        size = (
            f"{format_size(info.downloaded_bytes)} / {format_size(info.total_bytes)}"
            if info.total_bytes
            else format_size(info.downloaded_bytes)
        )
        return (
            f"{percent}   •   {size}   •   {format_speed(info.speed)}   •   "
            f"Осталось: {format_eta(info.eta)}"
        )
    return job.stage_text or job.url


def _open_path(path: Path) -> None:
    try:
        if sys.platform == "win32":
            os.startfile(path)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        else:
            subprocess.run(["xdg-open", str(path)], check=False)
    except OSError:
        pass


class QueueTab(ctk.CTkFrame):
    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._rows: dict[str, dict] = {}

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_list()

    # -- построение ----------------------------------------------------------
    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, theme.GAP["md"]))
        header.grid_columnconfigure(0, weight=1)

        titles = ctk.CTkFrame(header, fg_color="transparent")
        titles.grid(row=0, column=0, sticky="w")
        title_label(titles, "Очередь загрузок").grid(row=0, column=0, sticky="w")
        self.summary_label = muted_label(titles, "")
        self.summary_label.grid(row=1, column=0, sticky="w", pady=(2, 0))

        button(header, "Очистить завершённые", self._clear_finished).grid(row=0, column=1, sticky="e")

    def _build_list(self) -> None:
        self.list_frame = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
        self.list_frame.grid(row=1, column=0, sticky="nsew")
        self.list_frame.grid_columnconfigure(0, weight=1)

        self.empty_label = muted_label(self.list_frame, "Очередь пуста — добавьте загрузку")
        self.empty_label.grid(row=0, column=0, sticky="w", padx=theme.GAP["xs"], pady=theme.GAP["sm"])

    # -- обновления ------------------------------------------------------
    def refresh_queue(self) -> None:
        jobs = self.app.queue.jobs
        current_ids = {job.id for job in jobs}
        for job_id in list(self._rows):
            if job_id not in current_ids:
                self._rows.pop(job_id)["frame"].destroy()

        for index, job in enumerate(jobs):
            row = self._rows.get(job.id)
            if row is None:
                row = self._create_row(job)
                self._rows[job.id] = row
            row["frame"].grid(row=index, column=0, sticky="ew", pady=(0, theme.GAP["sm"]))
            self._update_row(job)

        if jobs:
            self.empty_label.grid_remove()
        else:
            self.empty_label.grid()
        self._update_summary(jobs)

    def _update_summary(self, jobs: list[Job]) -> None:
        if not jobs:
            self.summary_label.configure(text="Заданий нет")
            return
        done = sum(1 for job in jobs if job.status == JobStatus.COMPLETED.value)
        failed = sum(1 for job in jobs if job.status == JobStatus.FAILED.value)
        active = sum(1 for job in jobs if job.is_active)
        parts = [f"Всего: {len(jobs)}", f"выполняется: {active}", f"завершено: {done}"]
        if failed:
            parts.append(f"с ошибкой: {failed}")
        self.summary_label.configure(text="   •   ".join(parts))

    def update_job(self, job: Job, info: ProgressInfo | None = None) -> None:
        if job.id not in self._rows:
            self.refresh_queue()
            return
        if info is not None:
            job.progress = info.fraction
            self._rows[job.id]["last_progress"] = info
        self._update_row(job)

    # -- построение строки -------------------------------------------------
    def _create_row(self, job: Job) -> dict:
        frame = Card(self.list_frame)
        frame.body.grid_columnconfigure(0, weight=1)
        body = frame.body

        label = ctk.CTkLabel(body, text=job.label, anchor="w", font=theme.font("base", weight="bold"))
        label.grid(row=0, column=0, sticky="ew", padx=(0, theme.GAP["md"]))

        status = ctk.CTkLabel(
            body,
            text=job.status_title(),
            anchor="e",
            width=110,
            font=theme.font("small", weight="bold"),
        )
        status.grid(row=0, column=1, sticky="e")

        detail = muted_label(body, "")
        detail.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 0))

        bar = ctk.CTkProgressBar(body, height=6)
        bar.set(0)
        bar.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(theme.GAP["sm"], theme.GAP["sm"]))

        buttons = ctk.CTkFrame(body, fg_color="transparent")
        buttons.grid(row=3, column=0, columnspan=2, sticky="w")

        cancel_btn = compact_button(buttons, "Отмена", lambda: self._cancel_job(job.id), width=84)
        cancel_btn.grid(row=0, column=0, padx=(0, theme.GAP["sm"]))

        remove_btn = compact_button(
            buttons,
            "Удалить",
            lambda: (self.app.queue.remove(job.id), self.refresh_queue()),
            width=84,
        )
        remove_btn.grid(row=0, column=1, padx=(0, theme.GAP["sm"]))

        log_btn = compact_button(buttons, "Лог", lambda: self.open_log(job), width=64)
        log_btn.grid(row=0, column=2, padx=(0, theme.GAP["sm"]))

        folder_btn = compact_button(
            buttons, "Папка", lambda: self.app.open_output_folder(job), width=76
        )
        folder_btn.grid(row=0, column=3)

        return {
            "frame": frame,
            "label": label,
            "status": status,
            "detail": detail,
            "bar": bar,
            "cancel_btn": cancel_btn,
            "remove_btn": remove_btn,
            "log_btn": log_btn,
            "folder_btn": folder_btn,
        }

    def _update_row(self, job: Job) -> None:
        row = self._rows[job.id]
        severity = _STATUS_SEVERITY.get(job.status, "idle")
        row["label"].configure(text=job.label)
        row["status"].configure(
            text=job.status_title(),
            text_color=theme.color(SEVERITY_TOKENS.get(severity, "fg.secondary")),
        )
        row["bar"].set(max(0.0, min(1.0, job.progress)))
        row["bar"].configure(
            progress_color=theme.color(
                "state.error" if severity == "error" else ("state.ok" if severity == "ok" else "accent")
            )
        )
        row["detail"].configure(text=_progress_detail(job, row.get("last_progress")))

        can_cancel = job.status in (JobStatus.PENDING.value, JobStatus.RUNNING.value, JobStatus.POSTPROCESSING.value)
        row["cancel_btn"].configure(state="normal" if can_cancel else "disabled")
        row["remove_btn"].configure(state="disabled" if job.is_active else "normal")
        row["log_btn"].configure(state="normal" if job.log_path else "disabled")
        row["folder_btn"].configure(state="normal" if job.status == JobStatus.COMPLETED.value else "disabled")

    def _cancel_job(self, job_id: str) -> None:
        # Для активного задания cancel() делает terminate()+wait() (до
        # нескольких секунд) — не блокируем этим поток Tk.
        threading.Thread(target=self.app.queue.cancel, args=(job_id,), daemon=True).start()

    def _clear_finished(self) -> None:
        self.app.queue.clear_finished()
        self.refresh_queue()

    # -- вспомогательное -------------------------------------------------
    def open_log(self, job: Job) -> None:
        if job.log_path:
            _open_path(Path(job.log_path))

    #: Прежнее (внутреннее) имя метода — на него ссылались диалоги ошибок.
    _open_log = open_log

    def copy_to_clipboard(self, text: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(text)
