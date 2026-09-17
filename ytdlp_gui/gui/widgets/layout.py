"""Страница вкладки и подвал (design-system §5.1, §6.2).

Страница — одна вертикальная прокрутка; содержимое не шире 1440 px и
стоит с полями ``max(0, (W − 1440) / 2) + 28``. Подвал идёт сразу за
содержимым, как у «Стемницы»: волосяная линия и две строки мелким
моноширинным шрифтом.
"""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from .. import theme
from .design import Para, box, hline, text

FOOTER_NOTE = (
    "Загрузку выполняет yt-dlp прямо на этом компьютере: программа выходит в сеть только "
    "за видео, которые вы добавили, и за обновлениями по вашему запросу. Телеметрии нет."
)


def page_margin(width_px: int, scale: float) -> int:
    """Боковое поле страницы в логических пикселях."""
    width = width_px / max(scale, 0.01)
    return int(max(0.0, (width - theme.MAX_WIDTH) / 2) + theme.PAGE_PAD)


def autohide_scrollbar(scrollable: ctk.CTkScrollableFrame) -> None:
    """Тонкая полоса прокрутки, видимая только когда есть что прокручивать (§9.19)."""
    scrollable._scrollbar.configure(width=10)

    def sync() -> None:
        try:
            first, last = scrollable._parent_canvas.yview()
        except tk.TclError:
            return
        needed = first > 0.0 or last < 1.0
        # winfo_manager, а не winfo_ismapped: пока CustomTkinter прячет новое
        # окно, «не показан» любой виджет, даже размещённый.
        mapped = bool(scrollable._scrollbar.winfo_manager())
        if needed and not mapped:
            scrollable._create_grid()
        elif not needed and mapped:
            scrollable._scrollbar.grid_remove()
            scrollable._parent_canvas.yview_moveto(0)

    def schedule(_event=None) -> None:
        scrollable.after_idle(sync)

    tk.Frame.bind(scrollable, "<Configure>", schedule, add="+")
    scrollable._parent_canvas.bind("<Configure>", schedule, add="+")


class Footer(ctk.CTkFrame):
    def __init__(self, master) -> None:
        super().__init__(master, fg_color="transparent", width=0, height=0)
        self.grid_columnconfigure(0, weight=1)
        hline(self).place(relx=0, rely=0, relwidth=1)
        self.note = Para(self, FOOTER_NOTE, font=theme.mono(11), color=theme.FAINT)
        self.note.grid(row=0, column=0, sticky="ew", padx=(theme.PAGE_PAD, 32), pady=(22, 26))
        self.versions = text(self, "", font=theme.mono(11), color=theme.FAINT, anchor="ne")
        self.versions.grid(row=0, column=1, sticky="ne", padx=(0, theme.PAGE_PAD), pady=(22, 26))

    def set_versions(self, value: str) -> None:
        self.versions.configure(text=theme.caps(value, 0.05))

    def set_margin(self, margin: int) -> None:
        self.note.grid(padx=(margin, 32))
        self.versions.grid(padx=(0, margin))


class ScrollPage(ctk.CTkScrollableFrame):
    """Прокручиваемая вкладка: содержимое кладут в :attr:`body`."""

    def __init__(self, master, *, max_width: int = theme.MAX_WIDTH) -> None:
        # Холст сразу получает размер окна: иначе первая раскладка идёт при
        # ширине по умолчанию (200 px) и тут же переделывается целиком.
        width, height = getattr(master.winfo_toplevel(), "initial_size", (200, 200))
        super().__init__(
            master,
            width=width,
            height=height,
            fg_color=theme.BG,
            corner_radius=0,
            scrollbar_fg_color=theme.BG,
            scrollbar_button_color=theme.LINE2,
            scrollbar_button_hover_color=theme.DIM,
        )
        self._max_width = max_width
        self._margin = theme.PAGE_PAD
        self._width = 0

        self.grid_columnconfigure(0, weight=1)
        self.body = box(self)
        self.body.grid(row=0, column=0, sticky="nsew", padx=theme.PAGE_PAD)
        self.body.grid_columnconfigure(0, weight=1)
        self.footer = Footer(self)
        self.footer.grid(row=1, column=0, sticky="ew", pady=(44, 0))

        self._parent_canvas.bind("<Configure>", self._on_resize, add="+")
        autohide_scrollbar(self)

    # -- ширина ------------------------------------------------------------
    def _on_resize(self, event) -> None:
        # При закрытии окна Tk присылает Configure уже разобранной странице.
        if not self.winfo_exists() or not self.body.winfo_exists():
            return
        scale = theme.widget_scale(self)
        margin = page_margin(event.width, scale)
        if margin != self._margin:
            self._margin = margin
            self.body.grid(padx=margin)
            self.footer.set_margin(margin)
        width = int(event.width / scale) - 2 * margin
        if width != self._width:
            self._width = width
            self.on_width(width)

    def on_width(self, width: int) -> None:
        """Ширина содержимого в логических пикселях — для адаптивной раскладки."""
