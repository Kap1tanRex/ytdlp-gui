"""Раздел «Аудио»: извлечение звуковой дорожки в отдельный аудиофайл."""

from __future__ import annotations

from tkinter import filedialog, messagebox

import customtkinter as ctk

from ...core.models import DownloadMode, VideoInfo
from .. import theme
from ..widgets.design import (
    Card,
    Page,
    button,
    form_frame,
    form_row,
    muted_label,
    primary_button,
    title_label,
)
from ..widgets.dialogs import text_dialog
from ._controls import AudioTrackSelector

_AUDIO_FORMATS = ["mp3", "m4a", "opus", "flac", "wav", "best"]
_QUALITIES = ["320", "256", "192", "128", "96", "64", "0"]

_LABEL_WIDTH = 200


class AudioTab(ctk.CTkFrame):
    def __init__(self, master, app, on_start) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.on_start = on_start
        self.info: VideoInfo | None = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_page()
        self._build_actions()

        # Стартовое состояние — то же, что и при пустом списке видео.
        self.set_info(None)

    # -- построение ------------------------------------------------------
    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, theme.GAP["md"]))
        header.grid_columnconfigure(0, weight=1)

        self.title_label = title_label(header, "Видео не выбрано")
        self.title_label.configure(wraplength=760)
        self.title_label.grid(row=0, column=0, sticky="ew")

        self.subtitle_label = muted_label(header, "Извлечение звука в отдельный аудиофайл (нужен FFmpeg)")
        self.subtitle_label.grid(row=1, column=0, sticky="ew", pady=(2, 0))

    def _build_page(self) -> None:
        # Прокручиваемая область: содержимое может стать выше окна, без
        # неё кнопка «Скачать аудио» уезжала бы за пределы раздела.
        self.page = Page(self)
        self.page.grid(row=1, column=0, sticky="nsew")

        format_card = Card(self.page, "Формат")
        body = format_card.body
        form = form_frame(body, 0)

        self.format_menu = ctk.CTkOptionMenu(form, values=_AUDIO_FORMATS, height=32, width=240)
        form_row(form, 0, "Формат аудио", self.format_menu, label_width=_LABEL_WIDTH, stretch=False)
        self.format_menu.set(self.app.settings.default_audio_format)

        self.quality_menu = ctk.CTkOptionMenu(form, values=_QUALITIES, height=32, width=240)
        form_row(
            form, 1, "Битрейт, kbps (0 = лучший)", self.quality_menu, label_width=_LABEL_WIDTH, stretch=False
        )
        self.quality_menu.set(self.app.settings.default_audio_quality)

        self.track_panel = AudioTrackSelector(body, self.app, label_width=_LABEL_WIDTH)
        self.track_panel.grid(row=1, column=0, sticky="ew")
        self.page.add(format_card)

        output_card = Card(self.page, "Сохранение")
        self._build_output(output_card.body)
        self.page.add(output_card)

    def _build_output(self, parent) -> None:
        parent.grid_columnconfigure(0, weight=1)

        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.grid(row=0, column=0, sticky="ew")
        row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(row, text="Папка загрузки", anchor="w", width=_LABEL_WIDTH).grid(
            row=0, column=0, sticky="w", padx=(0, theme.GAP["md"])
        )
        self.output_entry = ctk.CTkEntry(row, height=32)
        self.output_entry.grid(row=0, column=1, sticky="ew")
        self.output_entry.insert(
            0,
            self.app.settings.output_directory or str(self.app.filesystem.default_download_dir()),
        )
        button(row, "Обзор", self._browse_output, width=90).grid(
            row=0, column=2, padx=(theme.GAP["sm"], 0)
        )

        self.embed_thumb_check = ctk.CTkCheckBox(parent, text="Встроить обложку (обычно для mp3/m4a)")
        self.embed_thumb_check.grid(row=1, column=0, sticky="w", pady=(theme.GAP["sm"], 0))
        if self.app.settings.embed_thumbnail_default:
            self.embed_thumb_check.select()

    def _build_actions(self) -> None:
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=2, column=0, sticky="ew", pady=(theme.GAP["md"], 0))
        frame.grid_columnconfigure(0, weight=1)

        button(frame, "Показать команду yt-dlp", self._show_command).grid(row=0, column=0, sticky="w")
        primary_button(frame, "Скачать аудио", self.start, width=180).grid(row=0, column=1, sticky="e")

    def _browse_output(self) -> None:
        path = filedialog.askdirectory(title="Папка загрузки")
        if path:
            self.output_entry.delete(0, "end")
            self.output_entry.insert(0, path)

    # -- данные ------------------------------------------------------------
    def set_info(self, info: VideoInfo | None) -> None:
        self.info = info
        if info is None:
            self.title_label.configure(text="Видео не выбрано")
        else:
            self.title_label.configure(text=info.title or info.url)
        self.track_panel.set_info(info)

    # -- сборка задания ------------------------------------------------------
    def _build_job(self):
        if self.info is None:
            messagebox.showwarning("Скачивание аудио", "Сначала добавьте и выберите ссылку на видео.")
            return None
        if self.info.probe_error:
            messagebox.showwarning("Скачивание аудио", f"Сведения о видео недоступны: {self.info.probe_error}")
            return None

        output_dir = self.output_entry.get().strip() or str(self.app.filesystem.default_download_dir())
        return self.app.build_job(
            self.info,
            mode=DownloadMode.AUDIO.value,
            audio_format_id=self.track_panel.get_audio_format_id(),
            audio_format=self.format_menu.get(),
            audio_quality=self.quality_menu.get(),
            embed_thumbnail=bool(self.embed_thumb_check.get()),
            output_dir=output_dir,
        )

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
            size=(820, 320),
            card_title="Будет выполнено",
        )

    def start(self) -> None:
        job = self._build_job()
        if job is not None:
            self.on_start(job)
