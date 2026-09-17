"""Шапка окна (design-system §6.1).

Слева логотип и подзаголовок, через 36 px — вкладки с янтарным
подчёркиванием, которое едет к выбранной; справа — чипы состояния.
Когда места мало, первым прячется подзаголовок, затем чипы в порядке
приоритета.
"""

from __future__ import annotations

import time
import tkinter as tk
from collections.abc import Callable, Sequence

import customtkinter as ctk

from .. import theme
from .design import Chip, box, caps_text, hline, set_caps, text
from .layout import page_margin

UNDERLINE_MS = 200


def _snap(t: float) -> float:
    """Приближение cubic-bezier(.22, 1, .36, 1) — кривая ``snap``."""
    return 1 - (1 - t) ** 4


class _Tab(ctk.CTkFrame):
    def __init__(self, master, title: str, command: Callable[[], None]) -> None:
        super().__init__(master, fg_color="transparent", width=0, height=0, cursor="hand2")
        self.grid_rowconfigure(0, weight=1)
        self.active = False
        self._hovered = False
        self.label = caps_text(self, title, size=11, tracking=0.12, color=theme.DIM, cursor="hand2")
        self.label.grid(row=0, column=0, padx=12)
        self.badge = ctk.CTkLabel(
            self,
            text="",
            width=16,
            height=14,
            corner_radius=7,
            fg_color=theme.AMBER,
            text_color=theme.ON_AMBER,
            font=theme.mono_medium(9),
            cursor="hand2",
        )
        for widget in (self, self.label, self.badge):
            widget.bind("<Button-1>", lambda _e: command())
            widget.bind("<Enter>", lambda _e: self._hover(True))
            widget.bind("<Leave>", lambda _e: self._hover(False))

    def _hover(self, inside: bool) -> None:
        self._hovered = inside
        self._paint()

    def _paint(self) -> None:
        self.label.configure(text_color=theme.TXT if self.active or self._hovered else theme.DIM)

    def set_active(self, active: bool) -> None:
        self.active = active
        self._paint()

    def set_count(self, count: int) -> None:
        if count > 0:
            self.badge.configure(text=str(count) if count < 100 else "99")
            self.badge.grid(row=0, column=1, padx=(0, 12))
            self.label.grid(padx=(12, 6))
        else:
            self.badge.grid_remove()
            self.label.grid(padx=12)


