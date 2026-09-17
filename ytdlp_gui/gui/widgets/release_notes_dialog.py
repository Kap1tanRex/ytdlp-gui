"""Окно «что нового»: релизы yt-dlp до того, как что-то скачано.

Новая версия приходит тегом и стеной Markdown, а окно оставляет от неё
то, по чему принимают решение: какая версия, когда вышла и что в ней
изменилось. Релизы идут сверху вниз, новые первыми.

Устроено как окно библиотек «Стемницы» (design-system §8.1): подвал с
версиями слева, «Закрыть» и основная кнопка справа, а над подвалом —
блок хода загрузки с янтарной полосой 4 px.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import customtkinter as ctk

from ...core.updates import NoteSection, ReleaseInfo
from .. import fmt, theme
from .design import Btn, Column, Para, ProgressBar, box, hline, sec_label, text
from .dialogs import Dialog
from .layout import autohide_scrollbar

DIALOG_SIZE = (680, 700)


class ReleaseCard(ctk.CTkFrame):
    """Один релиз: версия, дата и разделы описания под ними."""

    def __init__(self, master, release: ReleaseInfo, *, empty_text: str = "") -> None:
        super().__init__(master, fg_color="transparent", width=0, height=0)
        self.grid_columnconfigure(0, weight=1)

        head = box(self)
        head.grid(row=0, column=0, sticky="ew")
        head.grid_columnconfigure(1, weight=1)
        text(head, release.version_text, font=theme.sans_medium(17)).grid(row=0, column=0, sticky="w")
        details = fmt.join(
            release.date_text,
            "предварительная" if release.prerelease else "",
            f"файл {fmt.size(release.asset_size)}" if release.asset_size else "",
        )
        text(head, details, font=theme.mono(11), color=theme.FAINT).grid(
            row=0, column=1, sticky="w", padx=(12, 0), pady=(3, 0)
        )

        sections = release.sections()
        row = 1
        if sections:
            for section in sections:
                self._add_section(section, row)
                row += 1
        elif empty_text:
            Para(self, empty_text, font=theme.sans(13), color=theme.DIM).grid(
                row=row, column=0, sticky="ew", pady=(12, 0)
            )

    def _add_section(self, section: NoteSection, row: int) -> None:
        holder = Column(self)
        holder.grid(row=row, column=0, sticky="ew", pady=(16, 0))
        if section.title:
            holder.add(sec_label(holder, section.title), pady=(0, 8), sticky="w")
        for item in section.items:
            # Вложенные пункты сдвинуты и приглушены — иначе список второго
            # уровня читается как продолжение первого.
            holder.add(
                Para(
                    holder,
                    f"·  {item.text}",
                    font=theme.sans(12 if item.level else 13),
                    color=theme.DIM if item.level else theme.TXT,
                ),
                padx=(item.level * 18, 0),
                pady=(0, 4),
            )


class ReleaseNotesDialog(Dialog):
    """Само окно: релизы, ход загрузки, кнопка установки и переход к истории."""

    def __init__(
        self,
        master,
        releases: Sequence[ReleaseInfo],
        *,
        title: str = "Доступно обновление",
        subtitle: str = "",
        empty_text: str = "Описание изменений не опубликовано.",
        history_text: str = "История изменений",
        close_text: str = "Закрыть",
        on_download: Callable[[ReleaseInfo], None] | None = None,
        on_history: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master, title, subtitle=subtitle, size=DIALOG_SIZE, min_size=(520, 440))
        self._on_download = on_download
        self._releases: tuple[ReleaseInfo, ...] = ()
        self._empty_text = empty_text
        self._busy = False

        self.body = ctk.CTkScrollableFrame(
            self.content,
            fg_color=theme.BG2,
            corner_radius=0,
            scrollbar_button_color=theme.LINE2,
            scrollbar_button_hover_color=theme.DIM,
        )
        self.body.grid(row=0, column=0, sticky="nsew")
        self.body.grid_columnconfigure(0, weight=1)
        autohide_scrollbar(self.body)

        # Блок хода загрузки — над подвалом, как в окне библиотек «Стемницы».
        self.progress = box(self.content)
        self.progress.grid_columnconfigure(0, weight=1)
        self.progress_title = text(self.progress, "", font=theme.sans(13))
        self.progress_title.grid(row=0, column=0, sticky="w")
        self.progress_bar = ProgressBar(self.progress, height=4, color=theme.AMBER)
        self.progress_bar.grid(row=1, column=0, sticky="ew", pady=(8, 8))
        self.progress_detail = text(self.progress, "", font=theme.mono(11), color=theme.DIM)
        self.progress_detail.grid(row=2, column=0, sticky="w")

        self.set_info("github · yt-dlp/yt-dlp · sha-256")
        footer = box(self.footer)
        footer.grid(row=0, column=2, sticky="e")
        self.history_button = Btn(footer, history_text, on_history, kind="quiet")
        self.close_button = Btn(footer, close_text, self.destroy, kind="quiet")
        self.close_button.grid(row=0, column=1, padx=(8, 0))
        self.download_button = Btn(footer, "Скачать", self._download, kind="primary", size="md")
        self.download_button.grid(row=0, column=2, padx=(12, 0))
        self.set_history_visible(on_history is not None)

        self.set_releases(releases)

    def set_history_visible(self, visible: bool) -> None:
        """В окне истории кнопка «история» не нужна — мы уже в ней."""
        if visible:
            self.history_button.grid(row=0, column=0)
        else:
            self.history_button.grid_remove()

    # -- содержимое ----------------------------------------------------------
    def set_releases(self, releases: Sequence[ReleaseInfo]) -> None:
        """Заменяет показанное; кнопка загрузки ведёт на самый новый релиз."""
        for child in self.body.winfo_children():
            child.destroy()

        self._releases = tuple(releases)
        row = 0
        for index, release in enumerate(self._releases):
            if index:
                hline(self.body).grid(row=row, column=0, sticky="ew", pady=20)
                row += 1
            ReleaseCard(self.body, release, empty_text=self._empty_text).grid(
                row=row, column=0, sticky="ew", padx=(0, 12)
            )
            row += 1

        if not self._releases:
            text(self.body, "Список релизов пуст.", color=theme.DIM).grid(row=0, column=0, sticky="w")

        target = self._installable()
        label = "Скачать"
        if target is not None and target.asset_size:
            label = f"Скачать · {fmt.size(target.asset_size)}"
        if not self._busy:
            self.download_button.configure(text=label)
            self.download_button.set_enabled(target is not None)

    def _installable(self) -> ReleaseInfo | None:
        return next((release for release in self._releases if release.is_installable), None)

    # -- ход загрузки --------------------------------------------------------
    def _show_progress(self) -> None:
        if not self.progress.winfo_manager():
            self.progress.grid(row=1, column=0, sticky="ew", pady=(18, 0))

    def show_progress(self, done: int, total: int) -> None:
        self._show_progress()
        target = self._installable()
        name = target.asset_name if target is not None else "yt-dlp"
        self.progress_title.configure(
            text=fmt.join("Скачивание", name), text_color=theme.TXT
        )
        if total:
            self.progress_bar.set(done / total)
            self.progress_detail.configure(
                text=f"{fmt.size(done)} / {fmt.size(total)}", text_color=theme.DIM
            )
        else:
            self.progress_bar.start()
            self.progress_detail.configure(text=fmt.size(done), text_color=theme.DIM)

    def show_result(self, message: str, *, ok: bool = True) -> None:
        self._busy = False
        self._show_progress()
        self.progress_bar.stop()
        self.progress_bar.set_color(theme.OK if ok else theme.ERR)
        self.progress_bar.set(1.0 if ok else 0.0, animate=False)
        icon = "✓ " if ok else "× "
        self.progress_title.configure(text=icon + message, text_color=theme.OK if ok else theme.ERR)
        self.progress_detail.configure(
            text="" if ok else "Ничего не установлено — можно повторить.", text_color=theme.DIM
        )
        self.download_button.configure(text="Готово" if ok else "Повторить")
        if ok:
            self.download_button.configure(command=self.destroy)
        self.download_button.set_enabled(True)

    def _download(self) -> None:
        target = self._installable()
        if target is None or self._on_download is None:
            return
        self._busy = True
        self.download_button.configure(text="Скачиваю…")
        self.download_button.set_enabled(False)
        self._show_progress()
        self.progress_bar.set_color(theme.AMBER)
        self.progress_bar.reset()
        self.progress_bar.start()
        self.progress_title.configure(text="Подготовка загрузки…", text_color=theme.TXT)
        self.progress_detail.configure(text="")
        self._on_download(target)
