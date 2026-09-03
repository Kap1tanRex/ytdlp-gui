"""Раздел «Настройки»: инструменты, внешний вид, сеть, значения по умолчанию."""

from __future__ import annotations

import sys
from tkinter import filedialog

import customtkinter as ctk

from .. import theme
from ..widgets.design import (
    Card,
    Page,
    button,
    form_frame,
    form_row,
    muted_label,
    primary_button,
    status_label,
)
from ..widgets.dialogs import text_dialog

#: Браузеры, из которых yt-dlp умеет читать cookies (``--cookies-from-browser``).
#: Значение — то, что уходит в yt-dlp; ключ — то, что видит пользователь.
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

_OVERWRITE_LABELS = {"skip": "Пропускать существующие", "overwrite": "Перезаписывать"}
_OVERWRITE_BY_LABEL = {v: k for k, v in _OVERWRITE_LABELS.items()}
_CONTAINERS = ["mp4", "mkv", "webm"]
_AUDIO_FORMATS = ["mp3", "m4a", "opus", "flac", "wav", "best"]
_THEMES = {"System": "Системная", "Light": "Светлая", "Dark": "Тёмная"}
_THEME_BY_LABEL = {v: k for k, v in _THEMES.items()}

_LABEL_WIDTH = 260


class SettingsTab(Page):
    def __init__(self, master, app, on_settings_changed) -> None:
        super().__init__(master)
        self.app = app
        self.on_settings_changed = on_settings_changed
        self._loading = True

        self._build_tools_section()
        self._build_updates_section()
        self._build_appearance_section()
        self._build_network_section()
        self._build_general_section()
        self._build_defaults_section()
        self._build_diagnostics_section()

        self._load_from_settings()
        self._loading = False

    # -- yt-dlp / FFmpeg ---------------------------------------------------
    def _build_tools_section(self) -> None:
        card = Card(self, "Инструменты", subtitle="Пути к yt-dlp и FFmpeg")
        body = card.body

        self.tools_status_label = status_label(body, "", "info")
        self.tools_status_label.configure(wraplength=620)
        self.tools_status_label.grid(row=0, column=0, sticky="ew", pady=(0, theme.GAP["sm"]))

        form = form_frame(body, 1)

        self.ytdlp_path_entry = ctk.CTkEntry(form, height=32)
        form_row(
            form,
            0,
            "Путь к yt-dlp",
            self.ytdlp_path_entry,
            trailing=button(form, "Обзор", self._browse_ytdlp, width=90),
            label_width=_LABEL_WIDTH,
        )

        self.ffmpeg_path_entry = ctk.CTkEntry(form, height=32)
        form_row(
            form,
            1,
            "Путь к ffmpeg",
            self.ffmpeg_path_entry,
            trailing=button(form, "Обзор", self._browse_ffmpeg, width=90),
            label_width=_LABEL_WIDTH,
        )

        button(body, "Применить пути", self._apply_paths).grid(
            row=2, column=0, sticky="w", pady=(theme.GAP["sm"], 0)
        )
        self.add(card)

    def _browse_ytdlp(self) -> None:
        path = filedialog.askopenfilename(title="Укажите путь к yt-dlp")
        if path:
            self.ytdlp_path_entry.delete(0, "end")
            self.ytdlp_path_entry.insert(0, path)

    def _browse_ffmpeg(self) -> None:
        path = filedialog.askopenfilename(title="Укажите путь к ffmpeg")
        if path:
            self.ffmpeg_path_entry.delete(0, "end")
            self.ffmpeg_path_entry.insert(0, path)

    def _apply_paths(self) -> None:
        self.app.set_tool_paths(self.ytdlp_path_entry.get().strip(), self.ffmpeg_path_entry.get().strip())
        self.update_tools_status()

    def update_tools_status(self) -> None:
        binaries = self.app.ytdlp.binaries
        parts = []
        if binaries.ytdlp_available:
            parts.append(f"yt-dlp {binaries.ytdlp_version}   •   {binaries.ytdlp}")
        else:
            parts.append("yt-dlp не найден.")
        if binaries.ffmpeg_available:
            parts.append(f"FFmpeg {binaries.ffmpeg_version}   •   {binaries.ffmpeg}")
        else:
            parts.append("FFmpeg не найден — слияние видео/аудио, встраивание субтитров и обложек будут недоступны.")

        if not binaries.ytdlp_available:
            severity = "error"
        elif not binaries.ffmpeg_available:
            severity = "warning"
        else:
            severity = "ok"
        self.tools_status_label.configure(
            text="\n".join(parts), text_color=theme.color(_SEVERITY_TOKEN[severity])
        )

    # -- обновления ----------------------------------------------------------
    def _build_updates_section(self) -> None:
        card = Card(
            self,
            "Обновления yt-dlp",
            subtitle="YouTube меняется часто — устаревший yt-dlp перестаёт скачивать видео",
        )
        body = card.body

        self.update_status_label = status_label(body, "", "info")
        self.update_status_label.configure(wraplength=620)
        self.update_status_label.grid(row=0, column=0, sticky="ew")

        buttons = ctk.CTkFrame(body, fg_color="transparent")
        buttons.grid(row=1, column=0, sticky="ew", pady=(theme.GAP["md"], 0))
        primary_button(buttons, "Проверить обновления", self._check_updates, width=210).grid(
            row=0, column=0, padx=(0, theme.GAP["sm"])
        )
        button(buttons, "Что нового", self._show_release_history, width=150).grid(row=0, column=1)

        self.auto_update_check = ctk.CTkCheckBox(
            body,
            text="Проверять обновления при запуске",
            command=self._on_auto_update_changed,
        )
        self.auto_update_check.grid(row=2, column=0, sticky="w", pady=(theme.GAP["md"], 0))

        muted_label(
            body,
            "Проверка обращается к GitHub и ничего не устанавливает сама: что скачать, "
            "решаете вы в окне со списком изменений.",
            wraplength=620,
        ).grid(row=3, column=0, sticky="ew", pady=(theme.GAP["sm"], 0))
        self.add(card)

    def _check_updates(self) -> None:
        self.app.check_updates()

    def _show_release_history(self) -> None:
        self.set_update_status("Загружается список релизов…", "info")
        self.app.load_release_history(limit=10, only_new=False)

    def _on_auto_update_changed(self) -> None:
        self.app.update_settings(check_updates_on_start=bool(self.auto_update_check.get()))

    def set_update_status(self, text: str, severity: str = "info") -> None:
        """Строка состояния проверки — её обновляет главное окно по событиям."""
        self.update_status_label.configure(
            text=text, text_color=theme.color(_SEVERITY_TOKEN.get(severity, "fg.secondary"))
        )

    def refresh_update_status(self) -> None:
        """Что показывать, пока проверок в этом сеансе не было."""
        version = self.app.ytdlp.binaries.ytdlp_version or "не определена"
        stamp = getattr(self.app.settings, "last_update_check", "")
        checked = f"   •   последняя проверка: {stamp[:10]}" if stamp[:10] else ""
        self.set_update_status(f"Установленная версия yt-dlp: {version}{checked}", "info")

    # -- внешний вид ---------------------------------------------------------
    def _build_appearance_section(self) -> None:
        card = Card(
            self,
            "Внешний вид",
            subtitle="Тема оформления и масштаб интерфейса применяются сразу",
        )
        body = card.body
        form = form_frame(body, 0)

        self.theme_menu = ctk.CTkOptionMenu(
            form, values=list(_THEMES.values()), command=self._on_theme_changed, height=32, width=240
        )
        form_row(form, 0, "Тема", self.theme_menu, label_width=_LABEL_WIDTH, stretch=False)

        scale_box = ctk.CTkFrame(form, fg_color="transparent")
        scale_box.grid_columnconfigure(0, weight=1)

        # Ползунок, а не поле ввода: масштаб — грубая настройка, шаг 5 %
        # (как ползунок «Interface scale» в ZapretGUI).
        self.scale_slider = ctk.CTkSlider(
            scale_box,
            from_=theme.MIN_SCALE * 100,
            to=theme.MAX_SCALE * 100,
            number_of_steps=len(_SCALE_PRESETS) - 1,
            command=self._on_scale_slide,
        )
        self.scale_slider.grid(row=0, column=0, sticky="ew", padx=(0, theme.GAP["md"]))
        self.scale_slider.bind("<ButtonRelease-1>", self._on_scale_release)

        # Тот же набор значений, что и у ползунка, но выбирается точно и
        # одним кликом; заодно служит подписью текущего масштаба.
        self.scale_menu = ctk.CTkOptionMenu(
            scale_box,
            values=[_scale_label(value) for value in _SCALE_PRESETS],
            command=self._on_scale_preset,
            height=32,
            width=96,
        )
        self.scale_menu.grid(row=0, column=1)

        form_row(
            form,
            1,
            "Масштаб интерфейса",
            scale_box,
            trailing=button(form, "Сбросить", self._reset_scale, width=110),
            label_width=_LABEL_WIDTH,
        )

        muted_label(
            body,
            f"Допустимый диапазон: {int(theme.MIN_SCALE * 100)}–{int(theme.MAX_SCALE * 100)} %. "
            "Те же значения меняются горячими клавишами Ctrl+плюс, Ctrl+минус и Ctrl+0.",
            wraplength=620,
        ).grid(row=1, column=0, sticky="ew", pady=(theme.GAP["sm"], 0))
        self.add(card)

    def _on_theme_changed(self, value: str) -> None:
        self.app.update_settings(theme=_THEME_BY_LABEL.get(value, "System"))
        self.on_settings_changed()

    def _on_scale_slide(self, value: float) -> None:
        """Живое применение при перетаскивании — без записи на диск."""
        scale = theme.normalize_scale(round(value) / 100)
        self.scale_menu.set(_scale_label(theme.scale_percent(scale)))
        if self._loading:
            return
        self.app.settings.ui_scale = scale
        self.on_settings_changed()

    def _on_scale_release(self, _event=None) -> None:
        """Сохранение — один раз, когда ползунок отпущен."""
        scale = theme.normalize_scale(round(self.scale_slider.get()) / 100)
        self.app.update_settings(ui_scale=scale)
        self.on_settings_changed()

    def _on_scale_preset(self, label: str) -> None:
        """Выбор готового значения из списка — применяем и сохраняем сразу."""
        self.app.update_settings(ui_scale=theme.normalize_scale(_scale_percent(label) / 100))
        self.on_settings_changed()

    def _reset_scale(self) -> None:
        self._on_scale_preset(_scale_label(100))

    def sync_ui_scale(self, scale: float) -> None:
        """Подтягивает ползунок и список, если масштаб сменили горячей клавишей."""
        percent = theme.scale_percent(scale)
        if int(round(self.scale_slider.get())) != percent:
            self.scale_slider.set(percent)
        if _scale_percent(self.scale_menu.get()) != percent:
            self.scale_menu.set(_scale_label(percent))

    # -- сеть ----------------------------------------------------------------
    def _build_network_section(self) -> None:
        card = Card(self, "Сеть", subtitle="Прокси, cookies и ограничение скорости")
        form = form_frame(card.body, 0)

        self.proxy_entry = ctk.CTkEntry(form, height=32, placeholder_text="socks5://127.0.0.1:1080")
        form_row(form, 0, "Прокси", self.proxy_entry, label_width=_LABEL_WIDTH)
        self.proxy_entry.bind("<FocusOut>", lambda _e: self._on_network_changed())

        self.browser_menu = ctk.CTkOptionMenu(
            form, values=list(_BROWSERS), command=self._on_browser_changed, height=32, width=240
        )
        form_row(
            form, 1, "Cookies из браузера", self.browser_menu, label_width=_LABEL_WIDTH, stretch=False
        )

        self.cookies_entry = ctk.CTkEntry(
            form, height=32, placeholder_text="cookies.txt (для приватных/возрастных видео)"
        )
        self.cookies_browse_button = button(form, "Обзор", self._browse_cookies, width=90)
        self.cookies_label = form_row(
            form,
            2,
            "…либо файл cookies",
            self.cookies_entry,
            trailing=self.cookies_browse_button,
            label_width=_LABEL_WIDTH,
        )
        self.cookies_entry.bind("<FocusOut>", lambda _e: self._on_network_changed())

        self.limit_rate_entry = ctk.CTkEntry(form, height=32, placeholder_text="например, 2M")
        form_row(form, 3, "Ограничение скорости", self.limit_rate_entry, label_width=_LABEL_WIDTH)
        self.limit_rate_entry.bind("<FocusOut>", lambda _e: self._on_network_changed())

        self.cookies_hint = muted_label(card.body, "", wraplength=620)
        self.cookies_hint.grid(row=1, column=0, sticky="ew", pady=(theme.GAP["sm"], 0))
        self.add(card)

    def _browse_cookies(self) -> None:
        path = filedialog.askopenfilename(title="Файл cookies (Netscape format)")
        if path:
            self.cookies_entry.delete(0, "end")
            self.cookies_entry.insert(0, path)
            self._on_network_changed()

    def _on_browser_changed(self, _label: str | None = None) -> None:
        self._on_network_changed()
        self._sync_cookies_controls()

    def _selected_browser(self) -> str:
        return _BROWSERS.get(self.browser_menu.get(), "")

    def _sync_cookies_controls(self) -> None:
        """Файл и браузер — альтернативы; активна ровно одна из них."""
        browser = self._selected_browser()
        state = "disabled" if browser else "normal"
        # CTkEntry не приглушает свой текст сам — гасим его вместе с подписью,
        # иначе выключенное поле выглядит активным.
        muted = theme.color("fg.disabled" if browser else "fg.primary")
        self.cookies_entry.configure(state=state, text_color=muted)
        self.cookies_browse_button.configure(state=state)
        self.cookies_label.configure(text_color=muted)
        if browser:
            self.cookies_hint.configure(
                text=(
                    f"Cookies читаются из браузера {self.browser_menu.get()} при каждом запуске "
                    "yt-dlp — авторизация в браузере подхватывается сама. Браузер при этом лучше "
                    "закрыть: он держит базу cookies заблокированной. Указанный файл не используется."
                )
            )
        else:
            self.cookies_hint.configure(
                text=(
                    "Cookies нужны для приватных, возрастных и требующих входа видео. "
                    "Можно взять их прямо из браузера или указать файл в формате Netscape."
                )
            )

    def _on_network_changed(self) -> None:
        self.app.update_settings(
            proxy=self.proxy_entry.get().strip(),
            cookies_file=self.cookies_entry.get().strip(),
            cookies_from_browser=self._selected_browser(),
            limit_rate=self.limit_rate_entry.get().strip(),
        )

    # -- общие настройки -------------------------------------------------------
    def _build_general_section(self) -> None:
        card = Card(self, "Общие")
        body = card.body
        form = form_frame(body, 0)

        self.parallel_menu = ctk.CTkOptionMenu(
            form, values=["1", "2", "3", "4"], command=self._on_parallel_changed, height=32, width=240
        )
        form_row(form, 0, "Параллельных загрузок", self.parallel_menu, label_width=_LABEL_WIDTH, stretch=False)

        self.overwrite_menu = ctk.CTkOptionMenu(
            form, values=list(_OVERWRITE_LABELS.values()), command=self._on_overwrite_changed, height=32, width=240
        )
        form_row(form, 1, "При существующем файле", self.overwrite_menu, label_width=_LABEL_WIDTH, stretch=False)

        self.output_dir_entry = ctk.CTkEntry(form, height=32)
        form_row(
            form,
            2,
            "Папка загрузки по умолчанию",
            self.output_dir_entry,
            trailing=button(form, "Обзор", self._browse_output_dir, width=90),
            label_width=_LABEL_WIDTH,
        )
        self.output_dir_entry.bind("<FocusOut>", lambda _e: self._on_output_dir_changed())

        self.template_entry = ctk.CTkEntry(form, height=32)
        form_row(form, 3, "Шаблон имени файла", self.template_entry, label_width=_LABEL_WIDTH)
        self.template_entry.bind("<FocusOut>", lambda _e: self._on_template_changed())

        checks = ctk.CTkFrame(body, fg_color="transparent")
        checks.grid(row=1, column=0, sticky="ew", pady=(theme.GAP["sm"], 0))

        self.playlist_check = ctk.CTkCheckBox(
            checks,
            text="По умолчанию скачивать весь плейлист (если ссылка — плейлист)",
            command=self._on_playlist_changed,
        )
        self.playlist_check.grid(row=0, column=0, sticky="w", pady=2)

        self.restrict_check = ctk.CTkCheckBox(
            checks,
            text="Безопасные имена файлов (только ASCII, без пробелов)",
            command=self._on_restrict_changed,
        )
        self.restrict_check.grid(row=1, column=0, sticky="w", pady=2)

        self.tooltips_check = ctk.CTkCheckBox(
            checks,
            text="Показывать подсказки при наведении на параметры",
            command=self._on_tooltips_changed,
        )
        self.tooltips_check.grid(row=2, column=0, sticky="w", pady=2)
        self.add(card)

    def _on_parallel_changed(self, value: str) -> None:
        self.app.update_settings(parallel_jobs=int(value))

    def _on_overwrite_changed(self, value: str) -> None:
        self.app.update_settings(overwrite_policy=_OVERWRITE_BY_LABEL.get(value, "skip"))

    def _on_output_dir_changed(self) -> None:
        self.app.update_settings(output_directory=self.output_dir_entry.get().strip())

    def _browse_output_dir(self) -> None:
        path = filedialog.askdirectory(title="Папка загрузки по умолчанию")
        if path:
            self.output_dir_entry.delete(0, "end")
            self.output_dir_entry.insert(0, path)
            self._on_output_dir_changed()

    def _on_template_changed(self) -> None:
        self.app.update_settings(output_template=self.template_entry.get().strip() or "%(title).200B [%(id)s].%(ext)s")

    def _on_playlist_changed(self) -> None:
        self.app.update_settings(download_playlists=bool(self.playlist_check.get()))

    def _on_restrict_changed(self) -> None:
        self.app.update_settings(restrict_filenames=bool(self.restrict_check.get()))

    def _on_tooltips_changed(self) -> None:
        self.app.update_settings(show_tooltips=bool(self.tooltips_check.get()))

    # -- значения по умолчанию для новых заданий --------------------------------
    def _build_defaults_section(self) -> None:
        card = Card(self, "Значения по умолчанию", subtitle="Применяются к новым заданиям")
        body = card.body
        form = form_frame(body, 0)

        self.container_menu = ctk.CTkOptionMenu(
            form, values=_CONTAINERS, command=self._on_defaults_changed, height=32, width=240
        )
        form_row(form, 0, "Контейнер для видео", self.container_menu, label_width=_LABEL_WIDTH, stretch=False)

        self.audio_format_menu = ctk.CTkOptionMenu(
            form, values=_AUDIO_FORMATS, command=self._on_defaults_changed, height=32, width=240
        )
        form_row(form, 1, "Формат аудио", self.audio_format_menu, label_width=_LABEL_WIDTH, stretch=False)

        self.audio_quality_menu = ctk.CTkOptionMenu(
            form,
            values=["320", "256", "192", "128", "96", "64", "0"],
            command=self._on_defaults_changed,
            height=32,
            width=240,
        )
        form_row(form, 2, "Битрейт аудио, kbps", self.audio_quality_menu, label_width=_LABEL_WIDTH, stretch=False)

        checks = ctk.CTkFrame(body, fg_color="transparent")
        checks.grid(row=1, column=0, sticky="ew", pady=(theme.GAP["sm"], 0))

        self.metadata_check = ctk.CTkCheckBox(
            checks, text="Встраивать метаданные (название, автор)", command=self._on_defaults_changed
        )
        self.metadata_check.grid(row=0, column=0, sticky="w", pady=2)

        self.chapters_check = ctk.CTkCheckBox(
            checks, text="Встраивать главы", command=self._on_defaults_changed
        )
        self.chapters_check.grid(row=1, column=0, sticky="w", pady=2)

        self.thumbnail_check = ctk.CTkCheckBox(
            checks, text="Встраивать обложку по умолчанию", command=self._on_defaults_changed
        )
        self.thumbnail_check.grid(row=2, column=0, sticky="w", pady=2)

        self.auto_subs_check = ctk.CTkCheckBox(
            checks, text="По умолчанию включать автоматические субтитры", command=self._on_defaults_changed
        )
        self.auto_subs_check.grid(row=3, column=0, sticky="w", pady=2)

        langs_form = form_frame(body, 2, pady=(theme.GAP["sm"], 0))
        self.subtitle_langs_entry = ctk.CTkEntry(langs_form, height=32)
        form_row(
            langs_form,
            0,
            "Языки субтитров по умолчанию (через запятую)",
            self.subtitle_langs_entry,
            label_width=_LABEL_WIDTH,
        )
        self.subtitle_langs_entry.bind("<FocusOut>", lambda _e: self._on_defaults_changed())
        self.add(card)

    def _on_defaults_changed(self, _value: str | None = None) -> None:
        langs = [part.strip() for part in self.subtitle_langs_entry.get().split(",") if part.strip()]
        self.app.update_settings(
            default_container=self.container_menu.get(),
            default_audio_format=self.audio_format_menu.get(),
            default_audio_quality=self.audio_quality_menu.get(),
            embed_metadata_default=bool(self.metadata_check.get()),
            embed_chapters_default=bool(self.chapters_check.get()),
            embed_thumbnail_default=bool(self.thumbnail_check.get()),
            include_auto_subs_default=bool(self.auto_subs_check.get()),
            subtitle_langs_default=langs,
        )

    # -- диагностика -------------------------------------------------------------
    def _build_diagnostics_section(self) -> None:
        card = Card(self, "Диагностика", subtitle="Версии инструментов, свободное место, последние ошибки")
        button(card.body, "Показать отчёт", self._show_diagnostics).grid(row=0, column=0, sticky="w")
        self.add(card)

    def _show_diagnostics(self) -> None:
        text_dialog(
            self,
            "Диагностика",
            self.app.diagnostics().to_text(),
            mono=True,
            size=(700, 440),
            card_title="Отчёт",
        )

    # -- инициализация из настроек --------------------------------------------
    def _load_from_settings(self) -> None:
        settings = self.app.settings
        self.theme_menu.set(_THEMES.get(settings.theme, "Системная"))
        self.sync_ui_scale(getattr(settings, "ui_scale", 1.0))
        self.parallel_menu.set(str(settings.parallel_jobs))
        self.overwrite_menu.set(_OVERWRITE_LABELS.get(settings.overwrite_policy, "Пропускать существующие"))
        self.output_dir_entry.insert(0, settings.output_directory)
        self.template_entry.insert(0, settings.output_template)
        if settings.download_playlists:
            self.playlist_check.select()
        if settings.restrict_filenames:
            self.restrict_check.select()
        if settings.show_tooltips:
            self.tooltips_check.select()
        if getattr(settings, "check_updates_on_start", False):
            self.auto_update_check.select()
        self.refresh_update_status()

        self.proxy_entry.insert(0, settings.proxy)
        self.cookies_entry.insert(0, settings.cookies_file)
        self.browser_menu.set(
            _BROWSER_BY_VALUE.get(getattr(settings, "cookies_from_browser", ""), _NO_BROWSER)
        )
        self._sync_cookies_controls()
        self.limit_rate_entry.insert(0, settings.limit_rate)

        self.container_menu.set(settings.default_container)
        self.audio_format_menu.set(settings.default_audio_format)
        self.audio_quality_menu.set(settings.default_audio_quality)
        if settings.embed_metadata_default:
            self.metadata_check.select()
        if settings.embed_chapters_default:
            self.chapters_check.select()
        if settings.embed_thumbnail_default:
            self.thumbnail_check.select()
        if settings.include_auto_subs_default:
            self.auto_subs_check.select()
        self.subtitle_langs_entry.insert(0, ", ".join(settings.subtitle_langs_default))

        if self.app.ytdlp.binaries.ytdlp:
            self.ytdlp_path_entry.insert(0, str(self.app.ytdlp.binaries.ytdlp))
        if self.app.ytdlp.binaries.ffmpeg:
            self.ffmpeg_path_entry.insert(0, str(self.app.ytdlp.binaries.ffmpeg))
        self.update_tools_status()


#: Уровень важности -> токен цвета для строки состояния инструментов.
_SEVERITY_TOKEN = {
    "ok": "state.ok",
    "warning": "state.warn",
    "error": "state.error",
    "info": "fg.secondary",
    "busy": "state.info",
}

#: Предустановки масштаба интерфейса — весь допустимый диапазон с шагом 5 %.
_SCALE_PRESETS = list(range(int(theme.MIN_SCALE * 100), int(theme.MAX_SCALE * 100) + 1, 5))


def _scale_label(percent: int) -> str:
    return f"{percent} %"


def _scale_percent(label: str) -> int:
    """Обратное преобразование подписи в проценты; мусор считаем за 100 %."""
    try:
        return int(label.replace("%", "").strip())
    except ValueError:
        return 100
