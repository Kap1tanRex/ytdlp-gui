"""Диалоговые окна (design-system §8).

Все окна устроены одинаково: заливка ``BG2``, капс-заголовок Unbounded
с разрядкой, пояснение, содержимое и подвал под волосяной линией —
слева служебная подпись, справа тихая «Закрыть» и, если есть, основная
кнопка. Esc закрывает окно.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import customtkinter as ctk

from .. import theme
from .design import Btn, Para, box, caps_text, hline

PAD = 28


class Dialog(ctk.CTkToplevel):
    """Окно с заголовком, областью содержимого и подвалом с кнопками."""

    def __init__(
        self,
        master,
        title: str,
        *,
        subtitle: str = "",
        size: tuple[int, int] = (640, 460),
        min_size: tuple[int, int] | None = None,
    ) -> None:
        super().__init__(master, fg_color=theme.BG2)
        self.title(title)
        self.minsize(*(min_size or (min(size[0], 440), min(size[1], 280))))
        self._place_over(master, size)
        self.transient(master.winfo_toplevel())
        theme.style_window(self)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self.heading = caps_text(
            self, title, font=theme.display_semi(16), tracking=0.16, color=theme.TXT
        )
        self.heading.grid(row=0, column=0, sticky="ew", padx=PAD, pady=(26, 0))
        self.subtitle = Para(self, subtitle, font=theme.sans(13), color=theme.DIM)
        self.subtitle.grid(row=1, column=0, sticky="ew", padx=PAD, pady=(8, 18))
        if not subtitle:
            self.subtitle.grid_remove()

        self.content = box(self)
        self.content.grid(row=2, column=0, sticky="nsew", padx=PAD)
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        hline(self).grid(row=3, column=0, sticky="ew", padx=PAD, pady=(18, 0))
        self.footer = box(self)
        self.footer.grid(row=4, column=0, sticky="ew", padx=PAD, pady=(16, 22))
        self.footer.grid_columnconfigure(1, weight=1)
        self.info = caps_text(self.footer, "", size=10, tracking=0.1)
        self.info.grid(row=0, column=0, sticky="w")

        self.bind("<Escape>", lambda _e: self.destroy())
        # CTkToplevel в первый момент может оказаться позади родителя.
        self.after(120, self._raise)

    def _place_over(self, master, size: tuple[int, int]) -> None:
        parent = master.winfo_toplevel()
        scale = theme.widget_scale(parent)
        try:
            x = parent.winfo_rootx() + (parent.winfo_width() - round(size[0] * scale)) // 2
            y = parent.winfo_rooty() + (parent.winfo_height() - round(size[1] * scale)) // 3
        except Exception:  # noqa: BLE001 - родитель ещё не показан
            self.geometry(f"{size[0]}x{size[1]}")
            return
        self.geometry(f"{size[0]}x{size[1]}+{max(0, x)}+{max(0, y)}")

    def _raise(self) -> None:
        try:
            self.lift()
            self.focus()
        except Exception:  # noqa: BLE001 - окно могли закрыть до срабатывания after()
            pass

    def set_heading(self, value: str) -> None:
        self.title(value)
        self.heading.configure(text=theme.caps(value, 0.16))

    def set_subtitle(self, value: str) -> None:
        self.subtitle.configure(text=value)
        if value:
            self.subtitle.grid()
        else:
            self.subtitle.grid_remove()

    def set_info(self, value: str) -> None:
        self.info.configure(text=theme.caps(value, 0.1))

    # -- кнопки --------------------------------------------------------------
    def add_buttons(
        self,
        left: Sequence[tuple[str, Callable[[], None]]] = (),
        right: Sequence[tuple[str, Callable[[], None]]] = (),
        *,
        close_text: str = "Закрыть",
        primary: tuple[str, Callable[[], None]] | None = None,
    ) -> None:
        """``left`` — тихие служебные кнопки; ``right`` — обычные перед «Закрыть»."""
        left_frame = box(self.footer)
        left_frame.grid(row=0, column=0, sticky="w")
        for index, (label, command) in enumerate(left):
            Btn(left_frame, label, command, kind="quiet", size="sm").grid(
                row=0, column=index, padx=(0 if index == 0 else 6, 0)
            )
        if left:
            self.info.grid_remove()

        right_frame = box(self.footer)
        right_frame.grid(row=0, column=2, sticky="e")
        column = 0
        for label, command in right:
            Btn(right_frame, label, command).grid(row=0, column=column, padx=(0, 12))
            column += 1
        Btn(right_frame, close_text, self.destroy, kind="quiet" if primary else "ghost").grid(
            row=0, column=column
        )
        if primary is not None:
            Btn(right_frame, primary[0], primary[1], kind="primary", size="md").grid(
                row=0, column=column + 1, padx=(12, 0)
            )


def read_only_textbox(master, value: str, *, mono: bool = False, wrap: str = "word") -> ctk.CTkTextbox:
    widget = ctk.CTkTextbox(
        master,
        wrap=wrap,
        font=theme.mono(12) if mono else theme.sans(13),
        fg_color=theme.PIT if mono else theme.BG2,
        text_color=theme.TXT if not mono else theme.DIM,
        border_width=1 if mono else 0,
        border_color=theme.LINE,
        border_spacing=10 if mono else 0,
        corner_radius=3,
        scrollbar_button_color=theme.LINE2,
        scrollbar_button_hover_color=theme.DIM,
    )
    widget.insert("1.0", value)
    widget.configure(state="disabled")
    return widget


def text_dialog(
    master,
    title: str,
    value: str,
    *,
    subtitle: str = "",
    mono: bool = False,
    wrap: str = "word",
    size: tuple[int, int] = (720, 480),
    left_buttons: Sequence[tuple[str, Callable[[], None]]] = (),
    right_buttons: Sequence[tuple[str, Callable[[], None]]] = (),
    close_text: str = "Закрыть",
    info: str = "",
) -> Dialog:
    """Диалог с одним текстовым блоком — самый частый случай."""
    dialog = Dialog(master, title, subtitle=subtitle, size=size)
    read_only_textbox(dialog.content, value, mono=mono, wrap=wrap).grid(
        row=0, column=0, sticky="nsew"
    )
    if info:
        dialog.set_info(info)
    dialog.add_buttons(left_buttons, right_buttons, close_text=close_text)
    return dialog
