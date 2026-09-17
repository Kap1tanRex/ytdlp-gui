"""Визуальная система интерфейса — по образцу «Стемницы».

Тёплая тёмная «приборная панель»: почти чёрный коричневый фон,
волосяные линии, моноширинные капс-подписи с разрядкой и один янтарный
акцент. Токены названы так же, как в ``docs/design-system.md``
«Стемницы» (палитра — §3, шрифты — §4, метрики — §5), и экраны берут
цвета и шрифты только отсюда.

Тема одна — тёмная: светлой у «Стемницы» нет, а контраст цветов (§3.7)
посчитан под тёмный фон. Масштаб интерфейса делает CustomTkinter:
``set_widget_scaling`` пересчитывает размеры и шрифты уже созданных
виджетов, поэтому масштаб меняется без перезапуска.

Правила янтаря (§3.8): основная кнопка (одна на экран), активная
вкладка, выбранный сегмент, наведение и фокус, включённые флажки,
тумблеры и светодиоды. Больше нигде.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
import sys
import tkinter.font
from pathlib import Path

import customtkinter as ctk

log = logging.getLogger(__name__)

# -- цвет (§3.1–3.2) ----------------------------------------------------------
PIT = "#100D0B"  # «дно»: миниатюры, таблица форматов
BG = "#141110"  # фон окна и страниц
BG2 = "#1B1815"  # панели, карточки, строки списков, диалоги
BG3 = "#221E1A"  # наведение, выбранный сегмент, текущая строка, желоба
LINE = "#2A2521"  # волосяные линии и рамки панелей
LINE2 = "#3B342D"  # рамки элементов управления
TXT = "#E8E1D3"  # основной текст
DIM = "#96897A"  # вторичный текст, заливка прогресса
FAINT = "#655C50"  # подписи разделов, подсказки — только необязательное
AMBER = "#E8A33D"  # акцент
AMBER2 = "#F2B95A"  # основная кнопка при наведении
AMBER_DEEP = "#C98A2C"  # основная кнопка при нажатии
ON_AMBER = "#191410"  # текст на янтаре
TOAST_BG = "#221D18"  # уведомления, подсказки
OK = "#7FAE6F"
WARN = "#D9B13D"
ERR = "#C9604A"
ERR_BG = "#2A1A17"

#: Состояние -> цвет подписи. Ошибка всегда дублируется значком или
#: кромкой и текстом — один цвет ничего не сообщает (§3.2).
STATE_COLORS = {"ok": OK, "warn": WARN, "error": ERR, "info": DIM, "idle": FAINT}

# -- метрики (§5) ------------------------------------------------------------
MAX_WIDTH = 1440  # максимальная ширина содержимого
PAGE_PAD = 28  # боковое поле страницы
HEADER_HEIGHT = 58
SETTINGS_WIDTH = 900  # колонка настроек

#: Границы масштаба интерфейса.
MIN_SCALE = 0.8
MAX_SCALE = 1.6

# -- шрифты (§4.1) -------------------------------------------------------------
FONTS_DIR = Path(__file__).resolve().parent.parent / "resources" / "fonts"

#: Роль -> (семейство, файл). Начертания IBM Plex и Unbounded в Windows —
#: отдельные семейства («IBM Plex Sans Medium»), а не веса одного.
_FACES = {
    "sans": ("IBM Plex Sans", "IBMPlexSans-Regular.ttf"),
    "sans_medium": ("IBM Plex Sans Medium", "IBMPlexSans-Medium.ttf"),
    "sans_semi": ("IBM Plex Sans SemiBold", "IBMPlexSans-SemiBold.ttf"),
    "mono": ("IBM Plex Mono", "IBMPlexMono-Regular.ttf"),
    "mono_medium": ("IBM Plex Mono Medium", "IBMPlexMono-Medium.ttf"),
    "display": ("Unbounded Medium", "Unbounded-Medium.ttf"),
    "display_semi": ("Unbounded SemiBold", "Unbounded-SemiBold.ttf"),
}

#: Замена, если встроенный шрифт не загрузился: (семейство, вес).
_FALLBACKS = {
    "sans": ("Segoe UI", "normal"),
    "sans_medium": ("Segoe UI Semibold", "normal"),
    "sans_semi": ("Segoe UI", "bold"),
    "mono": ("Consolas", "normal"),
    "mono_medium": ("Consolas", "bold"),
    "display": ("Segoe UI Semibold", "normal"),
    "display_semi": ("Segoe UI", "bold"),
}

_resolved: dict[str, tuple[str, str]] = dict(_FALLBACKS)
_font_cache: dict[tuple[str, int], ctk.CTkFont] = {}


def install_fonts(root) -> None:
    """Подключает встроенные шрифты. Нужен уже созданный корень Tk.

    Файлы регистрируются только для этого процесса (в системе ничего не
    устанавливается). Если какое-то начертание не подхватилось, роль
    получает системную замену, а не падает.
    """
    for role, (family, filename) in _FACES.items():
        path = FONTS_DIR / filename
        loaded = False
        if path.is_file():
            try:
                loaded = bool(ctk.FontManager.load_font(str(path)))
            except Exception:  # noqa: BLE001 - без шрифта интерфейс всё равно должен открыться
                log.debug("Шрифт %s не загружен", path, exc_info=True)
        if loaded and _family_available(root, family):
            _resolved[role] = (family, "normal")
        else:
            log.info("Шрифт «%s» недоступен, используется замена", family)
            _resolved[role] = _FALLBACKS[role]
    _font_cache.clear()
    ctk.ThemeManager.theme["CTkFont"]["family"] = _resolved["sans"][0]


def _family_available(root, family: str) -> bool:
    # Шрифты загружены как «неперечисляемые» и в families() не видны,
    # поэтому проверяем, во что Tk на самом деле превратил запрос.
    try:
        actual = tkinter.font.Font(root, family=family, size=-12).actual("family")
    except Exception:  # noqa: BLE001
        return False
    return str(actual).lower() == family.lower()


def family(role: str) -> str:
    """Семейство, которым на деле рисуется роль (встроенное или замена)."""
    return _resolved.get(role, _FALLBACKS["sans"])[0]


def font(role: str, size: int) -> ctk.CTkFont:
    """Шрифт роли ``role`` (см. :data:`_FACES`) кеглем ``size`` пикселей."""
    key = (role, int(size))
    cached = _font_cache.get(key)
    if cached is None:
        family, weight = _resolved.get(role, _FALLBACKS["sans"])
        cached = ctk.CTkFont(family=family, size=int(size), weight=weight)
        _font_cache[key] = cached
    return cached


def sans(size: int = 13) -> ctk.CTkFont:
    return font("sans", size)


def sans_medium(size: int = 14) -> ctk.CTkFont:
    return font("sans_medium", size)


def mono(size: int = 12) -> ctk.CTkFont:
    return font("mono", size)


def mono_medium(size: int = 12) -> ctk.CTkFont:
    return font("mono_medium", size)


def display(size: int = 30) -> ctk.CTkFont:
    return font("display", size)


def display_semi(size: int = 16) -> ctk.CTkFont:
    return font("display_semi", size)


# -- набор (§4.3) ------------------------------------------------------------
HAIR_SPACE = "\u200a"
THIN_SPACE = "\u2009"


def caps(text: str, tracking: float = 0.12) -> str:
    """Служебная подпись: капс с разрядкой.

    Tk не умеет межбуквенный интервал, поэтому разрядка набирается
    пробелами: волосяной (≈1 px при 11–12 px) для 0.08–0.13 em и тонкий
    (≈2 px) для 0.14 em и больше. Ниже 0.08 em разрядки нет.
    """
    text = text.upper()
    if tracking < 0.08 or not text:
        return text
    return (THIN_SPACE if tracking >= 0.14 else HAIR_SPACE).join(text)


def mix(a: str, b: str, t: float) -> str:
    """Смесь цветов: ``t = 0`` — ``a``, ``t = 1`` — ``b``.

    CustomTkinter не умеет полупрозрачные заливки, поэтому «цвет с
    альфой 0.45 на фоне» считается заранее этой функцией.
    """
    t = max(0.0, min(1.0, t))
    ra, ga, ba = _rgb(a)
    rb, gb, bb = _rgb(b)
    return "#{:02X}{:02X}{:02X}".format(
        round(ra + (rb - ra) * t), round(ga + (gb - ga) * t), round(ba + (bb - ba) * t)
    )


def _rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    if len(value) == 3:
        value = "".join(char * 2 for char in value)
    try:
        return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    except ValueError:
        return 128, 128, 128


# -- тема CustomTkinter ------------------------------------------------------
def build_theme() -> dict:
    """Значения по умолчанию для виджетов CustomTkinter.

    Здесь только нейтральная основа; конкретный вид кнопок, сегментов,
    полей и прочего задают компоненты :mod:`ytdlp_gui.gui.widgets.design`.
    """
    return {
        "CTk": {"fg_color": BG},
        "CTkToplevel": {"fg_color": BG2},
        "CTkFrame": {
            "corner_radius": 0,
            "border_width": 0,
            "fg_color": BG,
            "top_fg_color": BG2,
            "border_color": LINE,
        },
        "CTkButton": {
            "corner_radius": 3,
            "border_width": 1,
            "fg_color": "transparent",
            "hover_color": BG3,
            "border_color": LINE2,
            "text_color": TXT,
            "text_color_disabled": FAINT,
        },
        "CTkLabel": {
            "corner_radius": 0,
            "border_width": 0,
            "fg_color": "transparent",
            "border_color": LINE,
            "text_color": TXT,
        },
        "CTkEntry": {
            "corner_radius": 3,
            "border_width": 1,
            "fg_color": BG,
            "border_color": LINE2,
            "text_color": TXT,
            "placeholder_text_color": FAINT,
        },
        "CTkCheckBox": {
            "corner_radius": 2,
            "border_width": 1,
            "fg_color": AMBER,
            "border_color": LINE2,
            "hover_color": AMBER2,
            "checkmark_color": ON_AMBER,
            "text_color": TXT,
            "text_color_disabled": FAINT,
        },
        "CTkSwitch": {
            "corner_radius": 10,
            "border_width": 2,
            "button_length": 0,
            "fg_color": LINE2,
            "progress_color": AMBER,
            "button_color": TXT,
            "button_hover_color": TXT,
            "text_color": TXT,
            "text_color_disabled": FAINT,
        },
        "CTkRadioButton": {
            "corner_radius": 1000,
            "border_width_checked": 4,
            "border_width_unchecked": 1,
            "fg_color": AMBER,
            "border_color": LINE2,
            "hover_color": AMBER2,
            "text_color": TXT,
            "text_color_disabled": FAINT,
        },
        "CTkProgressBar": {
            "corner_radius": 0,
            "border_width": 0,
            "fg_color": BG3,
            "progress_color": DIM,
            "border_color": LINE,
        },
        "CTkSlider": {
            "corner_radius": 2,
            "button_corner_radius": 2,
            "border_width": 6,
            "button_length": 0,
            "fg_color": LINE2,
            "progress_color": DIM,
            "button_color": DIM,
            "button_hover_color": AMBER,
        },
        "CTkOptionMenu": {
            "corner_radius": 2,
            "fg_color": BG,
            "button_color": BG,
            "button_hover_color": BG,
            "text_color": TXT,
            "text_color_disabled": FAINT,
        },
        "CTkComboBox": {
            "corner_radius": 3,
            "border_width": 1,
            "fg_color": BG,
            "border_color": LINE2,
            "button_color": LINE2,
            "button_hover_color": AMBER,
            "text_color": TXT,
            "text_color_disabled": FAINT,
        },
        "CTkScrollbar": {
            "corner_radius": 3,
            "border_spacing": 2,
            "fg_color": "transparent",
            "button_color": LINE2,
            "button_hover_color": DIM,
        },
        "CTkSegmentedButton": {
            "corner_radius": 3,
            "border_width": 1,
            "fg_color": LINE2,
            "selected_color": BG3,
            "selected_hover_color": BG3,
            "unselected_color": BG,
            "unselected_hover_color": BG3,
            "text_color": TXT,
            "text_color_disabled": FAINT,
        },
        "CTkTextbox": {
            "corner_radius": 3,
            "border_width": 0,
            "fg_color": PIT,
            "border_color": LINE,
            "text_color": DIM,
            "scrollbar_button_color": LINE2,
            "scrollbar_button_hover_color": DIM,
        },
        "CTkScrollableFrame": {"label_fg_color": BG2},
        "DropdownMenu": {"fg_color": BG2, "hover_color": BG3, "text_color": TXT},
        "CTkFont": {"family": _resolved["sans"][0], "size": 13, "weight": "normal"},
    }


def install() -> None:
    """Делает тему активной. Вызывается до создания виджетов."""
    ctk.ThemeManager.theme = build_theme()
    ctk.ThemeManager._currently_loaded_theme = "stemnica"
    ctk.set_appearance_mode("Dark")


# -- масштаб -----------------------------------------------------------------
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


def apply_scale(scale: float) -> float:
    """Применяет масштаб ко всем окнам и возвращает фактическое значение."""
    value = normalize_scale(scale)
    ctk.set_widget_scaling(value)
    ctk.set_window_scaling(value)
    return value


def widget_scale(widget) -> float:
    """Итоговый множитель (DPI × масштаб) для рисования «сырыми» пикселями."""
    try:
        return ctk.ScalingTracker.get_widget_scaling(widget)
    except Exception:  # noqa: BLE001 - виджет вне отслеживаемого окна
        return 1.0


# -- оболочка Windows (§14.1) -------------------------------------------------
APP_ICON = Path(__file__).resolve().parent.parent / "resources" / "app.ico"

_DWMWA_BORDER_COLOR = 34
_DWMWA_CAPTION_COLOR = 35
_DWMWA_TEXT_COLOR = 36


def style_window(window) -> None:
    """Значок и цвета заголовка окна (Windows 11) под фон приложения.

    CustomTkinter сам включает тёмный заголовок; здесь ему задаётся
    точный цвет фона, рамки и текста. На Windows 10 эти атрибуты не
    поддерживаются, и вызов тихо ничего не меняет.
    """
    if APP_ICON.is_file():
        try:
            window.iconbitmap(str(APP_ICON))
        except Exception:  # noqa: BLE001 - значок — не повод не открыть окно
            log.debug("Значок окна не установлен", exc_info=True)
    if sys.platform != "win32":
        return
    # Рамка окна появляется не сразу: CustomTkinter ещё прячет и снова
    # показывает окно, перекрашивая заголовок в тёмный.
    window.after(120, lambda: _paint_titlebar(window))


def _paint_titlebar(window) -> None:
    try:
        window.update_idletasks()
        hwnd = ctypes.wintypes.HWND(int(window.wm_frame(), 16))
        for attribute, value in (
            (_DWMWA_CAPTION_COLOR, BG),
            (_DWMWA_BORDER_COLOR, LINE),
            (_DWMWA_TEXT_COLOR, TXT),
        ):
            red, green, blue = _rgb(value)
            colorref = ctypes.c_int(red | (green << 8) | (blue << 16))
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attribute, ctypes.byref(colorref), ctypes.sizeof(colorref)
            )
    except Exception:  # noqa: BLE001 - окно могли закрыть; DWM может быть недоступен
        log.debug("Цвет заголовка окна не задан", exc_info=True)
