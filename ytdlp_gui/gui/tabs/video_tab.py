"""Раздел «Видео»: выбор качества, звуковой дорожки, субтитров."""

from __future__ import annotations

from tkinter import filedialog, messagebox

import customtkinter as ctk

from ...core.models import DownloadMode, VideoInfo
from .. import theme
from ..widgets.design import Card, Page, button, muted_label, primary_button, title_label
from ..widgets.dialogs import text_dialog
from ._controls import AudioTrackSelector, QualitySelector, SubtitlePanel


class VideoTab(ctk.CTkFrame):
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

        self.subtitle_label = muted_label(header, "Скачивание видеопотока со звуком и субтитрами")
        self.subtitle_label.grid(row=1, column=0, sticky="ew", pady=(2, 0))

    def _build_page(self) -> None:
        # Прокручиваемая область нужна, т.к. содержимое (форматы, языки
        # субтитров) может стать выше окна — без неё кнопка «Скачать
        # видео» уезжала бы за пределы раздела и становилась недоступной.
        self.page = Page(self)
        self.page.grid(row=1, column=0, sticky="nsew")

        quality_card = Card(self.page, "Качество и звук")
        quality_card.body.grid_columnconfigure((0, 1), weight=1, uniform="quality")
        self.quality_panel = QualitySelector(quality_card.body, self.app)
        self.quality_panel.grid(row=0, column=0, sticky="new", padx=(0, theme.GAP["lg"]))
        self.audio_panel = AudioTrackSelector(quality_card.body, self.app)
        self.audio_panel.grid(row=0, column=1, sticky="new")
        self.page.add(quality_card)

        subtitle_card = Card(self.page, "Субтитры")
        self.subtitle_panel = SubtitlePanel(subtitle_card.body, self.app)
        self.subtitle_panel.grid(row=0, column=0, sticky="ew")
        self.page.add(subtitle_card)

        output_card = Card(self.page, "Сохранение")
        self._build_output(output_card.body)
        self.page.add(output_card)

    def _build_output(self, parent) -> None:
        parent.grid_columnconfigure(0, weight=1)

        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.grid(row=0, column=0, sticky="ew")
        row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(row, text="Папка загрузки", anchor="w", width=160).grid(
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

        self.embed_thumb_check = ctk.CTkCheckBox(parent, text="Встроить обложку в файл")
        self.embed_thumb_check.grid(row=1, column=0, sticky="w", pady=(theme.GAP["sm"], 0))
        if self.app.settings.embed_thumbnail_default:
            self.embed_thumb_check.select()

    def _build_actions(self) -> None:
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=2, column=0, sticky="ew", pady=(theme.GAP["md"], 0))
        frame.grid_columnconfigure(0, weight=1)

        button(frame, "Показать команду yt-dlp", self._show_command).grid(row=0, column=0, sticky="w")
        primary_button(frame, "Скачать видео", self.start, width=180).grid(row=0, column=1, sticky="e")

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
        self.quality_panel.set_info(info)
        self.audio_panel.set_info(info)
        self.subtitle_panel.set_info(info)

    # -- сборка задания ------------------------------------------------------
    def _build_job(self):
        if self.info is None:
            messagebox.showwarning("Скачивание видео", "Сначала добавьте и выберите ссылку на видео.")
            return None
        if self.info.probe_error:
            messagebox.showwarning("Скачивание видео", f"Сведения о видео недоступны: {self.info.probe_error}")
            return None

        subtitle_mode, subtitle_langs, include_auto = self.subtitle_panel.get_options()
        output_dir = self.output_entry.get().strip() or str(self.app.filesystem.default_download_dir())

        return self.app.build_job(
            self.info,
            mode=DownloadMode.VIDEO.value,
            video_format_id=self.quality_panel.get_video_format_id(),
            audio_format_id=self.audio_panel.get_audio_format_id(),
            container=self.quality_panel.get_container(),
            subtitle_mode=subtitle_mode,
            subtitle_langs=subtitle_langs,
            include_auto_subs=include_auto,
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
