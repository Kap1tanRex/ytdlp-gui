"""Дизайн-токены и оформление интерфейса.

Повторяет систему оформления ZapretGUI: палитра описывается набором
токенов (``bg.*``, ``fg.*``, ``accent*``, ``state.*``, ``border*``), а
экраны берут цвета только из них — ни один виджет не задаёт цвет
«руками». В ZapretGUI из токенов собирается QSS для Qt; здесь из тех же
значений собирается тема CustomTkinter (словарь
``customtkinter.ThemeManager.theme``).

Каждый цвет — пара ``(светлая тема, тёмная тема)``: CustomTkinter сам
выбирает нужный элемент пары по режиму оформления, поэтому переключение
«Системная / Светлая / Тёмная» работает без пересоздания виджетов.

Масштаб интерфейса (в ZapretGUI — ``font_scale``, §13.1) реализован
средствами CustomTkinter: ``set_widget_scaling`` пересчитывает размеры
шрифтов, отступов и самих виджетов у всех уже созданных окон, поэтому
ползунок в настройках действует сразу, без перезапуска.
"""

from __future__ import annotations

import logging
import tkinter.font

import customtkinter as ctk

log = logging.getLogger(__name__)

#: Границы масштаба интерфейса — как в ZapretGUI (80…160 %).
MIN_SCALE = 0.8
MAX_SCALE = 1.6

Palette = dict[str, str]

#: Токены светлой темы (значения — из ZapretGUI ``themes/light.json``).
LIGHT: Palette = {
    "bg.window": "#F5F6F8",
    "bg.surface": "#FFFFFF",
    "bg.elevated": "#FFFFFF",
    "bg.hover": "#EDEFF3",
    "bg.selected": "#E3EBFB",
    "fg.primary": "#1B1D21",
    "fg.secondary": "#5F6368",
    "fg.disabled": "#A0A4AB",
    "fg.inverted": "#FFFFFF",
    "accent": "#2F6FE4",
    "accent.hover": "#3F7DF0",
    "accent.pressed": "#2559BC",
    "accent.fg": "#FFFFFF",
    "state.ok": "#1A7F37",
    "state.warn": "#9A6700",
    "state.error": "#CF222E",
    "state.info": "#0969DA",
    "border": "#D8DCE3",
    "border.strong": "#BFC5CF",
    # Заливка выпадающих списков: CustomTkinter не умеет рисовать им рамку,
    # поэтому в светлой теме поле должно отличаться от поверхности карточки.
    "bg.field": "#ECEFF4",
    "bg.field.button": "#DEE3EB",
}

#: Токены тёмной темы (значения — из ZapretGUI ``themes/dark.json``).
DARK: Palette = {
    "bg.window": "#14161A",
    "bg.surface": "#1C1F25",
    "bg.elevated": "#242830",
    "bg.hover": "#2A2F38",
    "bg.selected": "#2F3742",
    "fg.primary": "#E8EAED",
    "fg.secondary": "#9AA0A6",
    "fg.disabled": "#5F6368",
    "fg.inverted": "#14161A",
    "accent": "#4C8DFF",
    "accent.hover": "#679DFF",
    "accent.pressed": "#3A78E0",
    "accent.fg": "#FFFFFF",
    "state.ok": "#3FB950",
    "state.warn": "#D29922",
    "state.error": "#F85149",
    "state.info": "#58A6FF",
    "border": "#2C313A",
    "border.strong": "#3A414D",
    "bg.field": "#242830",
    "bg.field.button": "#2F3742",
}

#: Радиусы скруглений (токены ``radius.sm|md|lg`` ZapretGUI).
RADIUS = {"sm": 7, "md": 10, "lg": 14}

#: Базовые размеры шрифта. Масштаб интерфейса применяется поверх них
#: средствами CustomTkinter, поэтому здесь значения всегда «стопроцентные».
FONT_SIZE = {
    "small": 12,
    "base": 13,
    "large": 15,
    "title": 17,
    "hero": 26,
}

#: Отступы, из которых собраны все экраны (аналог полей Card/Page в ZapretGUI).
GAP = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 20}

#: Ширина боковой панели навигации.
SIDEBAR_WIDTH = 236

_FAMILY_CANDIDATES = ("Segoe UI Variable Text", "Segoe UI", "Inter", "Noto Sans", "DejaVu Sans")
_MONO_CANDIDATES = ("Cascadia Mono", "Consolas", "DejaVu Sans Mono", "Menlo", "Courier New")

_family = "Segoe UI"
_mono_family = "Consolas"


