"""Очередь загрузок (design-system §7.2).

Заголовок страницы со сводкой и кнопками, ниже — одна панель со
строками заданий: миниатюра, название, строка данных, статус цветом
состояния и квадратные кнопки справа. Пустая очередь — пунктирная зона.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path

from ...core.models import DownloadMode, Job, JobStatus, ProgressInfo
from ...services.filesystem_service import open_folder
from .. import fmt, theme
from ..widgets.design import Btn, Column, DashedBox, PageTitle, Panel, Para, hline, text
from ..widgets.layout import ScrollPage
from ..widgets.rows import ListRow
from ..widgets.thumbnail_view import ThumbnailLoader
from ..widgets.tooltip import Tooltip

#: Статус -> (подпись, цвет).
_STATUS = {
    JobStatus.PENDING.value: ("В очереди", theme.FAINT),
    JobStatus.RUNNING.value: ("Загружаю", theme.DIM),
    JobStatus.POSTPROCESSING.value: ("Обрабатываю", theme.DIM),
    JobStatus.COMPLETED.value: ("Готово", theme.OK),
    JobStatus.FAILED.value: ("Ошибка", theme.ERR),
    JobStatus.CANCELLED.value: ("Остановлено", theme.WARN),
    JobStatus.SKIPPED.value: ("Пропущено", theme.FAINT),
}

_ACTIVE = (JobStatus.RUNNING.value, JobStatus.POSTPROCESSING.value)


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


def _describe(job: Job) -> str:
    """Что скачивается: «видео · mp4» или «звук · mp3 · 192 кбит/с»."""
    options = job.options
    if options.mode == DownloadMode.AUDIO.value:
        quality = ""
        if options.audio_format not in ("flac", "wav", "best"):
            if options.audio_quality == "0":
                quality = "макс. качество"
            else:
                quality = f"{options.audio_quality}{fmt.THIN}кбит/с"
        return fmt.join("звук", options.audio_format, quality)
    return fmt.join("видео", options.container or "", "свой формат" if options.video_format_id else "")


class _JobRow(ListRow):
    def __init__(self, master, page: "QueuePage", job: Job) -> None:
        super().__init__(master, on_click=lambda: page.row_clicked(self.job))
        self.job = job
        self.page = page
        self.last_progress: ProgressInfo | None = None

        self.status = text(self, "", font=theme.sans(12), anchor="e")
        self.add_right(self.status, padx=(16, 0))
        self.percent = text(self, "", font=theme.mono(12), color=theme.DIM, anchor="e")
        self.add_right(self.percent, padx=(10, 0))
        self.cancel_button = Btn(self, "■", lambda: page.cancel(self.job), kind="tool")
        self.add_right(self.cancel_button, padx=(14, 0))
        self.folder_button = Btn(self, "↗", lambda: page.app.open_output_folder(self.job), kind="tool")
        self.add_right(self.folder_button, padx=(6, 0))
        self.log_button = Btn(self, "≡", lambda: page.open_log(self.job), kind="tool")
        self.add_right(self.log_button, padx=(6, 0))
        self.remove_button = Btn(self, "×", lambda: page.remove(self.job), kind="tool")
        self.add_right(self.remove_button, padx=(6, 0))
        self.finish_right()

        tooltips = (
            (self.cancel_button, "Остановить · Esc — текущую"),
            (self.folder_button, "Открыть папку с файлом"),
            (self.log_button, "Технический журнал yt-dlp"),
            (self.remove_button, "Убрать из списка"),
        )
        for widget, hint in tooltips:
            Tooltip(widget, page.app, hint)
        if job.source is not None:
            self.thumb.load(page.loader, job.source)

    def refresh(self) -> None:
        job = self.job
        title, color = _STATUS.get(job.status, (job.status_title(), theme.DIM))
        progress = self.last_progress

        if job.status == JobStatus.CANCELLED.value and job.progress > 0:
            title = f"Остановлено на {fmt.percent(job.progress)}"
        self.status.configure(text=title, text_color=color)
        self.title.set(job.label)

        running = job.status == JobStatus.RUNNING.value
        if running and progress is not None:
            if progress.total_bytes:
                done = f"{fmt.size(progress.downloaded_bytes)} из {fmt.size(progress.total_bytes)}"
                self.percent.configure(text=fmt.percent(progress.fraction))
            else:
                done = fmt.size(progress.downloaded_bytes)
                self.percent.configure(text="")
            data = fmt.join(
                done,
                fmt.speed(progress.speed) if progress.speed else "",
                fmt.remaining(progress.eta),
            )
            self.data.set(data, theme.DIM)
        else:
            self.percent.configure(text="")
            if job.status == JobStatus.POSTPROCESSING.value:
                self.data.set(job.stage_text or "обработка…", theme.DIM)
            elif job.status == JobStatus.FAILED.value:
                first_line = (job.error or "неизвестная ошибка").strip().splitlines()[0]
                self.data.set(fmt.join(first_line, "подробнее — щелчок по строке"), theme.ERR)
            elif job.status == JobStatus.COMPLETED.value and job.output_files:
                self.data.set(fmt.join(_describe(job), Path(job.output_files[0]).name), theme.DIM)
            else:
                self.data.set(fmt.join(_describe(job), job.output_dir), theme.DIM)

        if job.status == JobStatus.FAILED.value:
            self.set_state("error")
        elif job.is_active:
            self.set_state("current")
        else:
            self.set_state("normal")
        self.set_progress(job.progress if running else None)

        self._show(self.cancel_button, job.status in (JobStatus.PENDING.value, *_ACTIVE))
        self._show(self.folder_button, job.status == JobStatus.COMPLETED.value)
        self._show(self.log_button, bool(job.log_path))
        self._show(self.remove_button, not job.is_active)

    @staticmethod
    def _show(widget, visible: bool) -> None:
        if visible:
            widget.grid()
        else:
            widget.grid_remove()


class QueuePage(ScrollPage):
    def __init__(
        self,
        master,
        app,
        *,
        loader: ThumbnailLoader,
        on_error_details: Callable[[Job], None],
    ) -> None:
        super().__init__(master)
        self.app = app
        self.loader = loader
        self.on_error_details = on_error_details
        self._rows: dict[str, _JobRow] = {}
        self._order: list[str] = []

        self.heading = PageTitle(self.body, "Очередь")
        self.heading.grid(row=0, column=0, sticky="ew", pady=(40, 18))
        self.heading.add_action(Btn(self.heading.actions, "Открыть папку", self._open_downloads))
        self.clear_button = Btn(
            self.heading.actions, "Очистить завершённые", self._clear_finished, icon="×"
        )
        self.heading.add_action(self.clear_button)

        self.empty = DashedBox(
            self.body,
            "Очередь пуста\nдобавьте ссылку на главной и нажмите «Скачать»",
        )
        self.empty.grid(row=1, column=0, sticky="ew")
        self.panel = Panel(self.body)
        self.panel.grid(row=2, column=0, sticky="ew")
        self.list = Column(self.panel)
        self.list.grid(row=0, column=0, sticky="ew", padx=1, pady=3)

        self.hint = Para(self.body, "", font=theme.sans(12), color=theme.FAINT, max_width=760)
        self.hint.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        self.refresh_queue()

    # -- список --------------------------------------------------------------
    def refresh_queue(self) -> None:
        jobs = list(self.app.queue.jobs)
        order = [job.id for job in jobs]
        if order != self._order:
            self._rebuild(jobs)
        else:
            for job in jobs:
                self._rows[job.id].job = job
                self._rows[job.id].refresh()
        self._update_summary(jobs)

    def _rebuild(self, jobs: list[Job]) -> None:
        old = self._rows
        self._rows = {}
        for job_id, row in old.items():
            if job_id not in {job.id for job in jobs}:
                row.destroy()
        # Строки пересобираются целиком: порядок в сетке проще задать заново.
        for child in self.list.winfo_children():
            if not isinstance(child, _JobRow):
                child.destroy()
        self.list.rewind()
        for index, job in enumerate(jobs):
            if index:
                self.list.add(hline(self.list))
            row = old.get(job.id) or _JobRow(self.list, self, job)
            row.job = job
            self.list.add(row)
            self._rows[job.id] = row
            row.refresh()
        self._order = [job.id for job in jobs]

        if jobs:
            self.empty.grid_remove()
            self.panel.grid()
        else:
            self.panel.grid_remove()
            self.empty.grid()

    def update_job(self, job: Job, info: ProgressInfo | None = None) -> None:
        row = self._rows.get(job.id)
        if row is None:
            self.refresh_queue()
            return
        if info is not None:
            job.progress = info.fraction
            row.last_progress = info
        row.refresh()
        self._update_summary(self.app.queue.jobs)

    def _update_summary(self, jobs: list[Job]) -> None:
        total = len(jobs)
        done = sum(1 for job in jobs if job.status == JobStatus.COMPLETED.value)
        active = sum(1 for job in jobs if job.is_active)
        waiting = sum(1 for job in jobs if job.status == JobStatus.PENDING.value)
        failed = sum(1 for job in jobs if job.status == JobStatus.FAILED.value)
        parallel = self.app.settings.parallel_jobs
        self.heading.subtitle.configure(
            text=fmt.join(
                fmt.plural(total, "загрузка", "загрузки", "загрузок"),
                f"готово {done}",
                f"в работе {active}",
                f"ждут {waiting}" if waiting else "",
                f"с ошибкой {failed}" if failed else "",
                f"одновременно {parallel}",
            )
        )
        self.clear_button.set_enabled(any(job.is_finished for job in jobs))
        folder = self.app.settings.output_directory or str(self.app.filesystem.default_download_dir())
        self.hint.configure(
            text=(
                f"Загрузки идут по очереди, одновременно — {parallel} (меняется в настройках). "
                f"Файлы сохраняются в {folder}, если на главной не выбрана другая папка."
            )
        )

    # -- действия ------------------------------------------------------------
    def row_clicked(self, job: Job) -> None:
        if job.status == JobStatus.FAILED.value:
            self.on_error_details(job)
        elif job.status == JobStatus.COMPLETED.value:
            self.app.open_output_folder(job)

    def cancel(self, job: Job) -> None:
        # Для активного задания cancel() делает terminate()+wait() (до
        # нескольких секунд) — не блокируем этим поток Tk.
        threading.Thread(target=self.app.queue.cancel, args=(job.id,), daemon=True).start()

    def remove(self, job: Job) -> None:
        self.app.queue.remove(job.id)
        self.refresh_queue()

    def _clear_finished(self) -> None:
        self.app.queue.clear_finished()
        self.refresh_queue()

    def _open_downloads(self) -> None:
        folder = self.app.settings.output_directory or str(self.app.filesystem.default_download_dir())
        open_folder(Path(folder))

    def open_log(self, job: Job) -> None:
        if job.log_path:
            _open_path(Path(job.log_path))

    def copy_to_clipboard(self, value: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(value)
