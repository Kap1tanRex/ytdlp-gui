"""Список запрошенных видео/плейлистов."""

from __future__ import annotations

from collections.abc import Callable

import customtkinter as ctk

from .. import theme
from .design import icon_button, muted_label


class ItemList(ctk.CTkScrollableFrame):
    """Прокручиваемый список видео с выбором и удалением.

    Строки оформлены как в списках ZapretGUI: обычная строка — поднятая
    поверхность с рамкой, выбранная — подсвеченная фоном ``bg.selected``.
    """

    def __init__(
        self,
        master,
        on_select: Callable[[int], None],
        on_remove: Callable[[int], None],
        empty_text: str = "Список пуст",
        height: int = 150,
    ) -> None:
        super().__init__(master, height=height, fg_color="transparent", corner_radius=0)
        # ``height`` в CTkScrollableFrame задаёт высоту только внутреннего
        # холста; внешний фрейм продолжает запрашивать свои 200 px по
        # умолчанию, и список занимал бы пол-экрана. Фиксируем высоту
        # самого фрейма — она по-прежнему пересчитывается при смене
        # масштаба интерфейса, т.к. CTkFrame масштабирует размеры сам.
        self._parent_frame.configure(height=height)
        self._parent_frame.grid_propagate(False)
        self.on_select = on_select
        self.on_remove = on_remove
        self.empty_text = empty_text
        self.grid_columnconfigure(0, weight=1)

        self._rows: list[ctk.CTkFrame] = []
        self._empty_label: ctk.CTkLabel | None = None
        self._selected_index = -1
        self._show_empty()

    def _clear(self) -> None:
        for row in self._rows:
            row.destroy()
        self._rows.clear()
        if self._empty_label is not None:
            self._empty_label.destroy()
            self._empty_label = None

    def _show_empty(self) -> None:
        self._empty_label = muted_label(self, self.empty_text)
        self._empty_label.grid(row=0, column=0, sticky="w", padx=theme.GAP["sm"], pady=theme.GAP["sm"])

    def set_items(self, items: list, selected_index: int = -1) -> None:
        self._clear()
        self._selected_index = selected_index
        if not items:
            self._show_empty()
            return
        for index, info in enumerate(items):
            self._add_row(index, info)

    def _row_color(self, index: int):
        return theme.color("bg.selected") if index == self._selected_index else theme.color("bg.elevated")

    def _add_row(self, index: int, info) -> None:
        row = ctk.CTkFrame(
            self,
            fg_color=self._row_color(index),
            border_color=theme.color("border"),
            border_width=1,
            corner_radius=theme.RADIUS["sm"],
        )
        row.grid(row=index, column=0, sticky="ew", pady=2)
        row.grid_columnconfigure(0, weight=1)

        label = ctk.CTkLabel(row, text=info.summary_line(), anchor="w", justify="left")
        label.grid(row=0, column=0, sticky="ew", padx=theme.GAP["md"], pady=theme.GAP["sm"])

        remove_button = icon_button(row, "✕", lambda i=index: self.on_remove(i))
        remove_button.grid(row=0, column=1, padx=(theme.GAP["xs"], theme.GAP["sm"]), pady=theme.GAP["xs"])

        for widget in (row, label):
            widget.bind("<Button-1>", lambda _e, i=index: self.on_select(i))

        self._rows.append(row)

    def highlight(self, index: int) -> None:
        self._selected_index = index
        for row_index, row in enumerate(self._rows):
            row.configure(fg_color=self._row_color(row_index))
