"""Раздел «Информация»: превью, метаданные и список всех форматов."""

from __future__ import annotations

import threading
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from ...core.models import VideoInfo, format_size
from ...services.filesystem_service import sanitize_filename
from ...services.thumbnail_service import ThumbnailSaveError
from .. import theme
from ..widgets.design import Card, button, muted_label, title_label
from ..widgets.thumbnail_view import ThumbnailView


class InfoTab(ctk.CTkFrame):
    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.info: VideoInfo | None = None
        self._fetch_token = 0

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_formats()

        # Стартовое состояние — то же, что и при пустом списке видео.
        self.set_info(None)

    def _build_header(self) -> None:
        card = Card(self, "Сведения о видео")
        card.grid(row=0, column=0, sticky="ew", pady=(0, theme.GAP["md"]))
        body = card.body
        body.grid_columnconfigure(1, weight=1)

        self.thumbnail = ThumbnailView(body, width=240, height=135)
        self.thumbnail.grid(row=0, column=0, sticky="nw", padx=(0, theme.GAP["lg"]))

        meta = ctk.CTkFrame(body, fg_color="transparent")
        meta.grid(row=0, column=1, sticky="new")
        meta.grid_columnconfigure(0, weight=1)
        meta.grid_rowconfigure(3, weight=1)

        self.title_label = title_label(meta, "Видео не выбрано")
        self.title_label.configure(wraplength=520)
        self.title_label.grid(row=0, column=0, sticky="ew")

        self.meta_label = ctk.CTkLabel(meta, text="", anchor="w", justify="left", wraplength=520)
        self.meta_label.grid(row=1, column=0, sticky="ew", pady=(theme.GAP["sm"], 0))

        self.url_label = muted_label(meta, "", wraplength=520)
        self.url_label.grid(row=2, column=0, sticky="ew", pady=(theme.GAP["sm"], 0))

        self.save_thumb_button = button(meta, "Сохранить превью…", self._save_thumbnail, width=190)
        self.save_thumb_button.grid(row=3, column=0, sticky="sw", pady=(theme.GAP["md"], 0))

    def _build_formats(self) -> None:
        card = Card(self, "Доступные форматы")
        card.grid(row=1, column=0, sticky="nsew")
        card.body.grid_rowconfigure(0, weight=1)
        card.body.grid_columnconfigure(0, weight=1)

        self.formats_box = ctk.CTkTextbox(
            card.body, wrap="none", height=180, font=theme.font("small", mono=True)
        )
        self.formats_box.grid(row=0, column=0, sticky="nsew")
        self.formats_box.configure(state="disabled")

    # -- данные ------------------------------------------------------------
    def set_info(self, info: VideoInfo | None) -> None:
        self.info = info
        self._fetch_token += 1
        token = self._fetch_token

        if info is None:
            self.title_label.configure(text="Видео не выбрано")
            self.meta_label.configure(text="")
            self.url_label.configure(text="")
            self.thumbnail.clear()
            self._set_formats_text("")
            return

        if info.probe_error:
            self.title_label.configure(text=info.url)
            self.meta_label.configure(text=f"Ошибка: {info.probe_error}")
            self.url_label.configure(text="")
            self.thumbnail.clear()
            self._set_formats_text("")
            return

        self.title_label.configure(text=info.title or info.id or info.url)
        details = []
        if info.uploader:
            details.append(f"Канал: {info.uploader}")
        if info.duration:
            details.append(f"Длительность: {info.duration_text()}")
        if info.view_count:
            details.append(f"Просмотров: {info.view_count:,}".replace(",", " "))
        if info.upload_date and len(info.upload_date) == 8:
            details.append(f"Дата: {info.upload_date[6:8]}.{info.upload_date[4:6]}.{info.upload_date[0:4]}")
        self.meta_label.configure(text="   •   ".join(details))
        self.url_label.configure(text=info.webpage_url or info.url)

        self._set_formats_text(self._format_table(info))

        if info.thumbnail_url:
            self.thumbnail.show_loading()
            threading.Thread(target=self._fetch_thumbnail, args=(info, token), daemon=True).start()
        else:
            self.thumbnail.clear()

    def _fetch_thumbnail(self, info: VideoInfo, token: int) -> None:
        path = self.app.thumbnail_path(info)
        self.after(0, self._apply_thumbnail, path, token)

    def _apply_thumbnail(self, path, token: int) -> None:
        if token != self._fetch_token:
            return
        self.thumbnail.show_path(path)

    # -- сохранение превью ---------------------------------------------------
    def _save_thumbnail(self) -> None:
        if self.info is None or self.info.probe_error:
            messagebox.showwarning("Сохранение превью", "Сначала добавьте и выберите ссылку на видео.")
            return
        if not self.info.thumbnail_url:
            messagebox.showwarning("Сохранение превью", "У этого видео нет превью.")
            return

        suggested_name = sanitize_filename(self.info.title or self.info.id or "thumbnail")
        dest = filedialog.asksaveasfilename(
            title="Сохранить превью",
            initialfile=f"{suggested_name}.jpg",
            defaultextension=".jpg",
            filetypes=[("JPEG", "*.jpg *.jpeg"), ("PNG", "*.png")],
        )
        if not dest:
            return

        info = self.info
        self.save_thumb_button.configure(state="disabled", text="Сохранение…")
        threading.Thread(target=self._save_thumbnail_worker, args=(info, Path(dest)), daemon=True).start()

    def _save_thumbnail_worker(self, info: VideoInfo, dest: Path) -> None:
        error: str | None = None
        try:
            self.app.save_thumbnail(info, dest)
        except ThumbnailSaveError as exc:
            error = str(exc)
        except Exception as exc:  # noqa: BLE001 - показываем любую ошибку пользователю
            error = str(exc)
        self.after(0, self._thumbnail_saved, dest, error)

    def _thumbnail_saved(self, dest: Path, error: str | None) -> None:
        self.save_thumb_button.configure(state="normal", text="Сохранить превью…")
        if error:
            messagebox.showerror("Сохранение превью", f"Не удалось сохранить превью:\n{error}")
        else:
            messagebox.showinfo("Сохранение превью", f"Превью сохранено:\n{dest}")

    def _set_formats_text(self, text: str) -> None:
        self.formats_box.configure(state="normal")
        self.formats_box.delete("1.0", "end")
        self.formats_box.insert("1.0", text)
        self.formats_box.configure(state="disabled")

    @staticmethod
    def _format_table(info: VideoInfo) -> str:
        if not info.formats:
            return "Список форматов недоступен."
        header = f"{'ID':<10}{'EXT':<6}{'РАЗРЕШЕНИЕ':<20}{'ВИДЕО':<12}{'АУДИО':<10}{'БИТРЕЙТ':<14}{'ЯЗЫК':<8}{'РАЗМЕР':<10}"
        lines = [header, "-" * len(header)]
        ordered = sorted(
            info.formats,
            key=lambda f: (not f.has_video, -(f.height or 0), -(f.tbr or f.abr or 0)),
        )
        for fmt in ordered:
            lines.append(
                f"{fmt.format_id:<10}{fmt.ext:<6}{fmt.resolution_text:<20}"
                f"{(fmt.vcodec or '-').split('.')[0]:<12}{(fmt.acodec or '-').split('.')[0]:<10}"
                f"{fmt.bitrate_text:<14}{(fmt.language or '-'):<8}{format_size(fmt.size):<10}"
            )
        return "\n".join(lines)
