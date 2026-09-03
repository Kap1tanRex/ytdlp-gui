"""Главное окно приложения.

Компоновка повторяет ZapretGUI: слева — панель навигации по разделам,
справа — рабочая область (ввод ссылки, список видео, экран раздела),
внизу — строка состояния с индикаторами. Разделы — те же, что раньше
были вкладками ``CTkTabview``; их содержимое, обработчики событий и
работа с ``Application`` не изменились.
"""

from __future__ import annotations

import logging
import queue
import threading
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from ..app.application import Application
from ..app.events import Event
from ..app.state import APP_VERSION
from ..core.models import Job, JobStatus, ProgressInfo, VideoInfo
from ..core.updates import ReleaseInfo
from . import theme
from .tabs.audio_tab import AudioTab
from .tabs.info_tab import InfoTab
from .tabs.queue_tab import QueueTab
from .tabs.settings_tab import SettingsTab
from .tabs.video_tab import VideoTab
from .widgets.design import Card, body_label, button, muted_label, primary_button, separator
from .widgets.dialogs import Dialog, text_dialog
from .widgets.item_list import ItemList
from .widgets.progress_bar import ProgressPanel
from .widgets.release_notes_dialog import ReleaseNotesDialog
from .widgets.sidebar import Sidebar
from .widgets.status_strip import StatusStrip

log = logging.getLogger(__name__)

WINDOW_MIN_SIZE = (1060, 720)
WINDOW_SIZE = (1280, 880)

#: Порядок разделов в боковой панели.
PAGE_KEYS = ("video", "audio", "info", "queue", "settings")

HELP_TEXT = (
    "Порядок работы:\n"
    "1. Вставьте ссылку на видео/плейлист и нажмите Enter.\n"
    "2. Выберите видео в списке — в разделе «Информация» появится превью и список форматов.\n"
    "3. В разделе «Видео» выберите качество, звуковую дорожку и субтитры, "
    "либо в разделе «Аудио» — формат и битрейт для извлечения звука.\n"
    "4. Проверьте команду кнопкой «Показать команду yt-dlp».\n"
    "5. Нажмите «Скачать» — загрузка появится в очереди.\n\n"
    "Субтитры можно вшить в видео, сохранить отдельным файлом или сделать и то, и другое.\n\n"
    "Горячие клавиши:\n"
    "Enter                Добавить ссылку\n"
    "Delete               Удалить выбранное видео\n"
    "Ctrl+Enter           Запустить текущий раздел\n"
    "Esc                  Отмена текущей загрузки\n"
    "Ctrl+L               Лог\n"
    "Ctrl+U               Проверить обновления yt-dlp\n"
    "Ctrl+плюс / минус    Масштаб интерфейса\n"
    "Ctrl+0               Масштаб 100 %\n"
    "F1                   Справка\n\n"
    "Для слияния видео+аудио, извлечения аудио и субтитров нужен FFmpeg "
    "(путь указывается в разделе «Настройки»)."
)


