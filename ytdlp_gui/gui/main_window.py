"""Главное окно приложения.

Каркас — как у «Стемницы» (design-system §6): шапка 58 px с логотипом,
вкладками «Главная · Очередь · Настройки» и чипами состояния; у каждой
вкладки своя прокрутка и подвал; уведомления — в левом нижнем углу.
С ``Application`` окно, как и раньше, общается через шину событий.
"""

from __future__ import annotations

import logging
import queue
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from ..app.application import Application
from ..app.events import Event
from ..app.state import APP_VERSION
from ..core.models import Job, JobStatus, ProgressInfo
from ..core.updates import ReleaseInfo
from . import fmt, theme
from .tabs.home_tab import HomePage
from .tabs.queue_tab import QueuePage
from .tabs.settings_tab import HOTKEYS, SettingsPage
from .widgets.dialogs import text_dialog
from .widgets.header import Header
from .widgets.release_notes_dialog import ReleaseNotesDialog
from .widgets.thumbnail_view import ThumbnailLoader
from .widgets.toast import ToastStack

log = logging.getLogger(__name__)

WINDOW_SIZE = (1440, 920)
WINDOW_MIN_SIZE = (1000, 640)

TABS = (("home", "Главная"), ("queue", "Очередь"), ("settings", "Настройки"))
TAB_KEYS = tuple(key for key, _title in TABS)

HELP_TEXT = (
    "Как скачать\n"
    "1. Вставьте ссылку на видео или плейлист в поле на главной и нажмите Enter.\n"
    "2. Выберите видео в списке ссылок — справа появятся его форматы, звуковые "
    "дорожки и субтитры.\n"
    "3. Решите, что скачать: видео со звуком или только звук, — и выберите качество.\n"
    "4. Нажмите «Скачать видео» (Ctrl+Enter). Ход загрузки виден под кнопкой и на "
    "вкладке «Очередь».\n\n"
    "Кнопка «Команда» показывает, с какими параметрами запустится yt-dlp. Субтитры "
    "можно вшить в видео, сохранить отдельным файлом или и то, и другое.\n\n"
    "Для склейки видео со звуком, извлечения звука, субтитров и обложек нужен FFmpeg — "
    "путь к нему задаётся в «Настройках».\n\n"
    "Горячие клавиши\n"
    + "\n".join(f"{keys:<18}{description}" for keys, description in HOTKEYS)
)

#: Сочетания с Ctrl. На Windows смотрим на виртуальный код клавиши, а не на
#: символ: при русской раскладке Ctrl+L приходит как «Cyrillic_de».
_WINDOWS_KEYCODES = {
    76: "l", 85: "u", 86: "v", 48: "0", 96: "0", 49: "1", 50: "2", 51: "3",
    187: "plus", 107: "plus", 189: "minus", 109: "minus",
}
_KEYSYMS = {
    "l": "l", "u": "u", "v": "v", "0": "0", "kp_0": "0", "1": "1", "2": "2", "3": "3",
    "plus": "plus", "equal": "plus", "kp_add": "plus", "minus": "minus", "kp_subtract": "minus",
}

#: Как часто обновлять чип скорости в шапке (§11.4: опрос раз в 500 мс).
SPEED_CHIP_INTERVAL = 0.5


def _short_version(version: str) -> str:
    """«9.0.1-full_build-www.gyan.dev» → «9.0.1»."""
    head = version.split("-")[0]
    return head if any(char.isdigit() for char in head) else version[:16]


def _is_text_input(window) -> bool:
    try:
        widget = window.focus_get()
    except (KeyError, tk.TclError):  # фокус во всплывающем меню Tk
        return False
    return isinstance(widget, (tk.Entry, tk.Text))


