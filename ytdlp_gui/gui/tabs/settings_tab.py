"""Настройки (design-system §7.4).

Заголовок страницы, ниже разделы с заголовками Display 17 в колонке до
900 px: инструменты, обновления yt-dlp, сеть, загрузки, значения по
умолчанию, интерфейс, диагностика и горячие клавиши. Всё сохраняется
сразу, кнопок «Применить» нет.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from ...app.state import APP_VERSION
from ...services.filesystem_service import open_folder
from .. import fmt, theme
from ..widgets.design import (
    Btn,
    Column,
    Dropdown,
    Field,
    Line,
    MonoRow,
    PageTitle,
    Panel,
    Para,
    SectionTitle,
    Seg,
    box,
    field_label,
    text,
    toggle,
)
from ..widgets.dialogs import text_dialog
from ..widgets.layout import ScrollPage

#: Браузеры, из которых yt-dlp умеет читать cookies (``--cookies-from-browser``).
#: Ключ — то, что видит пользователь; значение — то, что уходит в yt-dlp.
_NO_BROWSER = "Не использовать"
_BROWSERS = {
    _NO_BROWSER: "",
    "Chrome": "chrome",
    "Edge": "edge",
    "Firefox": "firefox",
    "Brave": "brave",
    "Chromium": "chromium",
    "Opera": "opera",
    "Vivaldi": "vivaldi",
    "Whale": "whale",
}
if sys.platform == "darwin":
    _BROWSERS["Safari"] = "safari"
_BROWSER_BY_VALUE = {value: label for label, value in _BROWSERS.items()}

_PARALLEL = [(str(n), str(n)) for n in range(1, 5)]
_OVERWRITE = [("skip", "Пропускать"), ("overwrite", "Перезаписывать")]
_CONTAINERS = [("mp4", "MP4"), ("mkv", "MKV"), ("webm", "WEBM")]
_AUDIO_FORMATS = [
    ("mp3", "MP3"),
    ("m4a", "M4A"),
    ("opus", "OPUS"),
    ("flac", "FLAC"),
    ("wav", "WAV"),
    ("best", "Как есть"),
]
_BITRATES = [
    ("320", "320"), ("256", "256"), ("192", "192"), ("128", "128"),
    ("96", "96"), ("64", "64"), ("0", "Макс"),
]
_DEFAULT_TEMPLATE = "%(title).200B [%(id)s].%(ext)s"

HOTKEYS = (
    ("Enter", "Добавить ссылку из поля ввода"),
    ("Ctrl+V", "Вставить ссылку из буфера и добавить (вне поля ввода)"),
    ("Delete", "Убрать выбранное видео из списка"),
    ("Ctrl+Enter", "Скачать выбранное видео"),
    ("Esc", "Остановить текущую загрузку"),
    ("Ctrl+1 · 2 · 3", "Главная · Очередь · Настройки"),
    ("Ctrl+L", "Журнал yt-dlp"),
    ("Ctrl+U", "Проверить обновления yt-dlp"),
    ("Ctrl+= · Ctrl+−", "Крупнее · мельче"),
    ("Ctrl+0", "Масштаб 100 %"),
    ("F1", "Справка"),
)

#: Уровень важности -> цвет строки состояния.
_SEVERITY = {"ok": theme.OK, "warning": theme.WARN, "error": theme.ERR, "info": theme.DIM, "busy": theme.DIM}


def _short_path(path: Path | str) -> str:
    """Путь с ``%APPDATA%`` / ``%USERPROFILE%`` вместо начала — короче и без имени пользователя."""
    value = str(path)
    for variable in ("LOCALAPPDATA", "APPDATA", "USERPROFILE"):
        prefix = os.environ.get(variable)
        if prefix and value.lower().startswith(prefix.lower()):
            return f"%{variable}%{value[len(prefix):]}"
    return value


class _ToolCard(Panel):
    """Карточка инструмента (как карточка исполнителя «Стемницы», 58 px)."""

    def __init__(self, master, name: str, command: Callable[[], None]) -> None:
        super().__init__(master, height=58)
        self.grid_propagate(False)
        self.grid_rowconfigure((0, 1), weight=1)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.led = ctk.CTkFrame(self, width=6, height=6, corner_radius=3, fg_color=theme.FAINT)
        self.led.grid(row=0, column=0, rowspan=2, padx=(18, 12))
        self.name = name
        self.title = Line(self, name, font=theme.sans_medium(14))
        self.title.grid(row=0, column=1, sticky="sew")
        self.detail = Line(self, "", font=theme.mono(11), color=theme.FAINT)
        self.detail.grid(row=1, column=1, sticky="new", pady=(2, 0))
        self.status = text(self, "", font=theme.sans(12), anchor="e")
        self.status.grid(row=0, column=2, rowspan=2, padx=(12, 12))
        Btn(self, "Изменить…", command, size="sm").grid(row=0, column=3, rowspan=2, padx=(0, 14))

    def set(self, version: str, path: Path | None, *, missing_level: str, missing_text: str) -> None:
        if path is not None:
            self.led.configure(fg_color=theme.AMBER)
            self.title.set(fmt.join(self.name, version))
            self.detail.set(_short_path(path))
            self.status.configure(text="найден", text_color=theme.OK)
        else:
            color = theme.ERR if missing_level == "error" else theme.WARN
            self.led.configure(fg_color=color)
            self.title.set(self.name)
            self.detail.set(missing_text)
            self.status.configure(text="не найден", text_color=color)


class SettingsPage(ScrollPage):
    def __init__(
        self,
        master,
        app,
        *,
        on_settings_changed: Callable[[], None],
        on_defaults_changed: Callable[[], None],
        on_check_updates: Callable[[], None],
        on_show_logs: Callable[[], None],
    ) -> None:
        super().__init__(master)
        self.app = app
        self.on_settings_changed = on_settings_changed
        self.on_defaults_changed = on_defaults_changed
        self.on_check_updates = on_check_updates
        self.on_show_logs = on_show_logs
        self._loading = True

        self.body.grid_columnconfigure(0, weight=0)
        self.body.grid_columnconfigure(1, weight=1)
        self.column = Column(self.body)
        self.column.grid(row=0, column=0, sticky="new")

        heading = PageTitle(
            self.column,
            "Настройки",
            fmt.join(f"yt-dlp GUI {APP_VERSION}", f"данные в {_short_path(app.store.directory)}"),
        )
        self.column.add(heading, pady=(40, 4))

        self._build_tools()
        self._build_updates()
        self._build_network()
        self._build_downloads()
        self._build_defaults()
        self._build_interface()
        self._build_diagnostics()
        self._build_hotkeys()

        self._load_from_settings()
        self._loading = False

    def on_width(self, width: int) -> None:
        minsize = round(min(theme.SETTINGS_WIDTH, width) * theme.widget_scale(self))
        self.body.grid_columnconfigure(0, minsize=minsize)

    # -- общие куски ---------------------------------------------------------
    def _section(self, title: str) -> Column:
        self.column.add(SectionTitle(self.column, title), pady=(28, 12), sticky="w")
        body = Column(self.column)
        self.column.add(body)
        return body

    @staticmethod
    def _caption(body: Column, value: str, *, first: bool = False) -> None:
        body.add(field_label(body, value), pady=(0 if first else 16, 7), sticky="w")

    # -- инструменты -----------------------------------------------------------
    def _build_tools(self) -> None:
        body = self._section("Инструменты")
        self.ytdlp_card = _ToolCard(body, "yt-dlp", self._browse_ytdlp)
        body.add(self.ytdlp_card)
        self.ffmpeg_card = _ToolCard(body, "FFmpeg", self._browse_ffmpeg)
        body.add(self.ffmpeg_card, pady=(8, 0))
        body.add(
            Para(
                body,
                "Программа ищет их рядом с собой, в папке bin, в PATH и в системных каталогах. "
                "FFmpeg нужен для склейки видео со звуком, извлечения звука, субтитров и обложек.",
                font=theme.sans(12),
                color=theme.FAINT,
            ),
            pady=(10, 0),
        )

    def _browse_ytdlp(self) -> None:
        path = filedialog.askopenfilename(title="Где лежит yt-dlp", parent=self.winfo_toplevel())
        if path:
            binaries = self.app.ytdlp.binaries
            self.app.set_tool_paths(path, str(binaries.ffmpeg or ""))
            self.update_tools_status()

    def _browse_ffmpeg(self) -> None:
        path = filedialog.askopenfilename(title="Где лежит ffmpeg", parent=self.winfo_toplevel())
        if path:
            binaries = self.app.ytdlp.binaries
            self.app.set_tool_paths(str(binaries.ytdlp or ""), path)
            self.update_tools_status()

    def update_tools_status(self) -> None:
        binaries = self.app.ytdlp.binaries
        self.ytdlp_card.set(
            binaries.ytdlp_version,
            binaries.ytdlp,
            missing_level="error",
            missing_text="без него загрузка невозможна — укажите yt-dlp.exe",
        )
        self.ffmpeg_card.set(
            binaries.ffmpeg_version,
            binaries.ffmpeg,
            missing_level="warning",
            missing_text="склейка потоков, звук, субтитры и обложки недоступны",
        )
        self.version_row.set_value(binaries.ytdlp_version or "не определена")

    # -- обновления --------------------------------------------------------------
    def _build_updates(self) -> None:
        body = self._section("Обновления yt-dlp")
        self.version_row = MonoRow(body, "Установленная версия")
        body.add(self.version_row)
        self.update_status = Para(body, "", font=theme.sans(13), color=theme.DIM)
        body.add(self.update_status, pady=(12, 0))

        buttons = box(body)
        Btn(buttons, "Проверить обновления", lambda: self.on_check_updates()).grid(row=0, column=0)
        Btn(buttons, "Что нового", self._show_release_history, kind="quiet").grid(
            row=0, column=1, padx=(8, 0)
        )
        body.add(buttons, pady=(12, 0), sticky="w")

        self.auto_update = toggle(body, "Проверять обновления при запуске", self._on_auto_update)
        body.add(self.auto_update, pady=(16, 0), sticky="w")
        body.add(
            Para(
                body,
                "YouTube меняется часто, и устаревший yt-dlp перестаёт скачивать. Проверка "
                "обращается к GitHub и ничего не ставит сама: что скачать, решаете вы в окне "
                "со списком изменений.",
                font=theme.sans(12),
                color=theme.FAINT,
            ),
            pady=(6, 0),
        )

    def _show_release_history(self) -> None:
        self.set_update_status("Загружаю список релизов…", "info")
        self.app.load_release_history(limit=10, only_new=False)

    def _on_auto_update(self) -> None:
        self.app.update_settings(check_updates_on_start=bool(self.auto_update.get()))

    def set_update_status(self, message: str, severity: str = "info") -> None:
        self.update_status.configure(text=message, text_color=_SEVERITY.get(severity, theme.DIM))

    def refresh_update_status(self) -> None:
        stamp = getattr(self.app.settings, "last_update_check", "")[:10]
        self.set_update_status(
            f"Последняя проверка: {fmt.date(stamp.replace('-', ''))}." if stamp else "Проверок ещё не было.",
            "info",
        )

    # -- сеть -------------------------------------------------------------------
    def _build_network(self) -> None:
        body = self._section("Сеть")
        self._caption(body, "Прокси", first=True)
        self.proxy_entry = Field(body, placeholder_text="socks5://127.0.0.1:1080")
        self.proxy_entry.bind("<FocusOut>", lambda _e: self._on_network_changed())
        body.add(self.proxy_entry)

        self._caption(body, "Cookies из браузера")
        self.browser_menu = Dropdown(
            body, list(_BROWSERS), command=lambda _v: self._on_browser_changed(), width=260
        )
        body.add(self.browser_menu, sticky="w")

        self._caption(body, "Файл cookies (Netscape)")
        cookies_row = box(body)
        cookies_row.grid_columnconfigure(0, weight=1)
        self.cookies_entry = Field(
            cookies_row, placeholder_text="cookies.txt — для приватных и возрастных видео"
        )
        self.cookies_entry.grid(row=0, column=0, sticky="ew")
        self.cookies_entry.bind("<FocusOut>", lambda _e: self._on_network_changed())
        self.cookies_button = Btn(cookies_row, "Выбрать…", self._browse_cookies, size="sm")
        self.cookies_button.grid(row=0, column=1, padx=(8, 0))
        body.add(cookies_row)
        self.cookies_hint = Para(body, "", font=theme.sans(12), color=theme.FAINT)
        body.add(self.cookies_hint, pady=(8, 0))

        self._caption(body, "Ограничение скорости")
        self.limit_rate_entry = Field(body, placeholder_text="например, 2M", width=200)
        self.limit_rate_entry.bind("<FocusOut>", lambda _e: self._on_network_changed())
        body.add(self.limit_rate_entry, sticky="w")

    def _browse_cookies(self) -> None:
        path = filedialog.askopenfilename(
            title="Файл cookies (Netscape)", parent=self.winfo_toplevel()
        )
        if path:
            self.cookies_entry.set_text(path)
            self._on_network_changed()

    def _on_browser_changed(self) -> None:
        self._on_network_changed()
        self._sync_cookies_controls()

    def _selected_browser(self) -> str:
        return _BROWSERS.get(self.browser_menu.get(), "")

    def _sync_cookies_controls(self) -> None:
        """Файл и браузер — альтернативы: активна ровно одна из них."""
        browser = self._selected_browser()
        self.cookies_entry.set_enabled(not browser)
        self.cookies_button.set_enabled(not browser)
        if browser:
            self.cookies_hint.configure(
                text=(
                    f"Cookies читаются из {self.browser_menu.get()} при каждом запуске yt-dlp — "
                    "вход в браузере подхватывается сам. Браузер лучше закрыть: он держит базу "
                    "cookies заблокированной. Файл cookies не используется."
                )
            )
        else:
            self.cookies_hint.configure(
                text=(
                    "Cookies нужны для приватных, возрастных и требующих входа видео: их можно "
                    "взять прямо из браузера или указать файл."
                )
            )

    def _on_network_changed(self) -> None:
        if self._loading:
            return
        self.app.update_settings(
            proxy=self.proxy_entry.get().strip(),
            cookies_file=self.cookies_entry.get().strip(),
            cookies_from_browser=self._selected_browser(),
            limit_rate=self.limit_rate_entry.get().strip(),
        )

    # -- загрузки ---------------------------------------------------------------
    def _build_downloads(self) -> None:
        body = self._section("Загрузки")
        self._caption(body, "Одновременных загрузок", first=True)
        self.parallel_seg = Seg(
            body,
            _PARALLEL,
            command=lambda v: self.app.update_settings(parallel_jobs=int(v)),
            height=32,
            width=260,
        )
        body.add(self.parallel_seg, sticky="w")

        self._caption(body, "Если файл уже есть")
        self.overwrite_seg = Seg(
            body,
            _OVERWRITE,
            command=lambda v: self.app.update_settings(overwrite_policy=v),
            height=32,
            width=420,
        )
        body.add(self.overwrite_seg, sticky="w")

        self.output_row = MonoRow(body, "Папка загрузки")
        self.output_row.add_action(
            Btn(self.output_row.actions, "Изменить…", self._browse_output_dir, kind="quiet", size="sm")
        )
        body.add(self.output_row, pady=(14, 0))

        self._caption(body, "Шаблон имени файла")
        self.template_entry = Field(body)
        self.template_entry.bind("<FocusOut>", lambda _e: self._on_template_changed())
        body.add(self.template_entry)
        body.add(
            text(
                body,
                "переменные yt-dlp: %(title)s, %(id)s, %(uploader)s, %(upload_date)s, %(ext)s",
                font=theme.mono(11),
                color=theme.FAINT,
            ),
            pady=(6, 0),
            sticky="w",
        )

        self.playlist_toggle = toggle(
            body,
            "Скачивать плейлист целиком, если ссылка ведёт на плейлист",
            lambda: self.app.update_settings(download_playlists=bool(self.playlist_toggle.get())),
        )
        body.add(self.playlist_toggle, pady=(18, 0), sticky="w")
        self.restrict_toggle = toggle(
            body,
            "Безопасные имена файлов: только латиница, без пробелов",
            lambda: self.app.update_settings(restrict_filenames=bool(self.restrict_toggle.get())),
        )
        body.add(self.restrict_toggle, pady=(12, 0), sticky="w")

    def _browse_output_dir(self) -> None:
        path = filedialog.askdirectory(
            title="Папка загрузки по умолчанию", parent=self.winfo_toplevel()
        )
        if path:
            self.app.update_settings(output_directory=path)
            self._sync_output_row()

    def _sync_output_row(self) -> None:
        folder = self.app.settings.output_directory or str(self.app.filesystem.default_download_dir())
        self.output_row.set_value(_short_path(folder))

    def _on_template_changed(self) -> None:
        self.app.update_settings(output_template=self.template_entry.get().strip() or _DEFAULT_TEMPLATE)

    # -- значения по умолчанию ---------------------------------------------------
    def _build_defaults(self) -> None:
        body = self._section("По умолчанию")
        self._caption(body, "Контейнер видео", first=True)
        self.container_seg = Seg(body, _CONTAINERS, command=self._on_defaults_changed, height=32, width=260)
        body.add(self.container_seg, sticky="w")
        self._caption(body, "Формат звука")
        self.audio_format_seg = Seg(
            body, _AUDIO_FORMATS, command=self._on_defaults_changed, height=32, width=560
        )
        body.add(self.audio_format_seg, sticky="w")
        self._caption(body, "Битрейт звука, кбит/с")
        self.audio_quality_seg = Seg(body, _BITRATES, command=self._on_defaults_changed, height=32, width=560)
        body.add(self.audio_quality_seg, sticky="w")

        self._caption(body, "Языки субтитров")
        self.subtitle_langs_entry = Field(body, placeholder_text="ru, en", width=260)
        self.subtitle_langs_entry.bind("<FocusOut>", lambda _e: self._on_defaults_changed())
        body.add(self.subtitle_langs_entry, sticky="w")

        self.metadata_toggle = toggle(
            body, "Встраивать метаданные: название и автора", self._on_defaults_changed
        )
        body.add(self.metadata_toggle, pady=(18, 0), sticky="w")
        self.chapters_toggle = toggle(body, "Встраивать главы", self._on_defaults_changed)
        body.add(self.chapters_toggle, pady=(12, 0), sticky="w")
        self.thumbnail_toggle = toggle(body, "Встраивать обложку", self._on_defaults_changed)
        body.add(self.thumbnail_toggle, pady=(12, 0), sticky="w")
        self.auto_subs_toggle = toggle(body, "Включать автоматические субтитры", self._on_defaults_changed)
        body.add(self.auto_subs_toggle, pady=(12, 0), sticky="w")
        body.add(
            Para(
                body,
                "Эти значения сразу выставляются на главной и применяются к новым загрузкам.",
                font=theme.sans(12),
                color=theme.FAINT,
            ),
            pady=(8, 0),
        )

    def _on_defaults_changed(self, _value: str | None = None) -> None:
        if self._loading:
            return
        langs = [part.strip() for part in self.subtitle_langs_entry.get().split(",") if part.strip()]
        self.app.update_settings(
            default_container=self.container_seg.get() or "mp4",
            default_audio_format=self.audio_format_seg.get() or "mp3",
            default_audio_quality=self.audio_quality_seg.get() or "192",
            embed_metadata_default=bool(self.metadata_toggle.get()),
            embed_chapters_default=bool(self.chapters_toggle.get()),
            embed_thumbnail_default=bool(self.thumbnail_toggle.get()),
            include_auto_subs_default=bool(self.auto_subs_toggle.get()),
            subtitle_langs_default=langs,
        )
        self.on_defaults_changed()

    # -- интерфейс -----------------------------------------------------------------
    def _build_interface(self) -> None:
        body = self._section("Интерфейс")
        self._caption(body, "Масштаб", first=True)
        row = box(body)
        # Ползунок — грубая настройка с шагом 5 %; точно — Ctrl+=, Ctrl+− и Ctrl+0.
        self.scale_slider = ctk.CTkSlider(
            row,
            from_=theme.MIN_SCALE * 100,
            to=theme.MAX_SCALE * 100,
            number_of_steps=len(_SCALE_PRESETS) - 1,
            command=self._on_scale_slide,
            width=200,
            height=12,
            border_width=5,
            button_length=5,
            button_corner_radius=2,
            corner_radius=1,
        )
        self.scale_slider.grid(row=0, column=0)
        self.scale_slider.bind("<ButtonRelease-1>", self._on_scale_release)
        self.scale_value = text(row, "", font=theme.mono(12))
        self.scale_value.grid(row=0, column=1, padx=(14, 0))
        Btn(row, "Сбросить", self._reset_scale, kind="quiet", size="sm").grid(row=0, column=2, padx=(12, 0))
        body.add(row, sticky="w")
        body.add(
            Para(
                body,
                f"От {int(theme.MIN_SCALE * 100)} до {int(theme.MAX_SCALE * 100)} %. Интерфейс только "
                "тёмный — как у «Стемницы», на тёмный фон рассчитан контраст цветов.",
                font=theme.sans(12),
                color=theme.FAINT,
            ),
            pady=(8, 0),
        )
        self.tooltips_toggle = toggle(
            body,
            "Подсказки при наведении",
            lambda: self.app.update_settings(show_tooltips=bool(self.tooltips_toggle.get())),
        )
        body.add(self.tooltips_toggle, pady=(16, 0), sticky="w")

    def _on_scale_slide(self, value: float) -> None:
        """Живое применение при перетаскивании — без записи на диск."""
        scale = theme.normalize_scale(round(value) / 100)
        self.scale_value.configure(text=f"{theme.scale_percent(scale)}{fmt.THIN}%")
        if self._loading:
            return
        self.app.settings.ui_scale = scale
        self.on_settings_changed()

    def _on_scale_release(self, _event=None) -> None:
        """Сохранение — один раз, когда ползунок отпущен."""
        scale = theme.normalize_scale(round(self.scale_slider.get()) / 100)
        self.app.update_settings(ui_scale=scale)
        self.on_settings_changed()

    def _reset_scale(self) -> None:
        self.app.update_settings(ui_scale=1.0)
        self.on_settings_changed()

    def sync_ui_scale(self, scale: float) -> None:
        """Подтягивает ползунок, если масштаб сменили горячей клавишей."""
        percent = theme.scale_percent(scale)
        if int(round(self.scale_slider.get())) != percent:
            self.scale_slider.set(percent)
        self.scale_value.configure(text=f"{percent}{fmt.THIN}%")

    # -- диагностика ---------------------------------------------------------------
    def _build_diagnostics(self) -> None:
        body = self._section("Диагностика")
        logs = self.app.store.logs_dir
        row = MonoRow(body, "Журналы", _short_path(logs))
        row.add_action(Btn(row.actions, "Открыть", lambda: open_folder(logs), kind="quiet", size="sm"))
        body.add(row)
        buttons = box(body)
        Btn(buttons, "Отчёт", self._show_diagnostics).grid(row=0, column=0)
        Btn(buttons, "Журнал yt-dlp", lambda: self.on_show_logs(), kind="quiet").grid(
            row=0, column=1, padx=(8, 0)
        )
        body.add(buttons, pady=(14, 0), sticky="w")

    def _show_diagnostics(self) -> None:
        text_dialog(
            self,
            "Диагностика",
            self.app.diagnostics().to_text(),
            mono=True,
            size=(700, 460),
            info=f"yt-dlp gui {APP_VERSION}",
        )

    # -- горячие клавиши -----------------------------------------------------------
    def _build_hotkeys(self) -> None:
        body = self._section("Горячие клавиши")
        table = box(body)
        table.grid_columnconfigure(0, minsize=round(220 * theme.widget_scale(self)))
        for index, (keys, description) in enumerate(HOTKEYS):
            text(table, keys, font=theme.mono(12)).grid(row=index, column=0, sticky="w", pady=4)
            text(table, description, font=theme.sans(13), color=theme.DIM).grid(
                row=index, column=1, sticky="w", pady=4
            )
        body.add(table, sticky="w")

    # -- начальные значения ----------------------------------------------------------
    def _load_from_settings(self) -> None:
        settings = self.app.settings
        self.sync_ui_scale(getattr(settings, "ui_scale", 1.0))
        self.parallel_seg.set(str(settings.parallel_jobs))
        policy = settings.overwrite_policy
        self.overwrite_seg.set(policy if policy in dict(_OVERWRITE) else "skip")
        self._sync_output_row()
        self.template_entry.set_text(settings.output_template)
        for switch, value in (
            (self.playlist_toggle, settings.download_playlists),
            (self.restrict_toggle, settings.restrict_filenames),
            (self.tooltips_toggle, settings.show_tooltips),
            (self.auto_update, getattr(settings, "check_updates_on_start", False)),
            (self.metadata_toggle, settings.embed_metadata_default),
            (self.chapters_toggle, settings.embed_chapters_default),
            (self.thumbnail_toggle, settings.embed_thumbnail_default),
            (self.auto_subs_toggle, settings.include_auto_subs_default),
        ):
            if value:
                switch.select()
            else:
                switch.deselect()
        self.refresh_update_status()

        self.proxy_entry.set_text(settings.proxy)
        self.cookies_entry.set_text(settings.cookies_file)
        browser = getattr(settings, "cookies_from_browser", "")
        self.browser_menu.set(_BROWSER_BY_VALUE.get(browser, _NO_BROWSER))
        self._sync_cookies_controls()
        self.limit_rate_entry.set_text(settings.limit_rate)

        self.container_seg.set(settings.default_container)
        self.audio_format_seg.set(settings.default_audio_format)
        self.audio_quality_seg.set(settings.default_audio_quality)
        self.subtitle_langs_entry.set_text(", ".join(settings.subtitle_langs_default))
        self.update_tools_status()


#: Предустановки масштаба интерфейса — весь допустимый диапазон с шагом 5 %.
_SCALE_PRESETS = list(range(int(theme.MIN_SCALE * 100), int(theme.MAX_SCALE * 100) + 1, 5))
