"""Базовые элементы оформления: карточки, страницы, типографика, кнопки.

Повторяют ``presentation/views/widgets.py`` из ZapretGUI: там из
``Card``, ``Page``, ``hero``/``muted``/``status_label`` и фабрик кнопок
собран каждый экран. Здесь — то же самое для CustomTkinter, с цветами
исключительно из :mod:`ytdlp_gui.gui.theme`.
"""

from __future__ import annotations

from collections.abc import Callable

import customtkinter as ctk

from .. import theme


class Card(ctk.CTkFrame):
    """Поверхность с заголовком — основной блок компоновки экранов.

    Содержимое кладут в :attr:`body` (обычный прозрачный фрейм), сама
    карточка отвечает только за фон, рамку, скругление и поля.
    """

    def __init__(self, master, title: str = "", *, subtitle: str = "", **kwargs) -> None:
        super().__init__(
            master,
            fg_color=theme.color("bg.surface"),
            border_color=theme.color("border"),
            border_width=1,
            corner_radius=theme.RADIUS["md"],
            **kwargs,
        )
        self.grid_columnconfigure(0, weight=1)

        self.title_label = ctk.CTkLabel(
            self, text=title, anchor="w", font=theme.font("large", weight="bold")
        )
        self.subtitle_label = ctk.CTkLabel(
            self,
            text=subtitle,
            anchor="w",
            justify="left",
            text_color=theme.color("fg.secondary"),
            font=theme.font("small"),
        )
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.grid_columnconfigure(0, weight=1)

        self._place_header(title, subtitle)

    def _place_header(self, title: str, subtitle: str) -> None:
        row = 0
        if title:
            self.title_label.grid(
                row=row, column=0, sticky="ew", padx=theme.GAP["xl"], pady=(theme.GAP["lg"], 0)
            )
            row += 1
        if subtitle:
            self.subtitle_label.grid(
                row=row, column=0, sticky="ew", padx=theme.GAP["xl"], pady=(2, 0)
            )
            row += 1
        top_pad = theme.GAP["md"] if (title or subtitle) else theme.GAP["lg"]
        self.body.grid(
            row=row,
            column=0,
            sticky="nsew",
            padx=theme.GAP["xl"],
            pady=(top_pad, theme.GAP["lg"]),
        )
        self.grid_rowconfigure(row, weight=1)


class Page(ctk.CTkScrollableFrame):
    """Прокручиваемый экран с одинаковыми полями — как ``Page`` в ZapretGUI.

    Карточки складываются сверху вниз методом :meth:`add`; порядок строк
    ведётся самим экраном, поэтому вызывающему коду не нужно считать
    индексы ``grid``.
    """

    def __init__(self, master, **kwargs) -> None:
        super().__init__(master, fg_color="transparent", corner_radius=0, **kwargs)
        self.grid_columnconfigure(0, weight=1)
        self._next_row = 0

    def add(self, widget, *, stretch: bool = False, pady: tuple[int, int] | int | None = None):
        """Добавляет виджет очередной строкой экрана."""
        if pady is None:
            pady = (0, theme.GAP["md"])
        widget.grid(row=self._next_row, column=0, sticky="nsew" if stretch else "ew", pady=pady)
        if stretch:
            self.grid_rowconfigure(self._next_row, weight=1)
        self._next_row += 1
        return widget


# -- типографика --------------------------------------------------------------
def title_label(master, text: str = "", **kwargs) -> ctk.CTkLabel:
    return ctk.CTkLabel(master, text=text, anchor="w", font=theme.font("title", weight="bold"), **kwargs)


def body_label(master, text: str = "", **kwargs) -> ctk.CTkLabel:
    return ctk.CTkLabel(master, text=text, anchor="w", justify="left", **kwargs)


def muted_label(master, text: str = "", **kwargs) -> ctk.CTkLabel:
    return ctk.CTkLabel(
        master,
        text=text,
        anchor="w",
        justify="left",
        text_color=theme.color("fg.secondary"),
        font=theme.font("small"),
        **kwargs,
    )


#: Уровень важности -> токен цвета (как ``status_label`` в ZapretGUI).
SEVERITY_TOKENS = {
    "ok": "state.ok",
    "warning": "state.warn",
    "error": "state.error",
    "critical": "state.error",
    "info": "state.info",
    "idle": "fg.secondary",
    "busy": "state.info",
}


def status_label(master, text: str = "", severity: str = "info", **kwargs) -> ctk.CTkLabel:
    return ctk.CTkLabel(
        master,
        text=text,
        anchor="w",
        justify="left",
        text_color=theme.color(SEVERITY_TOKENS.get(severity, "state.info")),
        font=theme.font("base", weight="bold"),
        **kwargs,
    )


def set_severity(label: ctk.CTkLabel, severity: str) -> None:
    label.configure(text_color=theme.color(SEVERITY_TOKENS.get(severity, "state.info")))


def separator(master) -> ctk.CTkFrame:
    line = ctk.CTkFrame(master, height=1, corner_radius=0, fg_color=theme.color("border"))
    line.grid_propagate(False)
    return line


# -- кнопки -------------------------------------------------------------------
_BUTTON_HEIGHT = 34
_COMPACT_HEIGHT = 28


