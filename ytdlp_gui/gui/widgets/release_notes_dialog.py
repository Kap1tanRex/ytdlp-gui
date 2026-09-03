"""Окно «что нового»: релизы yt-dlp до того, как что-то скачано.

Повторяет ``views/dialogs/release_notes_dialog.py`` из ZapretGUI: новая
версия приходит тегом и стеной Markdown, а окно оставляет от неё те три
вещи, по которым принимают решение, — какая версия, когда вышла и что в
ней изменилось. По карточке на релиз, новые сверху.

Кнопка «Скачать» не открывает браузер: загрузка и установка идут здесь
же, прогресс показывается на месте кнопок.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import customtkinter as ctk

from ...core.updates import NoteSection, ReleaseInfo
from .. import theme
from .design import Card, button, link_button, muted_label, primary_button, separator, title_label

BADGE_SIZE = 44
DIALOG_SIZE = (720, 720)


class ReleaseCard(ctk.CTkFrame):
    """Один релиз: значок, версия, дата и разделы описания под ними."""

    def __init__(self, master, release: ReleaseInfo, *, empty_text: str = "") -> None:
        super().__init__(master, fg_color="transparent")
        self.release = release
        self.grid_columnconfigure(0, weight=1)

        header = Card(self)
        header.configure(fg_color=theme.color("bg.elevated"))
        header.grid(row=0, column=0, sticky="ew")
        body = header.body
        # Card растягивает свою единственную колонку; здесь колонок две, и
        # тянуться должна правая — иначе значок уезжает в центр карточки.
        body.grid_columnconfigure(0, weight=0)
        body.grid_columnconfigure(1, weight=1)

        badge = ctk.CTkFrame(
            body,
            width=BADGE_SIZE,
            height=BADGE_SIZE,
            corner_radius=BADGE_SIZE // 2,
            fg_color=theme.mix("accent", "bg.elevated", 0.18),
        )
        badge.grid(row=0, column=0, rowspan=2, padx=(0, theme.GAP["lg"]))
        badge.grid_propagate(False)
        ctk.CTkLabel(
            badge,
            text="!",
            text_color=theme.color("accent"),
            font=theme.font("title", weight="bold"),
        ).place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(
            body,
            text=release.version_text,
            anchor="w",
            font=theme.font("title", weight="bold"),
        ).grid(row=0, column=1, sticky="ew")

        ctk.CTkLabel(
            body,
            text=release.date_text,
            anchor="w",
            text_color=theme.color("accent"),
            font=theme.font("small"),
        ).grid(row=1, column=1, sticky="ew")

        sections = release.sections()
        row = 1
        if sections:
            for section in sections:
                self._add_section(section, row)
                row += 1
        elif empty_text:
            muted_label(self, empty_text, wraplength=600).grid(
                row=row, column=0, sticky="ew", pady=(theme.GAP["md"], 0)
            )

    def _add_section(self, section: NoteSection, row: int) -> None:
        holder = ctk.CTkFrame(self, fg_color="transparent")
        holder.grid(row=row, column=0, sticky="ew", padx=theme.GAP["xs"], pady=(theme.GAP["md"], 0))
        holder.grid_columnconfigure(0, weight=1)

        line = 0
        if section.title:
            ctk.CTkLabel(
                holder,
                text=section.title,
                anchor="w",
                justify="left",
                wraplength=620,
                font=theme.font("base", weight="bold"),
            ).grid(row=line, column=0, sticky="ew", pady=(0, theme.GAP["xs"]))
            line += 1

        for item in section.items:
            # Вложенные пункты сдвигаем и приглушаем — иначе список
            # второго уровня читается как продолжение первого.
            label = ctk.CTkLabel(
                holder,
                text=f"•  {item.text}",
                anchor="w",
                justify="left",
                wraplength=600 - item.level * 24,
                text_color=theme.color("fg.secondary" if item.level else "fg.primary"),
                font=theme.font("small" if item.level else "base"),
            )
            label.grid(
                row=line, column=0, sticky="ew", padx=(theme.GAP["sm"] + item.level * 24, 0), pady=1
            )
            line += 1


class ReleaseNotesDialog(ctk.CTkToplevel):
    """Само окно: релизы, кнопка загрузки и переход к полной истории."""

    def __init__(
        self,
        master,
        releases: Sequence[ReleaseInfo],
        *,
        title: str = "Доступно обновление",
        subtitle: str = "",
        empty_text: str = "Описание изменений не опубликовано.",
        download_text: str = "↓  Скачать",
        history_text: str = "Просмотр истории изменений",
        close_text: str = "Закрыть",
        on_download: Callable[[ReleaseInfo], None] | None = None,
        on_history: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master)
        self.title(title)
        self.geometry(f"{DIALOG_SIZE[0]}x{DIALOG_SIZE[1]}")
        self.minsize(520, 420)
        self.configure(fg_color=theme.color("bg.window"))
        self.transient(master.winfo_toplevel())

        self._on_download = on_download
        self._releases: tuple[ReleaseInfo, ...] = ()
        self._empty_text = empty_text

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self.heading = title_label(self, title)
        self.heading.configure(font=theme.font("hero", weight="bold"), wraplength=640)
        self.heading.grid(
            row=0, column=0, sticky="ew", padx=theme.GAP["xl"], pady=(theme.GAP["xl"], 0)
        )

        self.subtitle = muted_label(self, subtitle, wraplength=640)
        self.subtitle.grid(row=1, column=0, sticky="ew", padx=theme.GAP["xl"], pady=(4, theme.GAP["md"]))

        self.body = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
        self.body.grid(row=2, column=0, sticky="nsew", padx=theme.GAP["xl"])
        self.body.grid_columnconfigure(0, weight=1)

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(
            row=3, column=0, sticky="ew", padx=theme.GAP["xl"], pady=(theme.GAP["md"], theme.GAP["lg"])
        )
        footer.grid_columnconfigure(0, weight=1)

        self.progress_label = muted_label(footer, "")
        self.progress_bar = ctk.CTkProgressBar(footer, height=8)
        self.progress_bar.set(0)

        self.download_button = primary_button(footer, download_text, self._download, height=42)
        self.download_button.grid(row=2, column=0, sticky="ew")

        self.history_button = button(footer, history_text, on_history, height=38)
        self.set_history_visible(on_history is not None)

        self.close_button = link_button(footer, close_text, self.destroy)
        self.close_button.grid(row=4, column=0, pady=(theme.GAP["sm"], 0))

        self.bind("<Escape>", lambda _e: self.destroy())
        self.after(120, self._raise)
        self.set_releases(releases)

    def set_history_visible(self, visible: bool) -> None:
        """В окне истории кнопка «показать историю» не нужна — мы уже в ней."""
        if visible:
            self.history_button.grid(row=3, column=0, sticky="ew", pady=(theme.GAP["sm"], 0))
        else:
            self.history_button.grid_remove()

    def _raise(self) -> None:
        try:
            self.lift()
            self.focus()
        except Exception:  # noqa: BLE001 - окно могли закрыть до срабатывания after()
            pass

    # -- содержимое ----------------------------------------------------------
    def set_releases(self, releases: Sequence[ReleaseInfo]) -> None:
        """Заменяет показанное; кнопка загрузки ведёт на самый новый релиз."""
        for child in self.body.winfo_children():
            child.destroy()

        self._releases = tuple(releases)
        row = 0
        for index, release in enumerate(self._releases):
            if index:
                separator(self.body).grid(
                    row=row, column=0, sticky="ew", pady=theme.GAP["lg"]
                )
                row += 1
            ReleaseCard(self.body, release, empty_text=self._empty_text).grid(
                row=row, column=0, sticky="ew"
            )
            row += 1

        if not self._releases:
            muted_label(self.body, "Список релизов пуст.").grid(row=0, column=0, sticky="w")

        installable = self._installable()
        self.download_button.configure(state="normal" if installable else "disabled")

    def _installable(self) -> ReleaseInfo | None:
        return next((release for release in self._releases if release.is_installable), None)

    # -- ход загрузки --------------------------------------------------------
    def show_progress(self, done: int, total: int) -> None:
        self._show_progress_widgets()
        if total:
            self.progress_bar.set(max(0.0, min(1.0, done / total)))
            self.progress_label.configure(
                text=f"Загрузка: {done / 1048576:.1f} / {total / 1048576:.1f} МБ"
            )
        else:
            self.progress_label.configure(text=f"Загрузка: {done / 1048576:.1f} МБ")

    def show_result(self, text: str, *, ok: bool = True) -> None:
        self._show_progress_widgets()
        self.progress_bar.set(1.0 if ok else 0.0)
        self.progress_bar.configure(
            progress_color=theme.color("state.ok" if ok else "state.error")
        )
        self.progress_label.configure(
            text=text, text_color=theme.color("state.ok" if ok else "state.error")
        )
        self.download_button.configure(state="disabled" if ok else "normal", text="↓  Скачать")

    def _show_progress_widgets(self) -> None:
        if not self.progress_label.winfo_ismapped():
            self.progress_label.grid(row=0, column=0, sticky="ew", pady=(0, theme.GAP["xs"]))
            self.progress_bar.grid(row=1, column=0, sticky="ew", pady=(0, theme.GAP["md"]))

    def _download(self) -> None:
        target = self._installable()
        if target is None or self._on_download is None:
            return
        self.download_button.configure(state="disabled", text="Загрузка…")
        self._show_progress_widgets()
        self.progress_label.configure(text="Загрузка…", text_color=theme.color("fg.secondary"))
        self.progress_bar.configure(progress_color=theme.color("accent"))
        self.progress_bar.set(0)
        self._on_download(target)
