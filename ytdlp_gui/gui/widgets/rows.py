"""Строка списка (design-system §7.2): ссылки на главной и задания очереди.

Высота 56, слева миниатюра, затем название (Sans 14) и строка данных
(Sans 12), справа статус и квадратные кнопки. Текущая строка — фон
``BG3`` и янтарная кромка 2 px слева, строка с ошибкой — фон ``ERR_BG``
и красная кромка, наведение — ``BG3`` α 0.8. У идущей загрузки по нижней
кромке — полоса прогресса 2 px.

Все элементы лежат прямо в строке, без промежуточных прозрачных рамок:
CustomTkinter перекрашивает подложку только у непосредственных детей.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

import customtkinter as ctk

from .. import theme
from .design import Line
from .thumbnail_view import Thumb

ROW_HEIGHT = 56

_EDGES = {"current": theme.AMBER, "error": theme.ERR}
_FILLS = {"normal": theme.BG2, "current": theme.BG3, "error": theme.ERR_BG}


class ListRow(ctk.CTkFrame):
    def __init__(self, master, *, on_click: Callable[[], None] | None = None) -> None:
        super().__init__(master, fg_color=theme.BG2, corner_radius=0, height=ROW_HEIGHT)
        self.grid_propagate(False)
        self.grid_rowconfigure((0, 1), weight=1)
        self.grid_columnconfigure(1, weight=1)
        self._on_click = on_click
        self._row_state = "normal"
        self._hovered = False
        self._right = 2

        self._edge = tk.Frame(self, width=2, highlightthickness=0, bd=0)
        self._bar = tk.Frame(self, height=2, bg=theme.DIM, highlightthickness=0, bd=0)

        self.thumb = Thumb(self, 64, 36)
        self.thumb.grid(row=0, column=0, rowspan=2, padx=(16, 14))
        self.title = Line(self, font=theme.sans(14), color=theme.TXT)
        self.title.grid(row=0, column=1, sticky="sew", pady=(0, 1))
        self.data = Line(self, font=theme.sans(12), color=theme.DIM)
        self.data.grid(row=1, column=1, sticky="new", pady=(1, 0))

        for widget in (self, self.thumb, self.title, self.data):
            widget.bind("<Enter>", lambda _e: self._hover(True))
            widget.bind("<Leave>", lambda _e: self._hover(False))
            if on_click is not None:
                widget.bind("<Button-1>", lambda _e: self._on_click())
        if on_click is not None:
            for widget in (self.title, self.data, self.thumb):
                widget.configure(cursor="hand2")

    def add_right(self, widget, *, padx=(8, 0)) -> None:
        """Кладёт элемент в правую часть строки, слева направо."""
        widget.grid(row=0, column=self._right, rowspan=2, padx=padx)
        self._right += 1

    def finish_right(self) -> None:
        """Отступ справа после последнего элемента."""
        self.grid_columnconfigure(self._right, minsize=round(14 * theme.widget_scale(self)))

    # -- состояние -----------------------------------------------------------
    def set_state(self, state: str) -> None:
        if state != self._row_state:
            self._row_state = state
            self._paint()

    def _hover(self, inside: bool) -> None:
        if inside:
            self._set_hovered(True)
        else:
            # Leave приходит и при переходе на дочерний виджет строки. Таймер —
            # на окне: строку могут пересоздать раньше, чем он сработает.
            self.winfo_toplevel().after(15, self._check_pointer)

    def _check_pointer(self) -> None:
        try:
            if not self.winfo_exists():
                return
            x, y = self.winfo_pointerxy()
            left, top = self.winfo_rootx(), self.winfo_rooty()
            inside = left <= x < left + self.winfo_width() and top <= y < top + self.winfo_height()
        except tk.TclError:
            return
        self._set_hovered(inside)

    def _set_hovered(self, hovered: bool) -> None:
        if hovered != self._hovered:
            self._hovered = hovered
            self._paint()

    def _paint(self) -> None:
        fill = _FILLS.get(self._row_state, theme.BG2)
        if self._row_state == "normal" and self._hovered:
            fill = theme.mix(theme.BG2, theme.BG3, 0.8)
        if self.cget("fg_color") != fill:
            self.configure(fg_color=fill)
        edge = _EDGES.get(self._row_state)
        if edge:
            self._edge.configure(bg=edge)
            self._edge.place(x=0, y=0, relheight=1)
            self._edge.lift()
        else:
            self._edge.place_forget()

    def set_progress(self, fraction: float | None) -> None:
        if fraction is None or fraction <= 0:
            self._bar.place_forget()
        else:
            self._bar.place(x=0, rely=1.0, relwidth=min(1.0, fraction), anchor="sw")
            self._bar.lift()
