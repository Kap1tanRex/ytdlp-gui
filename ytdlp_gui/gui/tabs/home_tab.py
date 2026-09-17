"""Главная: ссылки, выбранное видео, параметры загрузки и ход работы.

Раскладка — как у главной «Стемницы» (design-system §7.1): слева
крупный заголовок, ввод ссылки, список добавленного и карточка
выбранного видео; справа панель параметров с основной кнопкой и блоком
прогресса; ниже на всю ширину — таблица всех форматов. Сюда сведены
прежние разделы «Видео», «Аудио» и «Информация»: режим загрузки
выбирается сегментом, а не вкладкой.
"""

from __future__ import annotations

import threading
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from ...core.models import DownloadMode, Job, ProgressInfo, SubtitleMode, VideoInfo, format_size
from ...services.filesystem_service import sanitize_filename
from .. import fmt, theme
from ..widgets.design import (
    Btn,
    Column,
    DashedBox,
    Dropdown,
    Field,
    Fold,
    Hero,
    Line,
    Notice,
    Panel,
    Para,
    ProgressBar,
    Seg,
    box,
    check,
    field_label,
    hline,
    sec_label,
    text,
)
from ..widgets.dialogs import text_dialog
from ..widgets.layout import ScrollPage
from ..widgets.rows import ListRow
from ..widgets.thumbnail_view import Thumb, ThumbnailLoader

#: Ширина содержимого, начиная с которой колонки стоят рядом.
WIDE_MIN = 1020
COLUMN_GAP = 52

AUTO = "Авто — лучшее качество"
INTRO = (
    "Программа скачивает видео и звук через yt-dlp — с YouTube, VK, RuTube, Twitch и "
    "сотен других сайтов. Выберите качество, звуковую дорожку и субтитры: файл "
    "сохранится прямо на этот компьютер."
)

MODES = [(DownloadMode.VIDEO.value, "Видео со звуком"), (DownloadMode.AUDIO.value, "Только звук")]
MODE_HINTS = {
    DownloadMode.VIDEO.value: (
        "Лучшие видео и звук скачиваются отдельными потоками, FFmpeg склеивает их в один файл."
    ),
    DownloadMode.AUDIO.value: "Звук извлекается в отдельный файл выбранного формата.",
}
CONTAINERS = [("mp4", "MP4"), ("mkv", "MKV"), ("webm", "WEBM")]
AUDIO_FORMATS = [
    ("mp3", "MP3"),
    ("m4a", "M4A"),
    ("opus", "OPUS"),
    ("flac", "FLAC"),
    ("wav", "WAV"),
    ("best", "Как есть"),
]
LOSSLESS = {"flac", "wav", "best"}
BITRATES = [("320", "320"), ("256", "256"), ("192", "192"), ("128", "128"), ("96", "96"), ("0", "Макс")]
SUBTITLE_MODES = [
    (SubtitleMode.NONE.value, "Нет"),
    (SubtitleMode.EMBED.value, "Вшить"),
    (SubtitleMode.EXTERNAL.value, "Файлом"),
    (SubtitleMode.BOTH.value, "Оба"),
]
SUBTITLE_SUMMARY = {
    SubtitleMode.NONE.value: "не скачивать",
    SubtitleMode.EMBED.value: "вшить",
    SubtitleMode.EXTERNAL.value: "отдельным файлом",
    SubtitleMode.BOTH.value: "вшить и файлом",
}
LANG_COLUMNS = 5


class _Section(Column):
    """Раздел панели: волосяная линия сверху и капс-подпись (§7.1)."""

    def __init__(self, master, title: str = "", *, first: bool = False) -> None:
        super().__init__(master)
        if not first:
            hline(self).grid(row=0, column=0, sticky="ew")
        self._next_row = 1
        self.inner = Column(self)
        self.add(self.inner, pady=(15, 15))
        if title:
            self.inner.add(sec_label(self.inner, title), pady=(0, 9), sticky="w")


