"""Панель прогресса текущей загрузки.

Оформлена как карточка (см. :class:`ytdlp_gui.gui.widgets.design.Card`) и
показывается только тогда, когда есть о чём сообщить: во время загрузки,
постобработки и сразу после завершения. В простое панель убирается,
чтобы не занимать место пустой полосой.
"""

from __future__ import annotations

from collections.abc import Callable

import customtkinter as ctk

from ...core.models import ProgressInfo
from .. import theme
from .design import Card, danger_button, muted_label, set_severity


class ProgressPanel(Card):
    def __init__(self, master, on_cancel: Callable[[], None]) -> None:
        super().__init__(master)
        self.on_cancel = on_cancel
        self._visible = False

        body = self.body
        body.grid_columnconfigure(0, weight=1)

        self.title_label = ctk.CTkLabel(
            body, text="", anchor="w", font=theme.font("base", weight="bold")
        )
        self.title_label.grid(row=0, column=0, sticky="ew", padx=(0, theme.GAP["md"]))

        self.bar = ctk.CTkProgressBar(body, height=8)
        self.bar.set(0)
        self.bar.grid(row=1, column=0, sticky="ew", pady=(theme.GAP["sm"], theme.GAP["xs"]), padx=(0, theme.GAP["md"]))

        self.detail_label = muted_label(body, "")
        self.detail_label.grid(row=2, column=0, sticky="ew")

        self.cancel_button = danger_button(body, "Отмена", self._on_cancel, width=100)
        self.cancel_button.grid(row=0, column=1, rowspan=3, sticky="e")
        self.cancel_button.grid_remove()

    # -- видимость -----------------------------------------------------------
    def _show(self) -> None:
        if not self._visible:
            self.grid()
            self._visible = True

    def _hide(self) -> None:
        if self._visible:
            self.grid_remove()
            self._visible = False

    def _on_cancel(self) -> None:
        self.on_cancel()

    # -- состояния -----------------------------------------------------------
    def start(self, text: str) -> None:
        self.title_label.configure(text=text, text_color=theme.color("fg.primary"))
        self.detail_label.configure(text="")
        self.bar.configure(mode="determinate", progress_color=theme.color("accent"))
        self.bar.set(0)
        self.cancel_button.grid()
        self._show()

    def update_progress(self, info: ProgressInfo) -> None:
        self.bar.set(max(0.0, min(1.0, info.fraction)))
        self.detail_label.configure(text=info.human().replace("\n", "   •   "))

    def set_stage(self, text: str) -> None:
        self.title_label.configure(text=text)
        self.bar.configure(mode="indeterminate")
        self.bar.start()
        self._show()

    def finish(self, text: str) -> None:
        self.bar.configure(mode="determinate", progress_color=theme.color("state.ok"))
        self.bar.stop()
        self.bar.set(1.0)
        self.title_label.configure(text=text, text_color=theme.color("state.ok"))
        self.detail_label.configure(text="")
        self.cancel_button.grid_remove()
        self._show()

    def reset(self, text: str | None = None, *, severity: str = "info") -> None:
        self.bar.configure(mode="determinate", progress_color=theme.color("accent"))
        self.bar.stop()
        self.bar.set(0)
        self.title_label.configure(text=text or "")
        self.detail_label.configure(text="")
        self.cancel_button.grid_remove()
        if text:
            set_severity(self.title_label, severity)
            self._show()
        else:
            self.title_label.configure(text_color=theme.color("fg.primary"))
            self._hide()