# -- доступ к токенам ---------------------------------------------------------
def color(token: str, fallback: str = "#808080") -> tuple[str, str]:
    """Пара цветов ``(светлая, тёмная)`` для токена — в формате CustomTkinter."""
    return (LIGHT.get(token, fallback), DARK.get(token, fallback))


def mix(token: str, background: str, ratio: float = 0.2) -> tuple[str, str]:
    """Цвет ``token``, разбавленный фоном ``background``.

    CustomTkinter не умеет полупрозрачные заливки, поэтому «акцент с
    прозрачностью 20 %» приходится считать заранее — например, для круглой
    подложки под значком.
    """
    return tuple(  # type: ignore[return-value]
        _blend(palette.get(token, "#808080"), palette.get(background, "#808080"), ratio)
        for palette in (LIGHT, DARK)
    )


def _blend(foreground: str, background: str, ratio: float) -> str:
    ratio = max(0.0, min(1.0, ratio))
    front = _rgb(foreground)
    back = _rgb(background)
    return "#" + "".join(
        f"{round(f * ratio + b * (1 - ratio)):02X}" for f, b in zip(front, back, strict=False)
    )


def _rgb(color: str) -> tuple[int, int, int]:
    value = color.lstrip("#")
    if len(value) == 3:
        value = "".join(char * 2 for char in value)
    try:
        return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))
    except ValueError:
        return (128, 128, 128)


def font(size: str = "base", *, weight: str = "normal", mono: bool = False) -> ctk.CTkFont:
    """Шрифт по имени размера из :data:`FONT_SIZE`."""
    return ctk.CTkFont(
        family=_mono_family if mono else _family,
        size=FONT_SIZE.get(size, FONT_SIZE["base"]),
        weight=weight,
    )


# -- сборка темы CustomTkinter ------------------------------------------------
def build_theme() -> dict:
    """Тема CustomTkinter, собранная из токенов.

    Значения по умолчанию описывают «вторичный» вид элементов (как
    ``QPushButton`` без objectName в ZapretGUI); акцентный, опасный и
    ссылочный варианты задаются фабриками в
    :mod:`ytdlp_gui.gui.widgets.design`.
    """
    return {
        "CTk": {"fg_color": color("bg.window")},
        "CTkToplevel": {"fg_color": color("bg.window")},
        "CTkFrame": {
            "corner_radius": RADIUS["md"],
            "border_width": 0,
            "fg_color": color("bg.surface"),
            "top_fg_color": color("bg.elevated"),
            "border_color": color("border"),
        },
        "CTkButton": {
            "corner_radius": RADIUS["sm"],
            "border_width": 1,
            "fg_color": color("bg.elevated"),
            "hover_color": color("bg.hover"),
            "border_color": color("border.strong"),
            "text_color": color("fg.primary"),
            "text_color_disabled": color("fg.disabled"),
        },
        "CTkLabel": {
            "corner_radius": 0,
            "border_width": 0,
            "fg_color": "transparent",
            "border_color": color("border"),
            "text_color": color("fg.primary"),
        },
        "CTkEntry": {
            "corner_radius": RADIUS["sm"],
            "border_width": 1,
            "fg_color": color("bg.elevated"),
            "border_color": color("border.strong"),
            "text_color": color("fg.primary"),
            "placeholder_text_color": color("fg.disabled"),
        },
        "CTkCheckBox": {
            "corner_radius": 4,
            "border_width": 2,
            "fg_color": color("accent"),
            "border_color": color("border.strong"),
            "hover_color": color("accent.hover"),
            "checkmark_color": color("accent.fg"),
            "text_color": color("fg.primary"),
            "text_color_disabled": color("fg.disabled"),
        },
        "CTkSwitch": {
            "corner_radius": 1000,
            "border_width": 3,
            "button_length": 0,
            "fg_color": color("border.strong"),
            "progress_color": color("accent"),
            "button_color": color("bg.surface"),
            "button_hover_color": color("bg.hover"),
            "text_color": color("fg.primary"),
            "text_color_disabled": color("fg.disabled"),
        },
        "CTkRadioButton": {
            "corner_radius": 1000,
            "border_width_checked": 5,
            "border_width_unchecked": 2,
            "fg_color": color("accent"),
            "border_color": color("border.strong"),
            "hover_color": color("accent.hover"),
            "text_color": color("fg.primary"),
            "text_color_disabled": color("fg.disabled"),
        },
        "CTkProgressBar": {
            "corner_radius": 1000,
            "border_width": 0,
            "fg_color": color("bg.hover"),
            "progress_color": color("accent"),
            "border_color": color("border"),
        },
        "CTkSlider": {
            "corner_radius": 1000,
            "button_corner_radius": 1000,
            "border_width": 6,
            "button_length": 0,
            "fg_color": color("border.strong"),
            "progress_color": color("accent"),
            "button_color": color("accent"),
            "button_hover_color": color("accent.hover"),
        },
        "CTkOptionMenu": {
            "corner_radius": RADIUS["sm"],
            "fg_color": color("bg.field"),
            "button_color": color("bg.field.button"),
            "button_hover_color": color("accent"),
            "text_color": color("fg.primary"),
            "text_color_disabled": color("fg.disabled"),
        },
        "CTkComboBox": {
            "corner_radius": RADIUS["sm"],
            "border_width": 1,
            "fg_color": color("bg.field"),
            "border_color": color("border.strong"),
            "button_color": color("bg.field.button"),
            "button_hover_color": color("accent"),
            "text_color": color("fg.primary"),
            "text_color_disabled": color("fg.disabled"),
        },
        "CTkScrollbar": {
            "corner_radius": 1000,
            "border_spacing": 4,
            "fg_color": "transparent",
            "button_color": color("border.strong"),
            "button_hover_color": color("fg.disabled"),
        },
        "CTkSegmentedButton": {
            "corner_radius": RADIUS["sm"],
            "border_width": 2,
            "fg_color": color("bg.elevated"),
            "selected_color": color("accent"),
            "selected_hover_color": color("accent.hover"),
            "unselected_color": color("bg.elevated"),
            "unselected_hover_color": color("bg.hover"),
            "text_color": color("fg.primary"),
            "text_color_disabled": color("fg.disabled"),
        },
        "CTkTextbox": {
            "corner_radius": RADIUS["sm"],
            "border_width": 1,
            "fg_color": color("bg.elevated"),
            "border_color": color("border.strong"),
            "text_color": color("fg.primary"),
            "scrollbar_button_color": color("border.strong"),
            "scrollbar_button_hover_color": color("fg.disabled"),
        },
        "CTkScrollableFrame": {"label_fg_color": color("bg.elevated")},
        "DropdownMenu": {
            "fg_color": color("bg.elevated"),
            "hover_color": color("bg.selected"),
            "text_color": color("fg.primary"),
        },
        "CTkFont": {"family": _family, "size": FONT_SIZE["base"], "weight": "normal"},
    }