class HomePage(ScrollPage):
    def __init__(
        self,
        master,
        app,
        *,
        loader: ThumbnailLoader,
        post: Callable[..., None],
        toast: Callable[..., None],
        on_enqueue: Callable[[Job], None],
        on_cancel: Callable[[Job], None],
        on_show_settings: Callable[[], None],
    ) -> None:
        super().__init__(master)
        self.app = app
        self.loader = loader
        self.post = post
        self.toast = toast
        self.on_enqueue = on_enqueue
        self.on_cancel = on_cancel
        self.on_show_settings = on_show_settings

        self.video: VideoInfo | None = None  # выбранное видео
        self.mode = DownloadMode.VIDEO.value
        self._items: list[VideoInfo] = []
        self._pending: list[str] = []
        self._rows: list[ListRow] = []
        self._video_formats: dict[str, str] = {}
        self._audio_tracks: dict[str, str] = {}
        self._sub_checks: dict[str, ctk.CTkCheckBox] = {}
        self._shown_job: Job | None = None
        self._wide: bool | None = None

        self.columns = box(self.body)
        self.columns.grid(row=0, column=0, sticky="ew", pady=(50, 0))
        self._build_left()
        self._build_panel()
        self._build_formats()
        self._apply_layout(True)

        self.set_mode(self.mode)
        self.set_info(None)
        self._rebuild_rows()

    # =========================================================================
    # Построение: левая колонка
    # =========================================================================
    def _build_left(self) -> None:
        left = self.left = Column(self.columns)

        self.hero = Hero(
            left,
            (
                (("Вставь ссылку.", theme.TXT),),
                (("Забери ", theme.TXT), ("видео", theme.AMBER), (".", theme.TXT)),
            ),
            size=50,
        )
        left.add(self.hero, sticky="w")
        left.add(Para(left, INTRO, font=theme.sans(14), color=theme.DIM, max_width=505), pady=(22, 0))

        url_row = box(left)
        url_row.grid_columnconfigure(0, weight=1)
        self.url_entry = Field(
            url_row,
            height=46,
            font_size=13,
            placeholder_text="https://www.youtube.com/watch?v=…",
        )
        self.url_entry.grid(row=0, column=0, sticky="ew")
        self.url_entry.bind("<Return>", lambda _e: self.add_url())
        Btn(url_row, "Добавить", self.add_url, kind="primary", size="lg", icon="+").grid(
            row=0, column=1, padx=(10, 0)
        )
        left.add(url_row, pady=(30, 0))

        options = box(left)
        options.grid_columnconfigure(2, weight=1)
        self.playlist_check = check(
            options, "Плейлист целиком", checked=self.app.settings.download_playlists
        )
        self.playlist_check.grid(row=0, column=0, sticky="w")
        Btn(options, "Вставить из буфера", self.paste_url, kind="quiet", size="sm").grid(
            row=0, column=1, sticky="w", padx=(18, 0)
        )
        text(options, "Enter — добавить", font=theme.mono(11), color=theme.FAINT).grid(
            row=0, column=2, sticky="e"
        )
        left.add(options, pady=(12, 0))

        head = box(left)
        head.grid_columnconfigure(1, weight=1)
        sec_label(head, "Ссылки").grid(row=0, column=0, sticky="w")
        self.items_count = text(head, "", font=theme.mono(11), color=theme.DIM)
        self.items_count.grid(row=0, column=1, sticky="w", padx=(10, 0))
        self.clear_button = Btn(head, "Очистить", self.clear_items, kind="quiet", size="sm")
        self.clear_button.grid(row=0, column=2, sticky="e")
        left.add(head, pady=(34, 6))

        self.list_holder = Column(left)
        left.add(self.list_holder)
        self.empty_list = DashedBox(
            self.list_holder, "Здесь появятся добавленные видео", height=84, outer=False
        )
        self.empty_list.label.configure(font=theme.sans(13))
        self.list_holder.add(self.empty_list)
        self.list_panel = Panel(self.list_holder)
        self.list_holder.add(self.list_panel)
        self.list_rows = Column(self.list_panel)
        self.list_rows.grid(row=0, column=0, sticky="ew", padx=1, pady=3)

        self._build_card(left)

    def _build_card(self, left: Column) -> None:
        """Карточка выбранного видео (как карточка трека «Стемницы»)."""
        card = self.card = box(left)
        card.grid_columnconfigure(2, weight=1)
        hline(card).place(relx=0, rely=0, relwidth=1)
        sec_label(card, "Видео").grid(row=0, column=0, sticky="nw", pady=(16, 0))
        self.card_thumb = Thumb(card, 192, 108)
        self.card_thumb.grid(row=0, column=1, sticky="nw", padx=(20, 18), pady=(16, 0))

        details = Column(card)
        details.grid(row=0, column=2, sticky="new", pady=(12, 0))
        self.card_title = Para(details, "", font=theme.sans_medium(15), color=theme.TXT)
        details.add(self.card_title)
        self.card_data = Para(details, "", font=theme.mono(11), color=theme.DIM)
        details.add(self.card_data, pady=(6, 0))
        self.card_url = Line(details, font=theme.mono(11), color=theme.FAINT)
        details.add(self.card_url, pady=(4, 0))
        self.save_thumb_button = Btn(
            details, "Сохранить обложку…", self._save_thumbnail, kind="quiet", size="sm"
        )
        details.add(self.save_thumb_button, pady=(10, 0), sticky="w")
        left.add(card, pady=(28, 0))

    # =========================================================================
    # Построение: панель параметров
    # =========================================================================
    def _build_panel(self) -> None:
        self.panel = Panel(self.columns)
        inner = Column(self.panel)
        inner.grid(row=0, column=0, sticky="ew", padx=18, pady=(6, 16))
        settings = self.app.settings

        # -- что скачать --------------------------------------------------------
        section = _Section(inner, "Что скачать", first=True)
        inner.add(section)
        body = section.inner
        self.mode_seg = Seg(body, MODES, value=self.mode, command=self.set_mode, height=36)
        body.add(self.mode_seg)
        self.mode_hint = Para(body, "", font=theme.sans(12), color=theme.DIM)
        body.add(self.mode_hint, pady=(10, 0))
        self.ffmpeg_notice = Notice(
            body,
            "FFmpeg не найден: видео и звук не склеятся, извлечение звука, субтитры и "
            "обложки недоступны.",
            color=theme.WARN,
            action="Настройки",
            command=self.on_show_settings,
        )
        body.add(self.ffmpeg_notice, pady=(12, 0))
        self.ffmpeg_notice.grid_remove()

        # -- качество -----------------------------------------------------------
        section = _Section(inner, "Качество")
        inner.add(section)
        body = section.inner
        self.video_box = Column(body)
        body.add(self.video_box)
        self.format_menu = Dropdown(self.video_box, [AUTO], width=120)
        self.video_box.add(self.format_menu)
        self.container_seg = Seg(
            self.video_box, CONTAINERS, value=settings.default_container, height=32
        )
        self.video_box.add(self.container_seg, pady=(8, 0))
        self.formats_hint = text(self.video_box, "", font=theme.mono(11), color=theme.FAINT)
        self.video_box.add(self.formats_hint, pady=(10, 0), sticky="w")

        self.audio_box = Column(body)
        body.add(self.audio_box)
        self.audio_format_seg = Seg(
            self.audio_box,
            AUDIO_FORMATS,
            value=settings.default_audio_format,
            command=lambda _v: self._sync_bitrate(),
            height=32,
        )
        self.audio_box.add(self.audio_format_seg)
        self.audio_box.add(field_label(self.audio_box, "Битрейт, кбит/с"), pady=(14, 6), sticky="w")
        self.bitrate_seg = Seg(
            self.audio_box, BITRATES, value=settings.default_audio_quality, height=32
        )
        self.audio_box.add(self.bitrate_seg)

        body.add(field_label(body, "Звуковая дорожка"), pady=(14, 6), sticky="w")
        self.track_menu = Dropdown(body, [AUTO], width=120)
        body.add(self.track_menu)

        # -- субтитры -----------------------------------------------------------
        self.subtitles_section = _Section(inner)
        inner.add(self.subtitles_section)
        self.subs_fold = Fold(self.subtitles_section.inner, "Субтитры", summary="не скачивать")
        self.subtitles_section.inner.add(self.subs_fold)
        body = self.subs_fold.body
        self.sub_mode_seg = Seg(
            body,
            SUBTITLE_MODES,
            value=SubtitleMode.NONE.value,
            command=lambda _v: self._sync_subtitles(),
            height=32,
        )
        self.sub_mode_seg.grid(row=0, column=0, sticky="ew")
        self.langs_frame = box(body)
        self.langs_frame.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        self.auto_subs_check = check(
            body,
            "Автоматические субтитры",
            command=self._sync_subtitles,
            checked=settings.include_auto_subs_default,
        )
        self.auto_subs_check.grid(row=2, column=0, sticky="w", pady=(12, 0))

        # -- сохранение ---------------------------------------------------------
        section = _Section(inner)
        inner.add(section)
        self.save_fold = Fold(section.inner, "Сохранение")
        section.inner.add(self.save_fold)
        body = self.save_fold.body
        field_label(body, "Папка").grid(row=0, column=0, sticky="w", pady=(0, 6))
        folder_row = box(body)
        folder_row.grid(row=1, column=0, sticky="ew")
        folder_row.grid_columnconfigure(0, weight=1)
        self.output_entry = Field(folder_row)
        self.output_entry.grid(row=0, column=0, sticky="ew")
        self.output_entry.set_text(
            settings.output_directory or str(self.app.filesystem.default_download_dir())
        )
        self.output_entry.bind("<FocusOut>", lambda _e: self._sync_save_summary())
        Btn(folder_row, "Изменить…", self._browse_output, size="sm").grid(
            row=0, column=1, padx=(8, 0)
        )
        self.embed_thumb_check = check(
            body,
            "Встроить обложку в файл",
            command=self._sync_save_summary,
            checked=settings.embed_thumbnail_default,
        )
        self.embed_thumb_check.grid(row=2, column=0, sticky="w", pady=(12, 0))
        self._sync_save_summary()

        # -- кнопка, статус и ход работы ---------------------------------------
        section = _Section(inner)
        inner.add(section)
        body = section.inner
        self.download_button = Btn(
            body, "Скачать видео", self.start, kind="primary", size="lg", width=1
        )
        body.add(self.download_button)
        status_row = box(body)
        status_row.grid_columnconfigure(0, weight=1)
        self.status = Para(status_row, "", font=theme.mono(11), color=theme.DIM)
        self.status.grid(row=0, column=0, sticky="ew")
        self.command_button = Btn(
            status_row, "Команда", self._show_command, kind="quiet", size="sm"
        )
        self.command_button.grid(row=0, column=1, sticky="e", padx=(12, 0))
        body.add(status_row, pady=(10, 0))

        self.progress = Column(body)
        body.add(self.progress, pady=(16, 0))
        self.progress_title = Line(self.progress, font=theme.sans(13), color=theme.TXT)
        self.progress.add(self.progress_title, pady=(0, 10))
        self.progress_bar = ProgressBar(self.progress, height=8)
        self.progress.add(self.progress_bar)
        numbers = box(self.progress)
        numbers.grid_columnconfigure(1, weight=1)
        self.progress_percent = text(numbers, "", font=theme.mono(14), color=theme.DIM)
        self.progress_percent.grid(row=0, column=0, sticky="w")
        self.progress_left = text(numbers, "", font=theme.mono(14), color=theme.DIM, anchor="e")
        self.progress_left.grid(row=0, column=1, sticky="e")
        self.progress.add(numbers, pady=(8, 0))
        details = box(self.progress)
        details.grid_columnconfigure(0, weight=1)
        self.progress_detail = Line(details, font=theme.mono(11), color=theme.FAINT)
        self.progress_detail.grid(row=0, column=0, sticky="ew")
        self.cancel_button = Btn(details, "Отменить", self._cancel_shown, kind="danger", size="sm")
        self.cancel_button.grid(row=0, column=1, sticky="e", padx=(12, 0))
        self.progress.add(details, pady=(6, 0))
        self.progress.grid_remove()

    def _build_formats(self) -> None:
        """Таблица всех форматов — бывший раздел «Информация»."""
        self.formats_panel = Panel(self.body)
        self.formats_panel.grid(row=1, column=0, sticky="ew", pady=(34, 0))
        self.formats_fold = Fold(self.formats_panel, "Все форматы")
        self.formats_fold.grid(row=0, column=0, sticky="ew", padx=18, pady=16)
        self.formats_box = ctk.CTkTextbox(
            self.formats_fold.body,
            wrap="none",
            height=280,
            font=theme.mono(12),
            fg_color=theme.PIT,
            text_color=theme.DIM,
            border_width=0,
            border_spacing=10,
            corner_radius=3,
            scrollbar_button_color=theme.LINE2,
            scrollbar_button_hover_color=theme.DIM,
        )
        self.formats_box.grid(row=0, column=0, sticky="ew")
        self.formats_box.tag_config("head", foreground=theme.FAINT)
        self.formats_box.configure(state="disabled")

    # =========================================================================
    # Раскладка
    # =========================================================================
    def on_width(self, width: int) -> None:
        # Заголовок — 4 % ширины, от 29 до 50 px (§4.2).
        self.hero.set_size(max(29, min(50, round(width * 0.04))))
        self._apply_layout(width >= WIDE_MIN)

    def _apply_layout(self, wide: bool) -> None:
        columns = self.columns
        gap = round(COLUMN_GAP * theme.widget_scale(self))
        if wide:
            columns.grid_columnconfigure(0, weight=125, uniform="home")
            columns.grid_columnconfigure(1, weight=0, minsize=gap)
            columns.grid_columnconfigure(2, weight=85, uniform="home")
        if wide == self._wide:
            return
        self._wide = wide
        if wide:
            self.left.grid(row=0, column=0, sticky="new")
            self.panel.grid(row=0, column=2, sticky="new", pady=0)
        else:
            columns.grid_columnconfigure(0, weight=1, uniform="")
            columns.grid_columnconfigure(1, weight=0, minsize=0)
            columns.grid_columnconfigure(2, weight=0, uniform="")
            self.left.grid(row=0, column=0, sticky="new")
            self.panel.grid(row=1, column=0, sticky="new", pady=(26, 0))

    # =========================================================================
    # Ссылки
    # =========================================================================
    def add_url(self) -> None:
        url = self.url_entry.get().strip()
        if not url:
            self.set_status("вставьте ссылку и нажмите Enter")
            return
        self.url_entry.delete(0, "end")
        self.app.fetch_url(url, playlist=bool(self.playlist_check.get()))

    def paste_url(self) -> None:
        try:
            value = self.clipboard_get().strip()
        except tk.TclError:
            value = ""
        if not value:
            self.toast("Буфер обмена пуст — скопируйте ссылку на видео.", "warn")
            return
        self.url_entry.set_text(value)
        self.add_url()

    def clear_items(self) -> None:
        self.app.clear_items()

    def remove_selected(self) -> None:
        if self.app.state.selected_index >= 0:
            self.app.remove_item(self.app.state.selected_index)

    def set_items(self, items: list[VideoInfo]) -> None:
        self._items = list(items)
        index = self.app.state.selected_index
        if items:
            self.select(max(0, index))
        else:
            self.set_info(None)
        self._rebuild_rows()

    def select(self, index: int) -> None:
        info = self.app.select_item(index)
        # Тот же объект — не сбрасываем выбранные форматы и субтитры.
        if info is not self.video:
            self.set_info(info)
        self._paint_rows()

    def fetch_started(self, url: str) -> None:
        self._pending.append(url)
        self._rebuild_rows()
        self.set_status("получаю сведения о видео…")

    def fetch_finished(self, info: VideoInfo, added: bool) -> None:
        if info.url in self._pending:
            self._pending.remove(info.url)
        elif self._pending:
            self._pending.pop(0)
        self._rebuild_rows()
        if info.probe_error:
            self.toast(f"Не удалось получить сведения: {info.probe_error}", "error")
        elif not added:
            self.toast("Эта ссылка уже в списке.", "info")
        self._sync_status()

    def _rebuild_rows(self) -> None:
        self._rows.clear()
        self.list_rows.clear()

        count = len(self._items)
        self.items_count.configure(text=str(count) if count else "")
        self.clear_button.set_enabled(bool(count))
        if not self._items and not self._pending:
            self.list_panel.grid_remove()
            self.empty_list.grid()
            return
        self.empty_list.grid_remove()
        self.list_panel.grid()

        for index, info in enumerate(self._items):
            row = ListRow(self.list_rows, on_click=lambda i=index: self.select(i))
            if info.probe_error:
                row.title.set(info.url)
                row.data.set(info.probe_error, theme.ERR)
            elif info.is_playlist:
                row.title.set(info.playlist_title or info.title or info.url)
                count_text = f"{info.playlist_count} видео" if info.playlist_count else ""
                row.data.set(fmt.join("плейлист", count_text))
            else:
                row.title.set(info.title or info.id or info.url)
                row.data.set(
                    fmt.join(
                        info.uploader,
                        fmt.clock(info.duration) if info.duration else "",
                        fmt.date(info.upload_date),
                    )
                )
            row.thumb.load(self.loader, info)
            remove = Btn(row, "×", lambda i=index: self.app.remove_item(i), kind="tool")
            row.add_right(remove, padx=(12, 0))
            row.finish_right()
            self._add_row(row)
            self._rows.append(row)

        for url in self._pending:
            row = ListRow(self.list_rows)
            row.title.set(url)
            row.data.set("получаю сведения…", theme.FAINT)
            bar = ProgressBar(row, height=2)
            bar.place(relx=0, rely=1.0, relwidth=1, anchor="sw")
            bar.start()
            self._add_row(row)
        self._paint_rows()

    def _add_row(self, row: ListRow) -> None:
        if self.list_rows.count:
            self.list_rows.add(hline(self.list_rows))
        self.list_rows.add(row)

    def _paint_rows(self) -> None:
        selected = self.app.state.selected_index
        for index, row in enumerate(self._rows):
            info = self._items[index] if index < len(self._items) else None
            if info is not None and info.probe_error:
                row.set_state("error")
            else:
                row.set_state("current" if index == selected else "normal")

    # =========================================================================
    # Выбранное видео
    # =========================================================================
    def set_info(self, info: VideoInfo | None) -> None:
        self.video = info
        self._fill_video_formats(info)
        self._fill_audio_tracks(info)
        self._fill_subtitles(info)
        self._fill_card(info)
        self._fill_formats_table(info)
        self._sync_status()

    def _fill_card(self, info: VideoInfo | None) -> None:
        if info is None or info.probe_error:
            self.card.grid_remove()
            return
        self.card.grid()
        title = (info.playlist_title or info.title) if info.is_playlist else info.title
        self.card_title.configure(text=title or info.id or info.url)
        views = ""
        if info.view_count:
            word = fmt.plural_word(info.view_count, "просмотр", "просмотра", "просмотров")
            views = f"{fmt.grouped(info.view_count)} {word}"
        playlist = ""
        if info.is_playlist:
            playlist = "плейлист"
            if info.playlist_count:
                playlist += f" · {info.playlist_count} видео"
        self.card_data.configure(
            text=fmt.join(
                playlist,
                info.uploader,
                fmt.clock(info.duration) if info.duration else "",
                fmt.date(info.upload_date),
                views,
            )
        )
        self.card_url.set(info.webpage_url or info.url)
        self.save_thumb_button.set_enabled(bool(info.thumbnail_url))
        self.card_thumb.load(self.loader, info)

    def _fill_video_formats(self, info: VideoInfo | None) -> None:
        self._video_formats = {}
        formats = []
        if info is not None and not info.probe_error:
            formats = sorted(info.video_formats, key=lambda f: (f.height or 0, f.tbr or 0), reverse=True)
        labels = [AUTO]
        for item in formats:
            label = item.describe()
            self._video_formats[label] = item.format_id
            labels.append(label)
        self.format_menu.set_values(labels, AUTO)
        if formats:
            progressive = len(info.progressive_formats)
            self.formats_hint.configure(
                text=fmt.join(
                    fmt.plural(len(formats), "видеопоток", "видеопотока", "видеопотоков"),
                    f"{progressive} со звуком внутри" if progressive else "",
                )
            )
        else:
            self.formats_hint.configure(text="форматы появятся после выбора видео")

    def _fill_audio_tracks(self, info: VideoInfo | None) -> None:
        self._audio_tracks = {}
        labels = [AUTO]
        if info is not None and not info.probe_error:
            for item in info.audio_formats:
                label = item.describe()
                self._audio_tracks[label] = item.format_id
                labels.append(label)
        self.track_menu.set_values(labels, AUTO)

    def _fill_subtitles(self, info: VideoInfo | None) -> None:
        for widget in self.langs_frame.winfo_children():
            widget.destroy()
        self._sub_checks.clear()
        languages = info.subtitle_languages if info is not None and not info.probe_error else []
        if not languages:
            hint = (
                "Выберите видео — здесь появятся доступные языки."
                if info is None
                else "У этого видео субтитров нет."
            )
            text(self.langs_frame, hint, font=theme.sans(12), color=theme.FAINT).grid(
                row=0, column=0, sticky="w"
            )
        else:
            defaults = set(self.app.settings.subtitle_langs_default)
            for column in range(LANG_COLUMNS):
                self.langs_frame.grid_columnconfigure(column, weight=1, uniform="langs")
            for index, lang in enumerate(languages):
                checkbox = check(
                    self.langs_frame, lang, command=self._sync_subtitles, checked=lang in defaults
                )
                checkbox.grid(row=index // LANG_COLUMNS, column=index % LANG_COLUMNS, sticky="w", pady=2)
                self._sub_checks[lang] = checkbox
        self._sync_subtitles()

    def _fill_formats_table(self, info: VideoInfo | None) -> None:
        table = self.formats_box
        table.configure(state="normal")
        table.delete("1.0", "end")
        if info is None or info.probe_error:
            self.formats_panel.grid_remove()
            table.configure(state="disabled")
            return
        self.formats_panel.grid()
        if not info.formats:
            table.insert("1.0", "Список форматов недоступен.")
            self.formats_fold.set_summary("нет данных")
        else:
            header = (
                f"{'ID':<10}{'EXT':<6}{'РАЗРЕШЕНИЕ':<20}{'ВИДЕО':<12}{'АУДИО':<10}"
                f"{'БИТРЕЙТ':<14}{'ЯЗЫК':<8}{'РАЗМЕР':<10}"
            )
            table.insert("end", header + "\n", "head")
            ordered = sorted(
                info.formats,
                key=lambda f: (not f.has_video, -(f.height or 0), -(f.tbr or f.abr or 0)),
            )
            for item in ordered:
                table.insert(
                    "end",
                    f"{item.format_id:<10}{item.ext:<6}{item.resolution_text:<20}"
                    f"{(item.vcodec or '-').split('.')[0]:<12}{(item.acodec or '-').split('.')[0]:<10}"
                    f"{item.bitrate_text:<14}{(item.language or '-'):<8}{format_size(item.size):<10}\n",
                )
            video = len(info.video_formats)
            audio = len(info.audio_formats)
            self.formats_fold.set_summary(
                fmt.join(
                    fmt.plural(len(info.formats), "формат", "формата", "форматов"),
                    f"видео {video}",
                    f"звук {audio}",
                )
            )
        table.configure(state="disabled")

    # =========================================================================
    # Параметры
    # =========================================================================
    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self.mode_seg.set(mode)
        video = mode == DownloadMode.VIDEO.value
        if video:
            self.audio_box.grid_remove()
            self.video_box.grid()
            self.subtitles_section.grid()
        else:
            self.video_box.grid_remove()
            self.audio_box.grid()
            self.subtitles_section.grid_remove()
        self.mode_hint.configure(text=MODE_HINTS[mode])
        self.download_button.configure(text="Скачать видео" if video else "Скачать звук")
        self._sync_bitrate()

    def apply_defaults(self) -> None:
        """Значения по умолчанию из настроек — в элементы панели."""
        settings = self.app.settings
        self.container_seg.set(settings.default_container)
        self.audio_format_seg.set(settings.default_audio_format)
        self.bitrate_seg.set(settings.default_audio_quality)
        self._sync_bitrate()
        for checkbox, value in (
            (self.embed_thumb_check, settings.embed_thumbnail_default),
            (self.auto_subs_check, settings.include_auto_subs_default),
            (self.playlist_check, settings.download_playlists),
        ):
            if value:
                checkbox.select()
            else:
                checkbox.deselect()
        self._sync_save_summary()
        self._sync_subtitles()

    def refresh_status(self) -> None:
        self._sync_status()

    def set_tools(self, ffmpeg_available: bool) -> None:
        if ffmpeg_available:
            self.ffmpeg_notice.grid_remove()
        else:
            self.ffmpeg_notice.grid()

    def _sync_bitrate(self) -> None:
        lossless = self.audio_format_seg.get() in LOSSLESS
        for key in self.bitrate_seg.options():
            self.bitrate_seg.set_enabled(key, not lossless)

    def _subtitle_options(self) -> tuple[str, list[str], bool]:
        mode = self.sub_mode_seg.get() or SubtitleMode.NONE.value
        langs = [lang for lang, checkbox in self._sub_checks.items() if checkbox.get()]
        return mode, langs, bool(self.auto_subs_check.get())

    def _sync_subtitles(self) -> None:
        mode, langs, auto = self._subtitle_options()
        enabled = mode != SubtitleMode.NONE.value
        state = tk.NORMAL if enabled else tk.DISABLED
        for checkbox in self._sub_checks.values():
            checkbox.configure(state=state)
        self.auto_subs_check.configure(state=state)
        summary = SUBTITLE_SUMMARY.get(mode, "")
        if enabled:
            summary = fmt.join(summary, ", ".join(langs) if langs else "все языки", "авто" if auto else "")
        self.subs_fold.set_summary(summary)

    def _sync_save_summary(self) -> None:
        folder = self.output_entry.get().strip()
        self.save_fold.set_summary(
            fmt.join(Path(folder).name or folder, "с обложкой" if self.embed_thumb_check.get() else "")
        )

    def _browse_output(self) -> None:
        path = filedialog.askdirectory(title="Папка загрузки", parent=self.winfo_toplevel())
        if path:
            self.output_entry.set_text(path)
            self._sync_save_summary()

    # =========================================================================
    # Статус и запуск
    # =========================================================================
    def set_status(self, message: str, *, error: bool = False) -> None:
        self.status.configure(text=message, text_color=theme.ERR if error else theme.DIM)

    def _sync_status(self) -> None:
        info = self.video
        ready = info is not None and not info.probe_error
        self.download_button.set_enabled(ready)
        self.command_button.set_enabled(ready)
        if self._pending:
            self.set_status("получаю сведения о видео…")
        elif info is None:
            self.set_status("вставьте ссылку и нажмите Enter")
        elif info.probe_error:
            self.set_status(f"сведения недоступны: {info.probe_error}", error=True)
        else:
            self.set_status("готово к загрузке — Ctrl+Enter")

    def _build_job(self) -> Job | None:
        info = self.video
        if info is None or info.probe_error:
            self._sync_status()
            return None
        output_dir = self.output_entry.get().strip() or str(self.app.filesystem.default_download_dir())
        embed_thumbnail = bool(self.embed_thumb_check.get())
        track = self._audio_tracks.get(self.track_menu.get())
        if self.mode == DownloadMode.AUDIO.value:
            return self.app.build_job(
                info,
                mode=DownloadMode.AUDIO.value,
                audio_format_id=track,
                audio_format=self.audio_format_seg.get(),
                audio_quality=self.bitrate_seg.get(),
                embed_thumbnail=embed_thumbnail,
                output_dir=output_dir,
            )
        subtitle_mode, subtitle_langs, include_auto = self._subtitle_options()
        return self.app.build_job(
            info,
            mode=DownloadMode.VIDEO.value,
            video_format_id=self._video_formats.get(self.format_menu.get()),
            audio_format_id=track,
            container=self.container_seg.get(),
            subtitle_mode=subtitle_mode,
            subtitle_langs=subtitle_langs,
            include_auto_subs=include_auto,
            embed_thumbnail=embed_thumbnail,
            output_dir=output_dir,
        )

    def start(self) -> None:
        job = self._build_job()
        if job is not None:
            self.on_enqueue(job)
            self.set_status(f"в очереди: {job.label}")

    def _show_command(self) -> None:
        job = self._build_job()
        if job is None:
            return
        text_dialog(
            self,
            "Команда yt-dlp",
            self.app.preview_command(job),
            subtitle=job.label,
            mono=True,
            size=(820, 360),
            info="будет выполнено",
        )

    # =========================================================================
    # Ход загрузки
    # =========================================================================
    @property
    def shown_job(self) -> Job | None:
        return self._shown_job

    def show_job(self, job: Job | None) -> None:
        """Какое задание показывать в блоке прогресса (``None`` — спрятать)."""
        if job is None:
            self._shown_job = None
            self.progress_bar.reset()
            self.progress.grid_remove()
            return
        if job is not self._shown_job:
            self._shown_job = job
            self.progress_bar.reset()
            self.progress_percent.configure(text="")
            self.progress_left.configure(text="оцениваю время…")
            self.progress_detail.set("")
        self.progress.grid()
        self.progress_title.set(fmt.join("Загрузка", job.label))
        self.cancel_button.set_enabled(True)

    def job_progress(self, job: Job, info: ProgressInfo) -> None:
        if job is not self._shown_job:
            return
        self.progress_title.set(fmt.join("Загрузка", job.label))
        if info.total_bytes:
            self.progress_bar.set(info.fraction)
            self.progress_percent.configure(text=fmt.percent(info.fraction))
            done = f"{fmt.size(info.downloaded_bytes)} из {fmt.size(info.total_bytes)}"
        else:
            self.progress_bar.start()
            self.progress_percent.configure(text="")
            done = fmt.size(info.downloaded_bytes)
        self.progress_left.configure(text=fmt.remaining(info.eta) or "оцениваю время…")
        fragments = ""
        if info.fragment_index and info.fragment_count:
            fragments = f"фрагмент {info.fragment_index} из {info.fragment_count}"
        self.progress_detail.set(fmt.join(done, fmt.speed(info.speed) if info.speed else "", fragments))

    def job_stage(self, job: Job, stage: str) -> None:
        if job is not self._shown_job:
            return
        self.progress_title.set(fmt.join("Обработка", job.label))
        self.progress_bar.start()
        self.progress_percent.configure(text="")
        self.progress_left.configure(text="")
        self.progress_detail.set(stage.lower() if stage else "")

    def _cancel_shown(self) -> None:
        if self._shown_job is not None:
            self.cancel_button.set_enabled(False)
            self.on_cancel(self._shown_job)

    # =========================================================================
    # Обложка
    # =========================================================================
    def _save_thumbnail(self) -> None:
        info = self.video
        if info is None or info.probe_error or not info.thumbnail_url:
            return
        suggested = sanitize_filename(info.title or info.id or "thumbnail")
        dest = filedialog.asksaveasfilename(
            title="Сохранить обложку",
            initialfile=f"{suggested}.jpg",
            defaultextension=".jpg",
            filetypes=[("JPEG", "*.jpg *.jpeg"), ("PNG", "*.png")],
            parent=self.winfo_toplevel(),
        )
        if not dest:
            return
        self.save_thumb_button.configure(text="Сохраняю…")
        self.save_thumb_button.set_enabled(False)
        threading.Thread(target=self._save_worker, args=(info, Path(dest)), daemon=True).start()

    def _save_worker(self, info: VideoInfo, dest: Path) -> None:
        error = None
        try:
            self.app.save_thumbnail(info, dest)
        except Exception as exc:  # noqa: BLE001 - любую ошибку показываем пользователю
            error = str(exc)
        self.post(self._thumbnail_saved, dest, error)

    def _thumbnail_saved(self, dest: Path, error: str | None) -> None:
        self.save_thumb_button.configure(text="Сохранить обложку…")
        self.save_thumb_button.set_enabled(True)
        if error:
            self.toast(f"Обложка не сохранена: {error}", "error")
        else:
            self.toast(f"Обложка сохранена: {dest.name}", "ok")

