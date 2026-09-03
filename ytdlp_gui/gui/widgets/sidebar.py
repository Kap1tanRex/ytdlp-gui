"""Боковая панель навигации.

Повторяет сайдбар ZapretGUI (``presentation/views/main_window.py``):
название приложения, подпись, список разделов и версия внизу. Разделы —
это те же экраны, что раньше были вкладками ``CTkTabview``: логика и
состав экранов не изменились, изменился только способ переключения.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import customtkinter as ctk

from .. import theme
from .design import NavButton, link_button


class Sidebar(ctk.CTkFrame):
    def __init__(
        self,
        master,
        *,
        title: str,
        subtitle: str,
        items: Sequence[str],
        on_select: Callable[[int], None],
    ) -> None:
        super().__init__(
            master,
            width=theme.SIDEBAR_WIDTH,
            corner_radius=0,
            fg_color=theme.color("bg.surface"),
        )
        self.grid_propagate(False)
        self.grid_columnconfigure(0, weight=1)

        self._on_select = on_select
        self._current = -1

        self.title_label = ctk.CTkLabel(
            self, text=title, anchor="w", font=theme.font("title", weight="bold")
        )
        self.title_label.grid(
            row=0, column=0, sticky="ew", padx=theme.GAP["lg"], pady=(theme.GAP["lg"], 0)
        )

        self.subtitle_label = ctk.CTkLabel(
            self,
            text=subtitle,
            anchor="w",
            justify="left",
            wraplength=theme.SIDEBAR_WIDTH - 2 * theme.GAP["lg"],
            font=theme.font("small"),
            text_color=theme.color("fg.secondary"),
        )
        self.subtitle_label.grid(
            row=1, column=0, sticky="ew", padx=theme.GAP["lg"], pady=(2, theme.GAP["md"])
        )

        self.buttons: list[NavButton] = []
        for index, text in enumerate(items):
            nav = NavButton(self, text, command=lambda i=index: self.select(i))
            nav.grid(row=2 + index, column=0, sticky="ew", padx=theme.GAP["sm"], pady=2)
            self.buttons.append(nav)

        spacer_row = 2 + len(self.buttons)
        self.grid_rowconfigure(spacer_row, weight=1)

        self.footer = ctk.CTkFrame(self, fg_color="transparent")
        self.footer.grid(row=spacer_row + 1, column=0, sticky="ew", padx=theme.GAP["sm"], pady=(0, theme.GAP["sm"]))
        self.footer.grid_columnconfigure(0, weight=1)

        self.help_button = link_button(self.footer, "")
        self.help_button.grid(row=0, column=0, sticky="ew")

        self.version_label = ctk.CTkLabel(
            self,
            text="",
            anchor="w",
            font=theme.font("small"),
            text_color=theme.color("fg.secondary"),
        )
        self.version_label.grid(
            row=spacer_row + 2, column=0, sticky="ew", padx=theme.GAP["lg"], pady=(0, theme.GAP["md"])
        )

        # Правая граница панели (в ZapretGUI — border-right у #Sidebar).
        self._border = ctk.CTkFrame(self, width=1, corner_radius=0, fg_color=theme.color("border"))
        self._border.place(relx=1.0, rely=0, relheight=1.0, anchor="ne")

    # -- навигация -----------------------------------------------------------
    def select(self, index: int) -> None:
        if not 0 <= index < len(self.buttons):
            return
        self._current = index
        for position, nav in enumerate(self.buttons):
            nav.set_active(position == index)
        self._on_select(index)

    @property
    def current(self) -> int:
        return self._current

    # -- подписи -------------------------------------------------------------
    def set_version(self, text: str) -> None:
        self.version_label.configure(text=text)

    def set_help(self, text: str, command: Callable[[], None]) -> None:
        self.help_button.configure(text=text, command=command)