def install() -> None:
    """Делает тему активной. Вызывается до создания виджетов."""
    ctk.ThemeManager.theme = build_theme()
    ctk.ThemeManager._currently_loaded_theme = "ytdlp-gui"


def resolve_fonts(root) -> None:
    """Подбирает первое доступное семейство шрифтов из списка кандидатов.

    Список семейств доступен только при уже созданном корневом окне Tk,
    поэтому вызывается сразу после создания окна и до построения экранов.
    """
    global _family, _mono_family
    try:
        available = {name.lower() for name in tkinter.font.families(root)}
    except Exception:  # noqa: BLE001 - без списка семейств остаёмся на значениях по умолчанию
        log.debug("Список семейств шрифтов недоступен")
        return
    for candidate in _FAMILY_CANDIDATES:
        if candidate.lower() in available:
            _family = candidate
            break
    for candidate in _MONO_CANDIDATES:
        if candidate.lower() in available:
            _mono_family = candidate
            break
    try:
        ctk.ThemeManager.theme["CTkFont"]["family"] = _family
    except (KeyError, TypeError):  # pragma: no cover - тема всегда установлена install()
        pass


# -- режим оформления и масштаб ----------------------------------------------
def normalize_scale(value: float | int | str) -> float:
    """Приводит масштаб к допустимому диапазону; мусор заменяет на 1.0."""
    try:
        scale = float(value)
    except (TypeError, ValueError):
        return 1.0
    return max(MIN_SCALE, min(MAX_SCALE, round(scale, 2)))


def scale_percent(scale: float) -> int:
    """Масштаб в процентах.

    Именно ``round``, а не ``int``: 1.15 в двоичной плавающей точке чуть
    меньше самого себя, и отбрасывание дробной части дало бы 114 %.
    """
    return int(round(normalize_scale(scale) * 100))


def apply_appearance(mode: str) -> None:
    """``System`` | ``Light`` | ``Dark`` — значения из настроек приложения."""
    ctk.set_appearance_mode(mode if mode in ("System", "Light", "Dark") else "System")


def apply_scale(scale: float) -> float:
    """Применяет масштаб интерфейса ко всем окнам приложения.

    Возвращает фактически применённое значение (после ограничения
    диапазоном), чтобы вызывающий код мог сохранить именно его.
    """
    value = normalize_scale(scale)
    ctk.set_widget_scaling(value)
    ctk.set_window_scaling(value)
    return value