class Header(ctk.CTkFrame):
    """Логотип, вкладки и чипы."""

    def __init__(
        self,
        master,
        *,
        title: str,
        subtitle: str,
        tabs: Sequence[tuple[str, str]],
        on_select: Callable[[str], None],
    ) -> None:
        super().__init__(master, fg_color=theme.BG, corner_radius=0, height=theme.HEADER_HEIGHT)
        self.grid_propagate(False)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(3, weight=1)
        self._on_select = on_select
        self._current = ""
        self._margin = theme.PAGE_PAD

        self.logo = caps_text(
            self, title, font=theme.display_semi(15), tracking=0.16, color=theme.TXT
        )
        self.logo.grid(row=0, column=0, sticky="w", padx=(theme.PAGE_PAD, 0))
        self.subtitle = text(self, subtitle, font=theme.mono(11), color=theme.DIM)
        self.subtitle.grid(row=0, column=1, sticky="w", padx=(12, 0), pady=(3, 0))

        self.tabs_frame = box(self)
        self.tabs_frame.grid(row=0, column=2, sticky="ns", padx=(24, 0))
        self.tabs_frame.grid_rowconfigure(0, weight=1)
        self.tabs: dict[str, _Tab] = {}
        for index, (key, title_text) in enumerate(tabs):
            tab = _Tab(self.tabs_frame, title_text, lambda k=key: self._on_select(k))
            tab.grid(row=0, column=index, sticky="ns", padx=(0 if index == 0 else 4, 0))
            self.tabs[key] = tab

        self.chips_frame = box(self)
        self.chips_frame.grid(row=0, column=4, sticky="e", padx=(16, theme.PAGE_PAD))
        self.chips: dict[str, Chip] = {}
        self._chip_priority: dict[str, int] = {}
        self._chip_wanted: dict[str, bool] = {}
        self._fit_job: str | None = None

        hline(self).place(relx=0, rely=1.0, relwidth=1, anchor="sw")
        self._underline = tk.Frame(self, bg=theme.AMBER, height=2, highlightthickness=0, bd=0)
        self._line_from = (0.0, 0.0)
        self._line_to = (0.0, 0.0)
        self._line_t0 = 0.0
        self._line_job: str | None = None

        tk.Frame.bind(self, "<Configure>", self._on_resize, add="+")

    # -- вкладки -------------------------------------------------------------
    def select(self, key: str) -> None:
        if key not in self.tabs:
            return
        animate = bool(self._current)
        self._current = key
        for tab_key, tab in self.tabs.items():
            tab.set_active(tab_key == key)
        self.after_idle(lambda: self._move_underline(animate))

    def set_count(self, key: str, count: int) -> None:
        tab = self.tabs.get(key)
        if tab is not None:
            tab.set_count(count)
            self.after_idle(lambda: self._move_underline(False))

    def _tab_span(self) -> tuple[float, float]:
        tab = self.tabs[self._current]
        x = self.tabs_frame.winfo_x() + tab.winfo_x()
        return float(x), float(tab.winfo_width())

    def _move_underline(self, animate: bool) -> None:
        if not self._current:
            return
        try:
            target = self._tab_span()
        except tk.TclError:
            return
        if not animate or not self._underline.winfo_manager():
            self._line_from = self._line_to = target
            self._place_underline(target)
            return
        current = self._current_span()
        self._line_from, self._line_to = current, target
        self._line_t0 = time.monotonic()
        if self._line_job is None:
            self._animate_underline()

    def _current_span(self) -> tuple[float, float]:
        info = self._underline.place_info()
        return float(info.get("x", 0)), float(info.get("width", 0))

    def _animate_underline(self) -> None:
        progress = min(1.0, (time.monotonic() - self._line_t0) * 1000 / UNDERLINE_MS)
        eased = _snap(progress)
        (x0, w0), (x1, w1) = self._line_from, self._line_to
        self._place_underline((x0 + (x1 - x0) * eased, w0 + (w1 - w0) * eased))
        self._line_job = self.after(16, self._animate_underline) if progress < 1.0 else None

    def _place_underline(self, span: tuple[float, float]) -> None:
        x, width = span
        height = self.winfo_height()
        self._underline.place(x=round(x), y=height - 2, width=round(width), height=2)
        self._underline.lift()

    # -- чипы ----------------------------------------------------------------
    def add_chip(self, key: str, *, priority: int) -> Chip:
        chip = Chip(self.chips_frame)
        self.chips[key] = chip
        self._chip_priority[key] = priority
        self._chip_wanted[key] = False
        return chip

    def set_chip(
        self, key: str, value: str, led: str | None = None, *, command=None, visible: bool = True
    ) -> None:
        chip = self.chips[key]
        chip.set(value, led, command=command)
        self._chip_wanted[key] = visible
        self._schedule_fit()

    def set_subtitle(self, value: str) -> None:
        self.subtitle.configure(text=value)

    def set_title(self, value: str) -> None:
        set_caps(self.logo, value, 0.16)

    # -- раскладка -----------------------------------------------------------
    def _on_resize(self, event) -> None:
        margin = page_margin(event.width, theme.widget_scale(self))
        if margin != self._margin:
            self._margin = margin
            self.logo.grid(padx=(margin, 0))
            self.chips_frame.grid(padx=(16, margin))
        self._schedule_fit()
        self.after_idle(lambda: self._move_underline(False))

    def _schedule_fit(self) -> None:
        # Ширины виджетов пересчитываются в простое — считать раньше рано.
        if self._fit_job is None:
            self._fit_job = self.after_idle(self._fit)

    def _fit(self) -> None:
        """Прячет подзаголовок и чипы, которым не хватает места."""
        self._fit_job = None
        try:
            available = self.winfo_width()
        except tk.TclError:
            return
        if available <= 1:
            return
        scale = theme.widget_scale(self)
        gap = round(8 * scale)
        fixed = (
            self.logo.winfo_reqwidth()
            + self.tabs_frame.winfo_reqwidth()
            + round((2 * self._margin + 24 + 16 + 24) * scale)
        )
        order = sorted(self.chips, key=lambda k: self._chip_priority[k])
        chips_width = 0
        shown: list[str] = []
        for key in order:
            if not self._chip_wanted[key]:
                continue
            width = self.chips[key].winfo_reqwidth() + gap
            if fixed + chips_width + width <= available:
                chips_width += width
                shown.append(key)
        subtitle_width = self.subtitle.winfo_reqwidth() + round(12 * scale)
        show_subtitle = fixed + chips_width + subtitle_width <= available

        if show_subtitle:
            self.subtitle.grid()
        else:
            self.subtitle.grid_remove()
        # Порядок чипов слева направо постоянный; приоритет решает только, кого прятать.
        column = 0
        for key, chip in self.chips.items():
            if key in shown:
                chip.grid(row=0, column=column, padx=(8 if column else 0, 0))
                column += 1
            else:
                chip.grid_remove()
