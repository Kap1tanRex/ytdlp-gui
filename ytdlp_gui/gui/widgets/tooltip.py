"""Всплывающая подсказка при наведении на параметр.

Показ подсказки проверяет настройку ``show_tooltips`` в момент наведения
(не при создании виджета) — переключатель в настройках работает сразу,
без перезапуска приложения.
"""

from __future__ import annotations

import customtkinter as ctk

from .. import theme


class Tooltip:
    """Простая всплывающая подсказка поверх произвольного виджета."""

    def __init__(self, widget, app, text: str, delay: int = 450) -> None:
        self.widget = widget
        self.app = app
        self.text = text
        self.delay = delay
        self._after_id: str | None = None
        self._window: ctk.CTkToplevel | None = None

        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event=None) -> None:
        self._cancel()
        if not getattr(self.app.settings, "show_tooltips", True) or not self.text:
            return
        self._after_id = self.widget.after(self.delay, self._show)

    def _cancel(self) -> None:
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:  # noqa: BLE001
                pass
            self._after_id = None

    def _show(self) -> None:
        if self._window is not None:
            return
        try:
            x = self.widget.winfo_rootx() + 12
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        except Exception:  # noqa: BLE001 - виджет мог быть уже уничтожен
            return

        window = ctk.CTkToplevel(self.widget)
        window.wm_overrideredirect(True)
        window.wm_geometry(f"+{x}+{y}")
        try:
            window.attributes("-topmost", True)
        except Exception:  # noqa: BLE001
            pass
        ctk.CTkLabel(
            window,
            text=self.text,
            justify="left",
            anchor="w",
            fg_color=theme.color("bg.elevated"),
            text_color=theme.color("fg.primary"),
            corner_radius=theme.RADIUS["sm"],
            font=theme.font("small"),
            wraplength=320,
            padx=10,
            pady=6,
        ).pack()
        self._window = window

    def _hide(self, _event=None) -> None:
        self._cancel()
        if self._window is not None:
            try:
                self._window.destroy()
            except Exception:  # noqa: BLE001
                pass
            self._window = None
