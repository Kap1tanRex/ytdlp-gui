"""Нижняя строка состояния — «работает ли оно» одним взглядом.

Повторяет ``StatusStrip`` из ZapretGUI: слева — последнее сообщение
приложения, справа — по одному индикатору на каждую наблюдаемую
подсистему (yt-dlp, FFmpeg, очередь). Индикатор — цветная точка и
подпись; цвет берётся из токенов ``state.*``.
"""

from __future__ import annotations

import customtkinter as ctk

from .. import theme
from .design import SEVERITY_TOKENS
from .tooltip import Tooltip

DOT_SIZE = 10


class StatusChip(ctk.CTkFrame):
    """Цветная точка и подпись: одна наблюдаемая подсистема."""

    def __init__(self, master, caption: str = "", *, app=None) -> None:
        super().__init__(master, fg_color="transparent")
        self._app = app
        self._tooltip: Tooltip | None = None

        self.dot = ctk.CTkFrame(
            self,
            width=DOT_SIZE,
            height=DOT_SIZE,
            corner_radius=DOT_SIZE,
            fg_color=theme.color("fg.secondary"),
        )
        self.dot.grid(row=0, column=0, padx=(0, 6))
        self.dot.grid_propagate(False)

        self.label = ctk.CTkLabel(
            self, text=caption, anchor="w", font=theme.font("small"), text_color=theme.color("fg.primary")
        )
        self.label.grid(row=0, column=1)

    def set_state(self, caption: str, health: str = "idle", tooltip: str = "") -> None:
        self.label.configure(text=caption)
        self.dot.configure(fg_color=theme.color(SEVERITY_TOKENS.get(health, "fg.secondary")))
        if tooltip and self._app is not None:
            if self._tooltip is None:
                self._tooltip = Tooltip(self.label, self._app, tooltip)
            else:
                self._tooltip.text = tooltip


class StatusStrip(ctk.CTkFrame):
    """Полоса состояния во всю ширину окна, под областью содержимого."""

    def __init__(self, master, *, app=None) -> None:
        super().__init__(
            master,
            corner_radius=0,
            fg_color=theme.color("bg.surface"),
            border_width=0,
        )
        self._app = app
        self.grid_columnconfigure(0, weight=1)

        # Верхняя граница полосы (в ZapretGUI — border-top у QStatusBar).
        self._border = ctk.CTkFrame(self, height=1, corner_radius=0, fg_color=theme.color("border"))
        self._border.grid(row=0, column=0, columnspan=2, sticky="ew")

        self.message = ctk.CTkLabel(
            self,
            text="",
            anchor="w",
            justify="left",
            font=theme.font("small"),
            text_color=theme.color("fg.secondary"),
        )
        self.message.grid(row=1, column=0, sticky="ew", padx=(theme.GAP["lg"], theme.GAP["md"]), pady=6)

        self._chips_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._chips_frame.grid(row=1, column=1, sticky="e", padx=(0, theme.GAP["lg"]), pady=6)
        self._chips: dict[str, StatusChip] = {}

    # -- сообщение -----------------------------------------------------------
    def set_message(self, text: str, severity: str = "info") -> None:
        token = "fg.secondary" if severity == "info" else SEVERITY_TOKENS.get(severity, "fg.secondary")
        self.message.configure(text=text, text_color=theme.color(token))

    # -- индикаторы ----------------------------------------------------------
    def set_chip(self, key: str, caption: str, health: str = "idle", tooltip: str = "") -> None:
        chip = self._chips.get(key)
        if chip is None:
            chip = StatusChip(self._chips_frame, app=self._app)
            chip.grid(row=0, column=len(self._chips), padx=(theme.GAP["md"], 0))
            self._chips[key] = chip
        chip.set_state(caption, health, tooltip)