def button(master, text: str, command: Callable[[], None] | None = None, **kwargs) -> ctk.CTkButton:
    """Вторичная кнопка — вид по умолчанию (как ``QPushButton`` в ZapretGUI)."""
    kwargs.setdefault("height", _BUTTON_HEIGHT)
    return ctk.CTkButton(master, text=text, command=command, **kwargs)


def primary_button(master, text: str, command: Callable[[], None] | None = None, **kwargs) -> ctk.CTkButton:
    kwargs.setdefault("height", _BUTTON_HEIGHT)
    kwargs.setdefault("font", theme.font("base", weight="bold"))
    return ctk.CTkButton(
        master,
        text=text,
        command=command,
        fg_color=theme.color("accent"),
        hover_color=theme.color("accent.hover"),
        border_color=theme.color("accent"),
        text_color=theme.color("accent.fg"),
        **kwargs,
    )


def danger_button(master, text: str, command: Callable[[], None] | None = None, **kwargs) -> ctk.CTkButton:
    kwargs.setdefault("height", _BUTTON_HEIGHT)
    return ctk.CTkButton(
        master,
        text=text,
        command=command,
        fg_color=theme.color("bg.elevated"),
        hover_color=theme.color("bg.hover"),
        border_color=theme.color("border.strong"),
        text_color=theme.color("state.error"),
        **kwargs,
    )


def link_button(master, text: str, command: Callable[[], None] | None = None, **kwargs) -> ctk.CTkButton:
    kwargs.setdefault("height", _COMPACT_HEIGHT)
    return ctk.CTkButton(
        master,
        text=text,
        command=command,
        fg_color="transparent",
        hover_color=theme.color("bg.hover"),
        border_width=0,
        text_color=theme.color("accent"),
        **kwargs,
    )


def compact_button(master, text: str, command: Callable[[], None] | None = None, *, primary: bool = False, **kwargs) -> ctk.CTkButton:
    """Уменьшенная кнопка — для строк списков и таблиц."""
    kwargs.setdefault("height", _COMPACT_HEIGHT)
    kwargs.setdefault("font", theme.font("small", weight="bold" if primary else "normal"))
    factory = primary_button if primary else button
    return factory(master, text, **kwargs)


def icon_button(master, text: str, command: Callable[[], None] | None = None, **kwargs) -> ctk.CTkButton:
    """Кнопка-значок без рамки (закрыть, удалить строку)."""
    kwargs.setdefault("width", 28)
    kwargs.setdefault("height", 28)
    return ctk.CTkButton(
        master,
        text=text,
        command=command,
        fg_color="transparent",
        hover_color=theme.color("bg.hover"),
        border_width=0,
        text_color=theme.color("fg.secondary"),
        **kwargs,
    )


class NavButton(ctk.CTkButton):
    """Пункт боковой навигации: активный подсвечен, остальные приглушены."""

    def __init__(self, master, text: str, command: Callable[[], None] | None = None, **kwargs) -> None:
        super().__init__(
            master,
            text=text,
            command=command,
            anchor="w",
            height=38,
            corner_radius=theme.RADIUS["sm"],
            border_width=0,
            fg_color="transparent",
            hover_color=theme.color("bg.hover"),
            text_color=theme.color("fg.secondary"),
            font=theme.font("base"),
            **kwargs,
        )
        self._active = False

    def set_active(self, active: bool) -> None:
        if active == self._active:
            return
        self._active = active
        self.configure(
            fg_color=theme.color("bg.selected") if active else "transparent",
            text_color=theme.color("fg.primary") if active else theme.color("fg.secondary"),
            font=theme.font("base", weight="bold" if active else "normal"),
        )


# -- строки формы -------------------------------------------------------------
def form_frame(master, row: int = 0, **grid_options) -> ctk.CTkFrame:
    """Отдельная сетка под строки формы.

    Полноширинные элементы (длинные подписи, группы флажков) держат в
    родителе, а не в этой сетке: виджет, растянутый через ``columnspan``,
    расширяет колонку подписей и ломает выравнивание строк формы.
    """
    frame = ctk.CTkFrame(master, fg_color="transparent")
    grid_options.setdefault("sticky", "ew")
    frame.grid(row=row, column=0, **grid_options)
    frame.grid_columnconfigure(1, weight=1)
    return frame


def form_row(
    master,
    row: int,
    text: str,
    widget,
    *,
    trailing=None,
    label_width: int = 230,
    stretch: bool = True,
) -> ctk.CTkLabel:
    """Подпись + элемент управления в одной строке ``grid``.

    Подпись занимает колонку фиксированной ширины, поэтому строки формы
    выравниваются между собой — как ``form_row`` в ZapretGUI.
    """
    label = ctk.CTkLabel(master, text=text, anchor="w", width=label_width, justify="left")
    label.grid(row=row, column=0, sticky="w", padx=(0, theme.GAP["md"]), pady=theme.GAP["xs"])
    widget.grid(row=row, column=1, sticky="ew" if stretch else "w", pady=theme.GAP["xs"])
    if trailing is not None:
        trailing.grid(row=row, column=2, sticky="w", padx=(theme.GAP["sm"], 0), pady=theme.GAP["xs"])
    master.grid_columnconfigure(1, weight=1)
    return label