class MainWindow(ctk.CTk):
    """Окно верхнего уровня."""

    def __init__(self, app: Application) -> None:
        # Тема должна быть установлена до создания первого виджета: цвета
        # окна и всех элементов CustomTkinter читает из ThemeManager.theme
        # в момент создания, а не при отрисовке.
        theme.install()
        super().__init__()

        self.app = app
        self.tr = app.translator
        self._active_job: Job | None = None
        # События очереди/загрузки публикуются из фоновых потоков
        # (QueueManager запускает каждое задание в своём threading.Thread).
        # Tk.after(), вызванный из чужого потока, не гарантирует, что
        # Tcl-нотификатор вовремя разбудит mainloop — на практике колбэки
        # копятся и применяются все разом, когда что-то другое встряхивает
        # цикл событий (типично — по завершении задания). Из-за этого
        # прогресс-бар «стоял на месте» и скачкообразно обновлялся в
        # самом конце. Поэтому события кладутся в потокобезопасную
        # очередь и разбираются только из потока Tk, через self.after(),
        # запланированный сам собой изнутри уже выполняющегося колбэка.
        self._event_queue: queue.Queue = queue.Queue()
        self._update_dialog: ReleaseNotesDialog | None = None

        theme.resolve_fonts(self)
        theme.apply_appearance(app.settings.theme)
        self._scale = theme.apply_scale(getattr(app.settings, "ui_scale", 1.0))

        self.title(f"{self.tr('app.title', 'yt-dlp GUI')} {APP_VERSION}")
        self.geometry(f"{WINDOW_SIZE[0]}x{WINDOW_SIZE[1]}")
        self.minsize(*WINDOW_MIN_SIZE)

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_content()
        self._build_pages()
        self._build_status()

        self._subscribe()
        self._bind_shortcuts()

        self.show_page("video")
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(200, self.app.initialize)
        self.after(30, self._pump_events)

    def report_callback_exception(self, exc, val, tb) -> None:
        """Перехватывает необработанные исключения из любых колбэков
        виджетов (command=, bind(...) и т.п.).

        Стандартная реализация Tk просто пишет в sys.stderr. В собранном
        .exe (--windowed, без консоли) sys.stderr отсутствует (None) —
        падение окажется просто незаметным для пользователя: кнопка
        «ничего не делает», а причина нигде не видна. Здесь вместо этого
        пишем полный traceback в файловый лог и показываем диалог.
        """
        log.error("Необработанное исключение в обработчике интерфейса", exc_info=(exc, val, tb))
        try:
            messagebox.showerror(
                "Неожиданная ошибка",
                f"Произошла непредвиденная ошибка:\n\n{val}\n\nПодробности записаны в лог.",
            )
        except Exception:  # noqa: BLE001 - если даже диалог не показать, не роняем приложение
            pass

    # -- построение ---------------------------------------------------------
    def _build_sidebar(self) -> None:
        titles = [
            self.tr("tab.video", "Видео"),
            self.tr("tab.audio", "Аудио"),
            self.tr("tab.info", "Информация"),
            self.tr("tab.queue", "Очередь"),
            self.tr("tab.settings", "Настройки"),
        ]
        self.sidebar = Sidebar(
            self,
            title=self.tr("app.title", "yt-dlp GUI"),
            subtitle=self.tr("app.subtitle", "Загрузка видео и аудио с YouTube и других сайтов"),
            items=titles,
            on_select=self._on_nav_select,
        )
        self.sidebar.grid(row=0, column=0, rowspan=2, sticky="ns")
        self.sidebar.set_version(f"{self.tr('app.title', 'yt-dlp GUI')} {APP_VERSION}")
        self.sidebar.set_help(f"{self.tr('app.help', 'Справка')} (F1)", self.show_help)

    def _build_content(self) -> None:
        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(1, weight=1)

        self._build_import_card()

        self.page_container = ctk.CTkFrame(self.content, fg_color="transparent")
        self.page_container.grid(
            row=1, column=0, sticky="nsew", padx=theme.GAP["xl"], pady=(0, theme.GAP["md"])
        )
        self.page_container.grid_columnconfigure(0, weight=1)
        self.page_container.grid_rowconfigure(0, weight=1)

    def _build_import_card(self) -> None:
        """Ввод ссылки и список добавленных видео — одна карточка сверху.

        Она остаётся видимой в любом разделе: это вход в приложение, от
        выбранного здесь видео зависит содержимое всех остальных экранов.
        """
        card = Card(self.content, self.tr("import.title", "Ссылки"))
        card.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=theme.GAP["xl"],
            pady=(theme.GAP["lg"], theme.GAP["md"]),
        )
        body = card.body
        body.grid_columnconfigure(0, weight=1)

        row = ctk.CTkFrame(body, fg_color="transparent")
        row.grid(row=0, column=0, sticky="ew")
        row.grid_columnconfigure(0, weight=1)

        self.url_entry = ctk.CTkEntry(
            row,
            height=36,
            placeholder_text=self.tr(
                "import.url_placeholder",
                "Вставьте ссылку на видео/плейлист YouTube и нажмите Enter",
            ),
        )
        self.url_entry.grid(row=0, column=0, sticky="ew", padx=(0, theme.GAP["sm"]))
        self.url_entry.bind("<Return>", lambda _e: self.add_url())

        primary_button(
            row, self.tr("import.add_url", "Добавить ссылку"), self.add_url, width=150
        ).grid(row=0, column=1, padx=(0, theme.GAP["sm"]))
        button(row, self.tr("import.paste", "Вставить из буфера"), self.paste_url, width=160).grid(
            row=0, column=2, padx=(0, theme.GAP["sm"])
        )
        button(row, self.tr("import.clear", "Очистить"), self.clear_items, width=110).grid(
            row=0, column=3
        )

        options = ctk.CTkFrame(body, fg_color="transparent")
        options.grid(row=1, column=0, sticky="ew", pady=(theme.GAP["sm"], 0))
        options.grid_columnconfigure(1, weight=1)

        self.playlist_check = ctk.CTkCheckBox(options, text="Скачивать как плейлист")
        self.playlist_check.grid(row=0, column=0, sticky="w")
        if self.app.settings.download_playlists:
            self.playlist_check.select()

        self.import_hint = muted_label(options, "")
        self.import_hint.configure(anchor="e")
        self.import_hint.grid(row=0, column=1, sticky="e")

        separator(body).grid(row=2, column=0, sticky="ew", pady=theme.GAP["md"])

        self.item_list = ItemList(
            body,
            on_select=self.select_item,
            on_remove=self.app.remove_item,
            empty_text=self.tr("import.empty", "Список пуст — добавьте ссылку"),
            height=104,
        )
        self.item_list.grid(row=3, column=0, sticky="ew")

    def _build_pages(self) -> None:
        self.video_tab = VideoTab(self.page_container, self.app, self.enqueue)
        self.audio_tab = AudioTab(self.page_container, self.app, self.enqueue)
        self.info_tab = InfoTab(self.page_container, self.app)
        self.queue_tab = QueueTab(self.page_container, self.app)
        self.settings_tab = SettingsTab(self.page_container, self.app, self.on_settings_changed)

        self.pages = {
            "video": self.video_tab,
            "audio": self.audio_tab,
            "info": self.info_tab,
            "queue": self.queue_tab,
            "settings": self.settings_tab,
        }
        self.operation_tabs = (self.video_tab, self.audio_tab, self.info_tab)
        self._current_page = ""

    def _build_status(self) -> None:
        self.progress_panel = ProgressPanel(self.content, on_cancel=self.cancel_active)
        self.progress_panel.grid(
            row=2, column=0, sticky="ew", padx=theme.GAP["xl"], pady=(0, theme.GAP["md"])
        )
        self.progress_panel.grid_remove()

        self.status_strip = StatusStrip(self, app=self.app)
        self.status_strip.grid(row=2, column=0, columnspan=2, sticky="ew")
        self.status_strip.set_message(self.tr("status.ready", "Готово"))
        self.status_strip.set_chip("ytdlp", "yt-dlp: проверка…", "busy")
        self.status_strip.set_chip("ffmpeg", "FFmpeg: проверка…", "busy")
        self.status_strip.set_chip("queue", "Очередь: 0", "idle")

    # -- навигация ------------------------------------------------------------
    def _on_nav_select(self, index: int) -> None:
        if 0 <= index < len(PAGE_KEYS):
            self.show_page(PAGE_KEYS[index])

    def show_page(self, key: str) -> None:
        """Показывает раздел; на боковой панели подсвечивается его пункт."""
        if key not in self.pages or key == self._current_page:
            if key in self.pages and self.sidebar.current != PAGE_KEYS.index(key):
                self.sidebar.select(PAGE_KEYS.index(key))
            return
        if self._current_page:
            self.pages[self._current_page].grid_remove()
        page = self.pages[key]
        page.grid(row=0, column=0, sticky="nsew")
        self._current_page = key
        index = PAGE_KEYS.index(key)
        if self.sidebar.current != index:
            self.sidebar.select(index)

    # -- события приложения ---------------------------------------------------
    def _post(self, handler, *args) -> None:
        """Кладёт вызов в потокобезопасную очередь — можно звать из любого потока."""
        self._event_queue.put((handler, args))

    def _pump_events(self) -> None:
        """Разбирает накопленные события. Работает только в потоке Tk —
        self.after() ниже сам себя планирует уже изнутри цикла событий."""
        while True:
            try:
                handler, args = self._event_queue.get_nowait()
            except queue.Empty:
                break
            try:
                handler(*args)
            except Exception:  # noqa: BLE001 - один обработчик не должен рушить остальные
                log.exception("Ошибка обработчика события GUI")
        self.after(30, self._pump_events)

    def _subscribe(self) -> None:
        bus = self.app.bus
        bus.subscribe(Event.ITEMS_CHANGED, lambda items: self._post(self._items_changed, items))
        bus.subscribe(Event.FETCH_STARTED, lambda url: self._post(self._fetch_started, url))
        bus.subscribe(
            Event.FETCH_FINISHED, lambda info, added: self._post(self._fetch_finished, info, added)
        )
        bus.subscribe(Event.TOOLS_READY, lambda binaries: self._post(self._tools_ready, binaries))
        bus.subscribe(Event.YTDLP_MISSING, lambda: self._post(self._ytdlp_missing))
        bus.subscribe(Event.JOB_ADDED, lambda job: self._post(self._queue_changed))
        bus.subscribe(Event.JOB_STARTED, lambda job: self._post(self._job_started, job))
        bus.subscribe(Event.JOB_PROGRESS, lambda job, info: self._post(self._job_progress, job, info))
        bus.subscribe(Event.JOB_STAGE, lambda job, text: self._post(self._job_stage, job, text))
        bus.subscribe(Event.JOB_FINISHED, lambda job: self._post(self._job_finished, job))
        bus.subscribe(Event.QUEUE_CHANGED, lambda: self._post(self._queue_changed))
        bus.subscribe(Event.QUEUE_IDLE, lambda: self._post(self._queue_idle))
        bus.subscribe(Event.UPDATE_CHECK_STARTED, lambda: self._post(self._update_check_started))
        bus.subscribe(Event.UPDATE_AVAILABLE, lambda info: self._post(self._update_available, info))
        bus.subscribe(Event.UPDATE_UP_TO_DATE, lambda version: self._post(self._update_up_to_date, version))
        bus.subscribe(
            Event.UPDATE_HISTORY,
            lambda releases, only_new: self._post(self._update_history, releases, only_new),
        )
        bus.subscribe(
            Event.UPDATE_PROGRESS, lambda done, total: self._post(self._update_progress, done, total)
        )
        bus.subscribe(
            Event.UPDATE_INSTALLED, lambda info, path: self._post(self._update_installed, info, path)
        )
        bus.subscribe(Event.UPDATE_FAILED, lambda message: self._post(self._update_failed, message))

    def _bind_shortcuts(self) -> None:
        self.bind("<Delete>", lambda _e: self.remove_selected())
        self.bind("<Control-Return>", lambda _e: self.start_current_page())
        self.bind("<Escape>", lambda _e: self.cancel_active())
        self.bind("<Control-l>", lambda _e: self.show_logs())
        self.bind("<F1>", lambda _e: self.show_help())
        self.bind("<Control-u>", lambda _e: self.check_updates())
        # Масштаб интерфейса — как в браузере: Ctrl+плюс/минус/0.
        for sequence in ("<Control-plus>", "<Control-equal>", "<Control-KP_Add>"):
            self.bind(sequence, lambda _e: self.zoom_by(0.1))
        for sequence in ("<Control-minus>", "<Control-KP_Subtract>"):
            self.bind(sequence, lambda _e: self.zoom_by(-0.1))
        self.bind("<Control-0>", lambda _e: self.set_ui_scale(1.0))

    # -- масштаб интерфейса ---------------------------------------------------
    def set_ui_scale(self, scale: float, *, save: bool = True) -> float:
        """Применяет масштаб ко всем окнам и запоминает его в настройках."""
        self._scale = theme.apply_scale(scale)
        if save and getattr(self.app.settings, "ui_scale", None) != self._scale:
            self.app.update_settings(ui_scale=self._scale)
        self.settings_tab.sync_ui_scale(self._scale)
        return self._scale

    def zoom_by(self, delta: float) -> None:
        self.set_ui_scale(self._scale + delta)

    # -- ввод ссылок ----------------------------------------------------------
    def add_url(self) -> None:
        url = self.url_entry.get().strip()
        if not url:
            return
        self.url_entry.delete(0, "end")
        self.app.fetch_url(url, playlist=bool(self.playlist_check.get()))

    def paste_url(self) -> None:
        try:
            text = self.clipboard_get()
        except Exception:  # noqa: BLE001 - буфер обмена может быть пуст/недоступен
            return
        self.url_entry.delete(0, "end")
        self.url_entry.insert(0, text.strip())
        self.add_url()

    def clear_items(self) -> None:
        self.app.clear_items()

    def remove_selected(self) -> None:
        if self.app.state.selected_index >= 0:
            self.app.remove_item(self.app.state.selected_index)

    def select_item(self, index: int) -> None:
        info = self.app.select_item(index)
        self.item_list.highlight(index)
        for tab in self.operation_tabs:
            tab.set_info(info)

    # -- обработчики событий -------------------------------------------------
    def _items_changed(self, items: list[VideoInfo]) -> None:
        self.item_list.set_items(items, self.app.state.selected_index)
        self.import_hint.configure(text=f"Видео в списке: {len(items)}" if items else "")
        if items and self.app.state.selected_index < 0:
            self.select_item(0)
        elif items:
            self.select_item(self.app.state.selected_index)
        else:
            for tab in self.operation_tabs:
                tab.set_info(None)

    def _fetch_started(self, url: str) -> None:
        self.status_strip.set_message(
            f"{self.tr('import.fetching', 'Получение сведений о видео…')} {url}", "busy"
        )

    def _fetch_finished(self, info: VideoInfo, added: bool) -> None:
        if info.probe_error:
            self.status_strip.set_message(
                f"Не удалось получить сведения: {info.probe_error}", "error"
            )
        elif added:
            self.status_strip.set_message(f"Добавлено: {info.title or info.url}", "ok")
        else:
            self.status_strip.set_message("Эта ссылка уже в списке", "warning")

    def _tools_ready(self, binaries) -> None:
        self.settings_tab.update_tools_status()
        self.status_strip.set_chip(
            "ytdlp", f"yt-dlp {binaries.ytdlp_version}", "ok", str(binaries.ytdlp or "")
        )
        if binaries.ffmpeg_available:
            self.status_strip.set_chip(
                "ffmpeg", f"FFmpeg {binaries.ffmpeg_version}", "ok", str(binaries.ffmpeg or "")
            )
        else:
            self.status_strip.set_chip(
                "ffmpeg",
                "FFmpeg не найден",
                "warning",
                "Без FFmpeg недоступны слияние видео и звука, извлечение аудио, "
                "встраивание субтитров и обложек.",
            )
        self.status_strip.set_message(self.tr("status.ready", "Готово"))

    def _ytdlp_missing(self) -> None:
        self.status_strip.set_chip("ytdlp", "yt-dlp не найден", "error")
        messagebox.showerror(
            "yt-dlp не найден",
            "yt-dlp не найден.\n\n"
            "Укажите путь к yt-dlp.exe в разделе «Настройки».\n\n"
            "Автоматическая загрузка из сети не выполняется.",
        )
        self.show_page("settings")
        self.settings_tab.update_tools_status()

    def _queue_changed(self) -> None:
        self.queue_tab.refresh_queue()
        self._update_queue_chip()

    def _update_queue_chip(self) -> None:
        jobs = self.app.queue.jobs
        active = sum(1 for job in jobs if job.is_active)
        pending = sum(1 for job in jobs if job.status == JobStatus.PENDING.value)
        failed = sum(1 for job in jobs if job.status == JobStatus.FAILED.value)
        if active or pending:
            health, caption = "busy", f"Очередь: {active} активных, {pending} в ожидании"
        elif failed:
            health, caption = "error", f"Очередь: {failed} с ошибкой"
        else:
            health, caption = "idle", f"Очередь: {len(jobs)}"
        self.status_strip.set_chip("queue", caption, health)

    def _job_started(self, job: Job) -> None:
        self._active_job = job
        self.progress_panel.start(f"{self.tr('status.downloading', 'Загрузка')}: {job.label}")
        self.queue_tab.update_job(job)
        self._update_queue_chip()

    def _job_progress(self, job: Job, info: ProgressInfo) -> None:
        self.progress_panel.update_progress(info)
        self.queue_tab.update_job(job, info)

    def _job_stage(self, job: Job, text: str) -> None:
        self.progress_panel.set_stage(f"{job.label}: {text}")
        self.queue_tab.update_job(job)

    def _job_finished(self, job: Job) -> None:
        self.queue_tab.update_job(job)
        self.queue_tab.refresh_queue()
        if job.status == JobStatus.COMPLETED.value:
            self.progress_panel.finish(f"{self.tr('status.completed', 'Завершено')}: {job.label}")
            names = ", ".join(Path(p).name for p in job.output_files) or job.label
            self.status_strip.set_message(f"Готово: {names}", "ok")
            self._show_result(job)
        elif job.status == JobStatus.FAILED.value:
            self.progress_panel.reset(self.tr("status.failed", "Ошибка"), severity="error")
            self.status_strip.set_message(f"Ошибка: {job.label}", "error")
            self._show_error(job)
        elif job.status == JobStatus.CANCELLED.value:
            self.progress_panel.reset(self.tr("status.cancelled", "Отменено"), severity="warning")
            self.status_strip.set_message(self.tr("status.cancelled", "Отменено"), "warning")
        self._active_job = None
        self._update_queue_chip()

    def _queue_idle(self) -> None:
        self.progress_panel.reset()
        self.status_strip.set_message(self.tr("status.ready", "Готово"))
        self._update_queue_chip()

    # -- обновления yt-dlp ---------------------------------------------------
    def check_updates(self) -> None:
        self.app.check_updates()

    def _update_check_started(self) -> None:
        self.status_strip.set_message("Проверка обновлений yt-dlp…", "busy")
        self.settings_tab.set_update_status("Проверка обновлений…", "busy")

    def _update_available(self, release: ReleaseInfo) -> None:
        current = self.app.ytdlp.binaries.ytdlp_version or "неизвестна"
        message = f"Доступно обновление yt-dlp {release.version_text} (установлена {current})"
        self.status_strip.set_message(message, "warning")
        self.settings_tab.set_update_status(message, "warning")
        self._show_release_dialog(
            [release],
            title="Доступно обновление",
            subtitle=f"Установленная версия yt-dlp: {current}",
        )

    def _update_up_to_date(self, version: str) -> None:
        message = f"Установлена последняя версия yt-dlp ({version or '—'})"
        self.status_strip.set_message(message, "ok")
        self.settings_tab.set_update_status(message, "ok")

    def _update_history(self, releases, only_new: bool) -> None:
        current = self.app.ytdlp.binaries.ytdlp_version or "неизвестна"
        self.settings_tab.refresh_update_status()
        self._show_release_dialog(
            list(releases),
            title="Доступно обновление" if only_new else "История изменений yt-dlp",
            subtitle=f"Установленная версия yt-dlp: {current}",
            show_history=only_new,
        )

    def _show_release_dialog(
        self, releases, *, title: str, subtitle: str, show_history: bool = True
    ) -> None:
        """Показывает окно с описанием релизов; второе окно не открывает."""
        if self._update_dialog is not None and self._update_dialog.winfo_exists():
            self._update_dialog.title(title)
            self._update_dialog.heading.configure(text=title)
            self._update_dialog.subtitle.configure(text=subtitle)
            self._update_dialog.set_history_visible(show_history)
            self._update_dialog.set_releases(releases)
            self._update_dialog.lift()
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
        message = f"yt-dlp обновлён до {release.version_text}"
        self.status_strip.set_message(f"{message}   •   {path}", "ok")
        self.settings_tab.set_update_status(f"{message}\n{path}", "ok")
        self.settings_tab.update_tools_status()
        if self._update_dialog is not None and self._update_dialog.winfo_exists():
            self._update_dialog.show_result(message, ok=True)

    def _update_failed(self, message: str) -> None:
        self.status_strip.set_message(f"Обновление: {message}", "error")
        self.settings_tab.set_update_status(message, "error")
        if self._update_dialog is not None and self._update_dialog.winfo_exists():
            self._update_dialog.show_result(message, ok=False)

    def on_settings_changed(self) -> None:
        """Настройки изменились: применяем оформление и масштаб сразу."""
        theme.apply_appearance(self.app.settings.theme)
        scale = theme.normalize_scale(getattr(self.app.settings, "ui_scale", 1.0))
        if scale != self._scale:
            self.set_ui_scale(scale, save=False)

    # -- запуск заданий ------------------------------------------------------
    def start_current_page(self) -> None:
        tab = {"video": self.video_tab, "audio": self.audio_tab}.get(self._current_page)
        if tab is not None:
            tab.start()

    # Историческое имя обработчика Ctrl+Enter — сохранено для совместимости.
    start_current_tab = start_current_page

    def enqueue(self, job: Job) -> None:
        self.app.enqueue(job)
        self.queue_tab.refresh_queue()
        self.status_strip.set_message(f"Добавлено в очередь: {job.label}", "ok")
        self._update_queue_chip()
        self.show_page("queue")

    def cancel_active(self) -> None:
        job = self._active_job
        if job is not None:
            # QueueManager.cancel() для активного задания в итоге делает
            # process.terminate() + wait(timeout=5с) (и ещё столько же на
            # kill() при необходимости) — не блокируем этим поток Tk.
            threading.Thread(target=self.app.queue.cancel, args=(job.id,), daemon=True).start()
            self.status_strip.set_message(f"Отмена: {job.label}", "warning")

    # -- диалоги -------------------------------------------------------------
    def _show_error(self, job: Job) -> None:
        text_dialog(
            self,
            self.tr("error.title", "Ошибка"),
            job.error or "Неизвестная ошибка",
            subtitle=job.label,
            size=(720, 480),
            card_title="Сообщение об ошибке",
            left_buttons=(
                (self.tr("error.show_log", "Показать технический лог"), lambda: self.queue_tab.open_log(job)),
                (self.tr("error.copy", "Копировать"), lambda: self.queue_tab.copy_to_clipboard(job.error or "")),
            ),
            close_text=self.tr("common.close", "Закрыть"),
        )

    def _show_result(self, job: Job) -> None:
        dialog = Dialog(
            self, self.tr("result.title", "Результат"), subtitle=job.label, size=(520, 400)
        )
        card = Card(dialog.content, "Загрузка завершена")
        card.grid(row=0, column=0, sticky="nsew")
        card.body.grid_rowconfigure(1, weight=1)

        body_label(card.body, "Файлы:").grid(row=0, column=0, sticky="ew")
        files = "\n".join(f"• {Path(p).name}" for p in job.output_files) or "—"
        muted_label(card.body, files, wraplength=420).grid(
            row=1, column=0, sticky="new", pady=(theme.GAP["xs"], 0)
        )
        dialog.add_buttons(
            left=((self.tr("result.open_folder", "Открыть папку"), lambda: self.app.open_output_folder(job)),),
            close_text=self.tr("common.close", "Закрыть"),
        )

    def show_logs(self) -> None:
        path = self.app.store.logs_dir / "ytdlp.log"
        try:
            text = path.read_text(encoding="utf-8", errors="replace")[-200000:]
        except OSError as exc:
            text = f"Лог недоступен: {exc}"
        text_dialog(
            self,
            "Лог yt-dlp",
            text,
            subtitle=str(path),
            mono=True,
            wrap="none",
            size=(960, 640),
            close_text=self.tr("common.close", "Закрыть"),
        )

    def show_help(self) -> None:
        text_dialog(
            self,
            self.tr("app.help", "Справка"),
            HELP_TEXT,
            subtitle=f"{self.tr('app.title', 'yt-dlp GUI')} {APP_VERSION}",
            size=(640, 620),
            close_text=self.tr("common.close", "Закрыть"),
        )

    # -- завершение ----------------------------------------------------------
    def on_close(self) -> None:
        if self.app.queue.active_count and not messagebox.askyesno(
            "Выход", "Есть выполняющиеся загрузки. Прервать и выйти?"
        ):
            return
        # shutdown() останавливает активные процессы yt-dlp (terminate +
        # wait до нескольких секунд на каждый) — выполняем это в фоновом
        # потоке, чтобы окно закрывалось сразу. Поток не daemon: процесс
        # Python дождётся его завершения перед выходом, так что очистка
        # (отмена загрузок, сохранение настроек, чистка temp) всё равно
        # доводится до конца.
        threading.Thread(target=self.app.shutdown).start()
        self.destroy()