class MainWindow(ctk.CTk):
    """Окно верхнего уровня."""

    def __init__(self, app: Application) -> None:
        # Тема ставится до первого виджета: CustomTkinter читает цвета из
        # ThemeManager.theme в момент создания, а не при отрисовке.
        theme.install()
        super().__init__()

        self.app = app
        self.tr = app.translator
        # События очереди и загрузки публикуются из фоновых потоков.
        # Tk.after() из чужого потока не гарантирует, что цикл событий
        # вовремя проснётся: колбэки копятся и применяются разом (прогресс
        # «стоит», а потом прыгает). Поэтому события кладутся в
        # потокобезопасную очередь и разбираются только в потоке Tk.
        self._event_queue: queue.Queue = queue.Queue()
        self._update_dialog: ReleaseNotesDialog | None = None
        self._pending_release: ReleaseInfo | None = None
        self._manual_update_check = False
        self._speeds: dict[str, float] = {}
        self._speed_chip_at = 0.0
        self._current_page = ""
        self._closing = False
        self._settings_page: SettingsPage | None = None
        self._update_status: tuple[str, str] | None = None

        theme.install_fonts(self)
        self._scale = theme.apply_scale(getattr(app.settings, "ui_scale", 1.0))

        self.title(self.tr("app.title", "yt-dlp GUI"))
        self._set_initial_geometry()
        self.minsize(*WINDOW_MIN_SIZE)
        theme.style_window(self)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.toasts = ToastStack(self)
        self.loader = ThumbnailLoader(app, self._post)
        self._build_header()
        self._build_pages()

        self._subscribe()
        self._bind_shortcuts()

        self.show_page("home")
        self._sync_tool_chips()
        self._sync_footers()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(200, self.app.initialize)
        self.after(30, self._pump_events)

    def _set_initial_geometry(self) -> None:
        scale = theme.widget_scale(self)
        width = min(WINDOW_SIZE[0], int(self.winfo_screenwidth() / scale) - 80)
        height = min(WINDOW_SIZE[1], int(self.winfo_screenheight() / scale) - 120)
        width, height = max(width, WINDOW_MIN_SIZE[0]), max(height, WINDOW_MIN_SIZE[1])
        self.geometry(f"{width}x{height}")
        #: Логический размер окна при запуске — по нему страницы делают первую раскладку.
        self.initial_size = (width, height - theme.HEADER_HEIGHT)

    def report_callback_exception(self, exc, val, tb) -> None:
        """Необработанное исключение из колбэка виджета.

        Стандартная реализация Tk пишет в sys.stderr, которого в собранном
        .exe без консоли нет: кнопка просто «ничего не делает». Поэтому
        traceback уходит в файловый лог, а пользователь видит диалог.

        Пока окно закрывается, Tk ещё дёргает обработчики уже разобранных
        виджетов (Configure страниц, цикл полос прокрутки CTkTextbox). Такие
        ошибки безвредны — они только пишутся в журнал, без диалога.
        """
        if getattr(self, "_closing", False):
            log.debug("Ошибка обработчика во время закрытия окна", exc_info=(exc, val, tb))
            return
        log.error("Необработанное исключение в обработчике интерфейса", exc_info=(exc, val, tb))
        try:
            messagebox.showerror(
                "Неожиданная ошибка",
                f"Произошла непредвиденная ошибка:\n\n{val}\n\nПодробности записаны в журнал.",
            )
        except Exception:  # noqa: BLE001 - если даже диалог не показать, не роняем приложение
            pass

    # -- построение ---------------------------------------------------------
    def _build_header(self) -> None:
        self.header = Header(
            self,
            title=self.tr("app.title", "yt-dlp GUI"),
            subtitle="загрузка видео и звука",
            tabs=TABS,
            on_select=self.show_page,
        )
        self.header.grid(row=0, column=0, sticky="ew")
        self.header.add_chip("ytdlp", priority=0)
        self.header.add_chip("ffmpeg", priority=1)
        self.header.add_chip("speed", priority=2)

    def _build_pages(self) -> None:
        self.home = HomePage(
            self,
            self.app,
            loader=self.loader,
            post=self._post,
            toast=self.toast,
            on_enqueue=self.enqueue,
            on_cancel=self.cancel_job,
            on_show_settings=lambda: self.show_page("settings"),
        )
        self.queue_page = QueuePage(
            self, self.app, loader=self.loader, on_error_details=self.show_error
        )
        self.pages = {"home": self.home, "queue": self.queue_page}

    @property
    def settings_page(self) -> SettingsPage:
        """Вкладка настроек строится при первом обращении.

        Это самая тяжёлая страница: построенная заранее и скрытая, она
        добавляла к запуску больше секунды раскладки.
        """
        if self._settings_page is None:
            self.configure(cursor="watch")
            self.update_idletasks()
            page = SettingsPage(
                self,
                self.app,
                on_settings_changed=self.on_settings_changed,
                on_defaults_changed=self.home.apply_defaults,
                on_check_updates=self.check_updates,
                on_show_logs=self.show_logs,
            )
            self._settings_page = page
            self.pages["settings"] = page
            page.footer.set_versions(self._footer_versions())
            if self._update_status is not None:
                page.set_update_status(*self._update_status)
            self.configure(cursor="")
        return self._settings_page

    def _set_update_status(self, message: str, severity: str) -> None:
        """Строка проверки обновлений: запоминается до постройки настроек."""
        self._update_status = (message, severity)
        if self._settings_page is not None:
            self._settings_page.set_update_status(message, severity)

    # -- навигация ------------------------------------------------------------
    def show_page(self, key: str) -> None:
        if key not in TAB_KEYS:
            return
        page = self.settings_page if key == "settings" else self.pages[key]
        if key != self._current_page:
            if self._current_page:
                self.pages[self._current_page].grid_remove()
            page.grid(row=1, column=0, sticky="nsew")
            self._current_page = key
        self.header.select(key)
        self.toasts.layout()

    # -- события приложения ---------------------------------------------------
    def _post(self, handler, *args) -> None:
        """Кладёт вызов в потокобезопасную очередь — можно звать из любого потока."""
        self._event_queue.put((handler, args))

    def _pump_events(self) -> None:
        """Разбирает накопленные события; работает только в потоке Tk."""
        while True:
            try:
                handler, args = self._event_queue.get_nowait()
            except queue.Empty:
                break
            try:
                handler(*args)
            except Exception:  # noqa: BLE001 - один обработчик не должен рушить остальные
                log.exception("Ошибка обработчика события интерфейса")
        if not self._closing:
            self.after(30, self._pump_events)

    def _subscribe(self) -> None:
        bus = self.app.bus
        post = self._post
        bus.subscribe(Event.ITEMS_CHANGED, lambda items: post(self.home.set_items, list(items)))
        bus.subscribe(Event.FETCH_STARTED, lambda url: post(self.home.fetch_started, url))
        bus.subscribe(
            Event.FETCH_FINISHED, lambda info, added: post(self.home.fetch_finished, info, added)
        )
        bus.subscribe(Event.TOOLS_READY, lambda binaries: post(self._tools_ready))
        bus.subscribe(Event.YTDLP_MISSING, lambda: post(self._ytdlp_missing))
        bus.subscribe(Event.JOB_ADDED, lambda job: post(self._queue_changed))
        bus.subscribe(Event.JOB_STARTED, lambda job: post(self._job_started, job))
        bus.subscribe(Event.JOB_PROGRESS, lambda job, info: post(self._job_progress, job, info))
        bus.subscribe(Event.JOB_STAGE, lambda job, stage: post(self._job_stage, job, stage))
        bus.subscribe(Event.JOB_FINISHED, lambda job: post(self._job_finished, job))
        bus.subscribe(Event.QUEUE_CHANGED, lambda: post(self._queue_changed))
        bus.subscribe(Event.QUEUE_IDLE, lambda: post(self._queue_idle))
        bus.subscribe(Event.UPDATE_CHECK_STARTED, lambda: post(self._update_check_started))
        bus.subscribe(Event.UPDATE_AVAILABLE, lambda info: post(self._update_available, info))
        bus.subscribe(Event.UPDATE_UP_TO_DATE, lambda version: post(self._update_up_to_date, version))
        bus.subscribe(
            Event.UPDATE_HISTORY,
            lambda releases, only_new: post(self._update_history, releases, only_new),
        )
        bus.subscribe(Event.UPDATE_PROGRESS, lambda done, total: post(self._update_progress, done, total))
        bus.subscribe(Event.UPDATE_INSTALLED, lambda info, path: post(self._update_installed, info, path))
        bus.subscribe(Event.UPDATE_FAILED, lambda message: post(self._update_failed, message))

    def _bind_shortcuts(self) -> None:
        self.bind("<Delete>", self._on_delete)
        self.bind("<Control-Return>", lambda _e: self.start_download())
        self.bind("<Escape>", lambda _e: self.cancel_active())
        self.bind("<F1>", lambda _e: self.show_help())
        self.bind("<Control-KeyPress>", self._on_ctrl_key)

    def _on_ctrl_key(self, event) -> str | None:
        if sys.platform == "win32":
            key = _WINDOWS_KEYCODES.get(event.keycode)
        else:
            key = _KEYSYMS.get(str(event.keysym).lower())
        if key is None:
            return None
        if key == "v":
            # В поле ввода Ctrl+V — обычная вставка.
            if _is_text_input(self):
                return None
            self.show_page("home")
            self.home.paste_url()
        elif key in ("1", "2", "3"):
            self.show_page(TABS[int(key) - 1][0])
        elif key == "l":
            self.show_logs()
        elif key == "u":
            self.check_updates()
        elif key == "plus":
            self.zoom_by(0.1)
        elif key == "minus":
            self.zoom_by(-0.1)
        elif key == "0":
            self.set_ui_scale(1.0)
        return "break"

    def _on_delete(self, _event=None) -> None:
        if not _is_text_input(self) and self._current_page == "home":
            self.home.remove_selected()

    # -- масштаб интерфейса ---------------------------------------------------
    def set_ui_scale(self, scale: float, *, save: bool = True) -> float:
        """Применяет масштаб ко всем окнам и запоминает его в настройках."""
        self._scale = theme.apply_scale(scale)
        if save and getattr(self.app.settings, "ui_scale", None) != self._scale:
            self.app.update_settings(ui_scale=self._scale)
        if self._settings_page is not None:
            self._settings_page.sync_ui_scale(self._scale)
        self.after(50, self.toasts.layout)
        return self._scale

    def zoom_by(self, delta: float) -> None:
        self.set_ui_scale(self._scale + delta)

    def on_settings_changed(self) -> None:
        """Настройки изменились: масштаб применяется сразу."""
        scale = theme.normalize_scale(getattr(self.app.settings, "ui_scale", 1.0))
        if scale != self._scale:
            self.set_ui_scale(scale, save=False)

    # -- уведомления и шапка --------------------------------------------------
    def toast(self, message: str, kind: str = "info", *, action: str = "", command=None) -> None:
        self.toasts.show(message, kind, action=action, command=command)

    def _sync_tool_chips(self) -> None:
        binaries = self.app.ytdlp.binaries
        to_settings = lambda: self.show_page("settings")  # noqa: E731
        if self._pending_release is not None:
            self.header.set_chip(
                "ytdlp",
                f"yt-dlp {binaries.ytdlp_version} · есть обновление",
                "warn",
                command=self._show_pending_release,
            )
        elif binaries.ytdlp_available and binaries.ytdlp_version:
            self.header.set_chip("ytdlp", f"yt-dlp {binaries.ytdlp_version}", "on", command=None)
        elif binaries.ytdlp_available:
            self.header.set_chip("ytdlp", "yt-dlp", "on", command=None)
        else:
            self.header.set_chip("ytdlp", "нет yt-dlp", "error", command=to_settings)

        if binaries.ffmpeg_available:
            version = _short_version(binaries.ffmpeg_version) if binaries.ffmpeg_version else ""
            self.header.set_chip("ffmpeg", fmt.join("ffmpeg", version), "on", command=None)
        else:
            self.header.set_chip("ffmpeg", "нет ffmpeg", "warn", command=to_settings)
        self.home.set_tools(binaries.ffmpeg_available)

    def _footer_versions(self) -> str:
        binaries = self.app.ytdlp.binaries
        return fmt.join(
            f"yt-dlp gui {APP_VERSION}",
            f"yt-dlp {binaries.ytdlp_version}" if binaries.ytdlp_version else "",
            f"ffmpeg {_short_version(binaries.ffmpeg_version)}" if binaries.ffmpeg_version else "",
        )

    def _sync_footers(self) -> None:
        value = self._footer_versions()
        for page in self.pages.values():
            page.footer.set_versions(value)

    def _sync_activity(self) -> None:
        """Счётчик на вкладке, чип скорости и задание в блоке прогресса."""
        jobs = list(self.app.queue.jobs)
        active = [job for job in jobs if job.is_active]
        waiting = sum(1 for job in jobs if job.status == JobStatus.PENDING.value)
        self.header.set_count("queue", len(active) + waiting)

        shown = self.home.shown_job
        if shown is None or not shown.is_active:
            shown = max(active, key=lambda job: job.started_at or datetime.min, default=None)
        self.home.show_job(shown)

        for job_id in list(self._speeds):
            if not any(job.id == job_id for job in active):
                del self._speeds[job_id]
        self._update_speed_chip(force=True)

    def _update_speed_chip(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._speed_chip_at < SPEED_CHIP_INTERVAL:
            return
        self._speed_chip_at = now
        running = any(job.is_active for job in self.app.queue.jobs)
        total = sum(self._speeds.values())
        if running:
            self.header.set_chip("speed", f"↓ {fmt.speed(total)}" if total else "↓ загрузка")
        else:
            self.header.set_chip("speed", "", visible=False)

    # -- инструменты ----------------------------------------------------------
    def _tools_ready(self) -> None:
        if self._settings_page is not None:
            self._settings_page.update_tools_status()
        self._sync_tool_chips()
        self._sync_footers()

    def _ytdlp_missing(self) -> None:
        self._sync_tool_chips()
        if self._settings_page is not None:
            self._settings_page.update_tools_status()
        self.toast(
            "yt-dlp не найден. Укажите путь к yt-dlp.exe в настройках — сама программа его не скачивает.",
            "error",
            action="Настройки",
            command=lambda: self.show_page("settings"),
        )
        self.show_page("settings")

    # -- очередь --------------------------------------------------------------
    def _queue_changed(self) -> None:
        self.queue_page.refresh_queue()
        self._sync_activity()

    def _job_started(self, job: Job) -> None:
        self.queue_page.update_job(job)
        self._sync_activity()

    def _job_progress(self, job: Job, info: ProgressInfo) -> None:
        self.queue_page.update_job(job, info)
        self.home.job_progress(job, info)
        if info.speed:
            self._speeds[job.id] = info.speed
        self._update_speed_chip()

    def _job_stage(self, job: Job, stage: str) -> None:
        self._speeds.pop(job.id, None)
        self.queue_page.update_job(job)
        self.home.job_stage(job, stage)

    def _job_finished(self, job: Job) -> None:
        self._speeds.pop(job.id, None)
        self.queue_page.update_job(job)
        self.queue_page.refresh_queue()
        if job.status == JobStatus.COMPLETED.value:
            names = [Path(path).name for path in job.output_files]
            self.toast(
                fmt.join("Готово", names[0] if names else job.label),
                "ok",
                action="Открыть папку",
                command=lambda: self.app.open_output_folder(job),
            )
        elif job.status == JobStatus.FAILED.value:
            self.toast(
                fmt.join("Ошибка загрузки", job.label),
                "error",
                action="Подробнее",
                command=lambda: self.show_error(job),
            )
        elif job.status == JobStatus.CANCELLED.value:
            self.toast(fmt.join("Остановлено", job.label), "warn")
        self._sync_activity()

    def _queue_idle(self) -> None:
        self._sync_activity()
        self.home.refresh_status()

    def start_download(self) -> None:
        self.home.start()

    def enqueue(self, job: Job) -> None:
        self.app.enqueue(job)
        self.queue_page.refresh_queue()
        if job.status == JobStatus.PENDING.value:
            self.toast(
                fmt.join("В очереди", job.label),
                action="Очередь",
                command=lambda: self.show_page("queue"),
            )
        self._sync_activity()

    def cancel_job(self, job: Job) -> None:
        # QueueManager.cancel() для активного задания делает terminate() и
        # ждёт до нескольких секунд — не блокируем этим поток Tk.
        threading.Thread(target=self.app.queue.cancel, args=(job.id,), daemon=True).start()

    def cancel_active(self) -> None:
        job = self.home.shown_job
        if job is None or not job.is_active:
            job = next((item for item in self.app.queue.jobs if item.is_active), None)
        if job is not None:
            self.cancel_job(job)
            self.toast(fmt.join("Останавливаю", job.label), "warn")

    # -- обновления yt-dlp ---------------------------------------------------
    def check_updates(self) -> None:
        self._manual_update_check = True
        self.app.check_updates()

    def _update_check_started(self) -> None:
        self._set_update_status("Проверяю обновления…", "busy")

    def _update_available(self, release: ReleaseInfo) -> None:
        self._pending_release = release
        self._manual_update_check = False
        self._sync_tool_chips()
        current = self.app.ytdlp.binaries.ytdlp_version or "неизвестна"
        self._set_update_status(
            f"Доступна версия {release.version_text}, установлена {current}.", "warning"
        )
        self._show_pending_release()

    def _show_pending_release(self) -> None:
        release = self._pending_release
        if release is None:
            return
        current = self.app.ytdlp.binaries.ytdlp_version or "неизвестна"
        self._show_release_dialog(
            [release],
            title="Доступно обновление",
            subtitle=f"Установлена версия yt-dlp {current}.",
        )

    def _update_up_to_date(self, version: str) -> None:
        message = f"Установлена последняя версия yt-dlp — {version or '—'}."
        self._set_update_status(message, "ok")
        if self._manual_update_check:
            self.toast(message, "ok")
        self._manual_update_check = False

    def _update_history(self, releases, only_new: bool) -> None:
        current = self.app.ytdlp.binaries.ytdlp_version or "неизвестна"
        if self._settings_page is not None:
            self._settings_page.refresh_update_status()
        self._show_release_dialog(
            list(releases),
            title="Доступно обновление" if only_new else "История изменений yt-dlp",
            subtitle=f"Установлена версия yt-dlp {current}.",
            show_history=only_new,
        )

    def _show_release_dialog(
        self, releases, *, title: str, subtitle: str, show_history: bool = True
    ) -> None:
        """Показывает окно с описанием релизов; второе окно не открывает."""
        dialog = self._update_dialog
        if dialog is not None and dialog.winfo_exists():
            dialog.set_heading(title)
            dialog.set_subtitle(subtitle)
            dialog.set_history_visible(show_history)
            dialog.set_releases(releases)
            dialog.lift()
            return
        self._update_dialog = ReleaseNotesDialog(
            self,
            releases,
            title=title,
            subtitle=subtitle,
            on_download=self.app.install_update,
            on_history=(
                (lambda: self.app.load_release_history(limit=10, only_new=False))
                if show_history
                else None
            ),
        )

    def _update_progress(self, done: int, total: int) -> None:
        if self._update_dialog is not None and self._update_dialog.winfo_exists():
            self._update_dialog.show_progress(done, total)

    def _update_installed(self, release: ReleaseInfo, path: str) -> None:
        self._pending_release = None
        message = f"yt-dlp обновлён до {release.version_text}"
        self._set_update_status(f"{message}: {path}", "ok")
        if self._settings_page is not None:
            self._settings_page.update_tools_status()
        self._sync_tool_chips()
        self._sync_footers()
        if self._update_dialog is not None and self._update_dialog.winfo_exists():
            self._update_dialog.show_result(message, ok=True)
        else:
            self.toast(message + ".", "ok")

    def _update_failed(self, message: str) -> None:
        self._manual_update_check = False
        self._set_update_status(message, "error")
        if self._update_dialog is not None and self._update_dialog.winfo_exists():
            self._update_dialog.show_result(message, ok=False)
        else:
            self.toast(f"Обновление yt-dlp: {message}", "error")

    # -- диалоги -------------------------------------------------------------
    def show_error(self, job: Job) -> None:
        left = []
        if job.log_path:
            left.append(("Журнал", lambda: self.queue_page.open_log(job)))
        left.append(("Копировать", lambda: self.queue_page.copy_to_clipboard(job.error or "")))
        text_dialog(
            self,
            "Ошибка загрузки",
            job.error or "Неизвестная ошибка",
            subtitle=job.label,
            size=(720, 480),
            left_buttons=left,
        )

    def show_logs(self) -> None:
        path = self.app.store.logs_dir / "ytdlp.log"
        try:
            content = path.read_text(encoding="utf-8", errors="replace")[-200000:]
        except OSError as exc:
            content = f"Журнал недоступен: {exc}"
        text_dialog(
            self,
            "Журнал yt-dlp",
            content,
            subtitle=str(path),
            mono=True,
            wrap="none",
            size=(960, 640),
        )

    def show_help(self) -> None:
        text_dialog(
            self,
            "Справка",
            HELP_TEXT,
            size=(680, 640),
            mono=True,
            info=f"yt-dlp gui {APP_VERSION}",
        )

    # -- завершение ----------------------------------------------------------
    def on_close(self) -> None:
        if self.app.queue.active_count and not messagebox.askyesno(
            "Выход", "Есть незавершённые загрузки. Прервать их и выйти?"
        ):
            return
        # shutdown() останавливает процессы yt-dlp (terminate + ожидание) —
        # в фоновом потоке, чтобы окно закрылось сразу. Поток не daemon:
        # Python дождётся его перед выходом, и очистка доведётся до конца.
        threading.Thread(target=self.app.shutdown).start()
        self.destroy()

    def destroy(self) -> None:
        self._closing = True
        super().destroy()

