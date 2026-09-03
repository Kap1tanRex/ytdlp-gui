"""Переиспользуемые панели выбора качества, звуковой дорожки и субтитров."""

from __future__ import annotations

import customtkinter as ctk

from ...core.models import SubtitleMode, VideoInfo
from .. import theme
from ..widgets.design import form_row, muted_label

_AUTO_LABEL = "Авто (лучшее качество)"
_CONTAINERS = ["mp4", "mkv", "webm"]
_SUBTITLE_MODE_LABELS = {
    "Не скачивать": SubtitleMode.NONE,
    "Вшить в видео": SubtitleMode.EMBED,
    "Отдельным файлом": SubtitleMode.EXTERNAL,
    "Вшить и сохранить отдельно": SubtitleMode.BOTH,
}


class QualitySelector(ctk.CTkFrame):
    """Выбор видеоформата и контейнера результата."""

    def __init__(self, master, app, *, label_width: int = 160) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._format_map: dict[str, str] = {}

        self.grid_columnconfigure(1, weight=1)

        self.format_menu = ctk.CTkOptionMenu(self, values=[_AUTO_LABEL], height=32)
        form_row(self, 0, "Качество видео", self.format_menu, label_width=label_width)

        self.container_menu = ctk.CTkOptionMenu(self, values=_CONTAINERS, height=32, width=240)
        form_row(self, 1, "Контейнер", self.container_menu, label_width=label_width, stretch=False)
        self.container_menu.set(self.app.settings.default_container)

        self.hint_label = muted_label(self, "", wraplength=380)
        self.hint_label.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(theme.GAP["xs"], 0))

    def set_info(self, info: VideoInfo | None) -> None:
        self._format_map = {}
        if info is None or not info.video_formats:
            self.format_menu.configure(values=[_AUTO_LABEL])
            self.format_menu.set(_AUTO_LABEL)
            self.hint_label.configure(text="")
            return

        formats = sorted(
            info.video_formats,
            key=lambda f: (f.height or 0, f.tbr or 0),
            reverse=True,
        )
        labels = [_AUTO_LABEL]
        for fmt in formats:
            label = fmt.describe()
            self._format_map[label] = fmt.format_id
            labels.append(label)

        self.format_menu.configure(values=labels)
        self.format_menu.set(_AUTO_LABEL)
        progressive = len(info.progressive_formats)
        self.hint_label.configure(
            text=(
                f"Доступно {len(formats)} видеопотоков. Прогрессивных (без слияния): {progressive}. "
                "Для слияния видео и звука нужен FFmpeg."
            )
        )

    def get_video_format_id(self) -> str | None:
        return self._format_map.get(self.format_menu.get())

    def get_container(self) -> str:
        return self.container_menu.get()


class AudioTrackSelector(ctk.CTkFrame):
    """Выбор звуковой дорожки (например, другого языка озвучки)."""

    def __init__(self, master, app, *, label_width: int = 160) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._format_map: dict[str, str] = {}

        self.grid_columnconfigure(1, weight=1)
        self.audio_menu = ctk.CTkOptionMenu(self, values=[_AUTO_LABEL], height=32)
        form_row(self, 0, "Звуковая дорожка", self.audio_menu, label_width=label_width)

    def set_info(self, info: VideoInfo | None) -> None:
        self._format_map = {}
        if info is None or not info.audio_formats:
            self.audio_menu.configure(values=[_AUTO_LABEL])
            self.audio_menu.set(_AUTO_LABEL)
            return

        labels = [_AUTO_LABEL]
        for fmt in info.audio_formats:
            label = fmt.describe()
            self._format_map[label] = fmt.format_id
            labels.append(label)
        self.audio_menu.configure(values=labels)
        self.audio_menu.set(_AUTO_LABEL)

    def get_audio_format_id(self) -> str | None:
        return self._format_map.get(self.audio_menu.get())


class SubtitlePanel(ctk.CTkFrame):
    """Выбор режима субтитров: не скачивать / вшить / отдельным файлом / оба."""

    def __init__(self, master, app, *, label_width: int = 160) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._checkboxes: dict[str, ctk.CTkCheckBox] = {}

        self.grid_columnconfigure(1, weight=1)

        self.mode_menu = ctk.CTkOptionMenu(
            self, values=list(_SUBTITLE_MODE_LABELS), command=self._on_mode_change, height=32, width=280
        )
        form_row(self, 0, "Субтитры", self.mode_menu, label_width=label_width, stretch=False)
        self.mode_menu.set("Не скачивать")

        self.langs_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.langs_frame.grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(theme.GAP["sm"], 0)
        )

        self.auto_subs_check = ctk.CTkCheckBox(
            self, text="Включая автоматические (сгенерированные) субтитры"
        )
        self.auto_subs_check.grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(theme.GAP["sm"], 0)
        )

        self._set_controls_enabled(False)

    def _on_mode_change(self, value: str) -> None:
        self._set_controls_enabled(value != "Не скачивать")

    def _set_controls_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for checkbox in self._checkboxes.values():
            checkbox.configure(state=state)
        self.auto_subs_check.configure(state=state)

    def set_info(self, info: VideoInfo | None) -> None:
        for widget in self.langs_frame.winfo_children():
            widget.destroy()
        self._checkboxes.clear()

        if info is None or not info.subtitles:
            hint = (
                "Выберите видео в списке — здесь появятся доступные языки"
                if info is None
                else "Субтитры для этого видео не найдены"
            )
            muted_label(self.langs_frame, hint).grid(row=0, column=0, sticky="w")
            return

        defaults = set(self.app.settings.subtitle_langs_default)
        columns = 6
        for index, lang in enumerate(info.subtitle_languages):
            checkbox = ctk.CTkCheckBox(self.langs_frame, text=lang, width=64)
            checkbox.grid(
                row=index // columns,
                column=index % columns,
                sticky="w",
                padx=(0, theme.GAP["md"]),
                pady=2,
            )
            if lang in defaults:
                checkbox.select()
            self._checkboxes[lang] = checkbox
        self._set_controls_enabled(self.mode_menu.get() != "Не скачивать")
        if self.app.settings.include_auto_subs_default:
            self.auto_subs_check.select()

    def get_options(self) -> tuple[str, list[str], bool]:
        mode = _SUBTITLE_MODE_LABELS.get(self.mode_menu.get(), SubtitleMode.NONE).value
        langs = [lang for lang, box in self._checkboxes.items() if box.get()]
        include_auto = bool(self.auto_subs_check.get())
        return mode, langs, include_auto
