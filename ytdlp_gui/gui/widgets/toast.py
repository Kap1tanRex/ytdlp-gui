"""Уведомления в левом нижнем углу окна (design-system §8.4).

Карточка ``TOAST_BG`` с цветной полосой слева: янтарь — сведения,
зелёный — успех, жёлтый — предупреждение, красный — ошибка. Живёт 5 с
(ошибка — 8 с); наведение продлевает жизнь, щелчок закрывает. Повтор
того же текста не плодит карточки, а перезапускает прежнюю. Стопка
растёт снизу вверх, не больше пяти штук.

Карточки лежат поверх страниц через ``place`` в «сырых» пикселях — их
позицию стопка пересчитывает сама, в том числе при смене масштаба.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

import customtkinter as ctk

from .. import theme
from .design import Btn, text

WIDTH = 400
MARGIN = 22
GAP = 8
LIMIT = 5
LIFETIME_MS = 5000
ERROR_LIFETIME_MS = 8000
SLIDE_PX = 16
SLIDE_MS = 200

_STRIPES = {"info": theme.AMBER, "ok": theme.OK, "warn": theme.WARN, "error": theme.ERR}
_ICONS = {"ok": "✓", "warn": "!", "error": "×"}


class _Toast(ctk.CTkFrame):
    def __init__(self, stack: "ToastStack", message: str, kind: str, action: str, command) -> None:
        super().__init__(
            stack.root,
            fg_color=theme.TOAST_BG,
            border_width=1,
            border_color=theme.LINE2,
            corner_radius=3,
            width=WIDTH,
        )
        self.stack = stack
        self.message = message
        self.kind = kind
        self._timer: str | None = None
        self.offset = 0.0  # сдвиг вниз при появлении, px

        color = _STRIPES.get(kind, theme.AMBER)
        self.grid_columnconfigure(1, weight=1)
        stripe = tk.Frame(self, bg=color, width=3, highlightthickness=0, bd=0)
        stripe.place(x=1, y=1, relheight=1, height=-2)

        icon = _ICONS.get(kind)
        if icon:
            text(self, icon, font=theme.sans_medium(14), color=color).grid(
                row=0, column=0, sticky="n", padx=(14, 0), pady=10
            )
        width = WIDTH - (34 if icon else 14) - 14
        if action:
            width -= 110
        self.label = text(self, message, font=theme.sans(13), color=theme.TXT, wrap=width)
        self.label.grid(row=0, column=1, sticky="w", padx=(8 if icon else 14, 14), pady=10)
        if action and command is not None:
            Btn(self, action, lambda: (command(), self.close()), size="sm").grid(
                row=0, column=2, sticky="e", padx=(0, 10), pady=6
            )

        for widget in (self, self.label):
            widget.bind("<Button-1>", lambda _e: self.close())
            widget.bind("<Enter>", lambda _e: self.pause())
            widget.bind("<Leave>", lambda _e: self.restart())

    @property
    def lifetime(self) -> int:
        return ERROR_LIFETIME_MS if self.kind == "error" else LIFETIME_MS

    def restart(self) -> None:
        self.pause()
        self._timer = self.after(self.lifetime, self.close)

    def pause(self) -> None:
        if self._timer is not None:
            try:
                self.after_cancel(self._timer)
            except tk.TclError:
                pass
            self._timer = None

    def close(self) -> None:
        self.pause()
        self.stack.remove(self)


class ToastStack:
    """Стопка уведомлений одного окна."""

    def __init__(self, root) -> None:
        self.root = root
        self.items: list[_Toast] = []
        # Configure на окне приходит и от каждого потомка — нужен только свой.
        root.bind("<Configure>", lambda e: self.layout() if e.widget is root else None, add="+")

    def show(
        self,
        message: str,
        kind: str = "info",
        *,
        action: str = "",
        command: Callable[[], None] | None = None,
    ) -> None:
        for item in self.items:
            if item.message == message:
                item.restart()
                return
        while len(self.items) >= LIMIT:
            self.remove(self.items[0])
        toast = _Toast(self, message, kind, action, command)
        toast.offset = SLIDE_PX
        self.items.append(toast)
        toast.restart()
        self.root.update_idletasks()
        self.layout()
        self._slide(toast, 0)

    def remove(self, toast: _Toast) -> None:
        if toast in self.items:
            self.items.remove(toast)
            toast.pause()
            toast.destroy()
            self.layout()

    def _slide(self, toast: _Toast, step: int) -> None:
        steps = max(1, SLIDE_MS // 25)
        if toast not in self.items:
            return
        progress = min(1.0, (step + 1) / steps)
        eased = 1 - (1 - progress) ** 3
        toast.offset = SLIDE_PX * (1 - eased)
        self.layout()
        if progress < 1.0:
            self.root.after(25, self._slide, toast, step + 1)

    def layout(self) -> None:
        """Раскладывает стопку снизу вверх: новые — внизу."""
        if not self.items:
            return
        scale = theme.widget_scale(self.root)
        try:
            root_height = self.root.winfo_height()
            root_width = self.root.winfo_width()
        except tk.TclError:
            return
        margin = round(MARGIN * scale)
        gap = round(GAP * scale)
        width = min(round(WIDTH * scale), max(120, root_width - 2 * margin))
        bottom = root_height - margin
        for toast in reversed(self.items):
            height = toast.winfo_reqheight()
            y = bottom - height + round(toast.offset * scale)
            tk.Frame.place(toast, x=margin, y=y, width=width)
            toast.lift()
            bottom -= height + gap
