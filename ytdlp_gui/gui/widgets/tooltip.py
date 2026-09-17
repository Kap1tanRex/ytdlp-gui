"""Всплывающая подсказка при наведении (design-system §8.5).

Фон ``BG2``, рамка ``LINE2``, задержка 0.5 с. Показ проверяет настройку
``show_tooltips`` в момент наведения, поэтому переключатель в настройках
действует сразу. Окно — обычный ``tk.Toplevel``: у CTkToplevel есть
перерисовка заголовка, которая для подсказки даёт мерцание.
"""

from __future__ import annotations

import tkinter as tk

from .. import theme


class Tooltip:
    """Подсказка поверх произвольного виджета."""

    def __init__(self, widget, app, text: str, delay: int = 500) -> None:
        self.widget = widget
        self.app = app
        self.text = text
        self.delay = delay
        self._after_id: str | None = None
        self._window: tk.Toplevel | None = None

        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event=None) -> None:
        self._cancel()
        if self.app is not None and not getattr(self.app.settings, "show_tooltips", True):
            return
        if self.text:
            self._after_id = self.widget.after(self.delay, self._show)

    def _cancel(self) -> None:
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

    def _show(self) -> None:
        self._after_id = None
        if self._window is not None:
            return
        try:
            x = self.widget.winfo_rootx() + 12
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        except tk.TclError:  # виджет уже уничтожен
            return
        scale = theme.widget_scale(self.widget)
        family = theme.sans(12).actual("family")
        window = tk.Toplevel(self.widget)
        window.wm_overrideredirect(True)
        window.configure(bg=theme.LINE2)
        try:
            window.attributes("-topmost", True)
        except tk.TclError:
            pass
        tk.Label(
            window,
            text=self.text,
            justify="left",
            anchor="w",
            bg=theme.BG2,
            fg=theme.TXT,
            font=(family, -round(12 * scale)),
            wraplength=round(340 * scale),
            padx=round(10 * scale),
            pady=round(6 * scale),
        ).pack(padx=1, pady=1)
        window.wm_geometry(f"+{x}+{y}")
        self._window = window

    def _hide(self, _event=None) -> None:
        self._cancel()
        if self._window is not None:
            try:
                self._window.destroy()
            except tk.TclError:
                pass
            self._window = None
