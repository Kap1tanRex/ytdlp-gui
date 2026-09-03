"""Диалоговые окна в оформлении приложения.

Все вспомогательные окна (справка, лог, ошибка задания, результат,
команда yt-dlp, диагностика) строятся одним и тем же способом: заголовок,
карточка с содержимым и строка кнопок внизу — как диалоги ZapretGUI.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import customtkinter as ctk

from .. import theme
from .design import Card, button as make_button, muted_label, primary_button, title_label


class Dialog(ctk.CTkToplevel):
    """Окно с заголовком, областью содержимого и строкой кнопок."""

    def __init__(
        self,
        master,
        title: str,
        *,
        subtitle: str = "",
        size: tuple[int, int] = (680, 460),
        min_size: tuple[int, int] | None = None,
    ) -> None:
        super().__init__(master)
        self.title(title)
        self.geometry(f"{size[0]}x{size[1]}")
        self.minsize(*(min_size or (min(size[0], 420), min(size[1], 260))))
        self.configure(fg_color=theme.color("bg.window"))
        self.transient(master.winfo_toplevel())

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self.heading = title_label(self, title)
        self.heading.grid(
            row=0, column=0, sticky="ew", padx=theme.GAP["xl"], pady=(theme.GAP["lg"], 0)
        )

        self.subtitle = muted_label(self, subtitle)
        self.subtitle.grid(row=1, column=0, sticky="ew", padx=theme.GAP["xl"], pady=(2, theme.GAP["md"]))

        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.grid(row=2, column=0, sticky="nsew", padx=theme.GAP["xl"])
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        self.footer = ctk.CTkFrame(self, fg_color="transparent")
        self.footer.grid(
            row=3, column=0, sticky="ew", padx=theme.GAP["xl"], pady=(theme.GAP["md"], theme.GAP["lg"])
        )
        self.footer.grid_columnconfigure(0, weight=1)

        self.bind("<Escape>", lambda _e: self.destroy())
        # CTkToplevel в первый момент может оказаться позади родителя.
        self.after(120, self._raise)

    def _raise(self) -> None:
        try:
            self.lift()
            self.focus()
        except Exception:  # noqa: BLE001 - окно могли закрыть до срабатывания after()
            pass

    # -- кнопки --------------------------------------------------------------
    def add_buttons(
        self,
        left: Sequence[tuple[str, Callable[[], None]]] = (),
        right: Sequence[tuple[str, Callable[[], None]]] = (),
        *,
        close_text: str = "Закрыть",
    ) -> None:
        left_frame = ctk.CTkFrame(self.footer, fg_color="transparent")
        left_frame.grid(row=0, column=0, sticky="w")
        for index, (text, command) in enumerate(left):
            make_button(left_frame, text, command).grid(
                row=0, column=index, padx=(0, theme.GAP["sm"])
            )

        right_frame = ctk.CTkFrame(self.footer, fg_color="transparent")
        right_frame.grid(row=0, column=1, sticky="e")
        for index, (text, command) in enumerate(right):
            make_button(right_frame, text, command).grid(
                row=0, column=index, padx=(theme.GAP["sm"], 0)
            )
        primary_button(right_frame, close_text, self.destroy).grid(
            row=0, column=len(right), padx=(theme.GAP["sm"], 0)
        )


def read_only_textbox(master, text: str, *, mono: bool = False, wrap: str = "word") -> ctk.CTkTextbox:
    box = ctk.CTkTextbox(
        master,
        wrap=wrap,
        font=theme.font("small", mono=mono),
        fg_color=theme.color("bg.elevated"),
        border_color=theme.color("border"),
        border_width=1,
        corner_radius=theme.RADIUS["sm"],
    )
    box.insert("1.0", text)
    box.configure(state="disabled")
    return box


def text_dialog(
    master,
    title: str,
    text: str,
    *,
    subtitle: str = "",
    mono: bool = False,
    wrap: str = "word",
    size: tuple[int, int] = (720, 480),
    left_buttons: Sequence[tuple[str, Callable[[], None]]] = (),
    right_buttons: Sequence[tuple[str, Callable[[], None]]] = (),
    close_text: str = "Закрыть",
    card_title: str = "",
) -> Dialog:
    """Диалог с одним текстовым блоком — самый частый случай."""
    dialog = Dialog(master, title, subtitle=subtitle, size=size)
    card = Card(dialog.content, card_title)
    card.grid(row=0, column=0, sticky="nsew")
    card.body.grid_rowconfigure(0, weight=1)
    read_only_textbox(card.body, text, mono=mono, wrap=wrap).grid(row=0, column=0, sticky="nsew")
    dialog.add_buttons(left_buttons, right_buttons, close_text=close_text)
    return dialog
