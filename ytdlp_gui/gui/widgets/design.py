"""Компоненты интерфейса в стиле «Стемницы» (design-system §9).

Каждый компонент берёт цвета и шрифты только из :mod:`..theme` и ведёт
себя, как описано в документе: наведение меняет одно свойство, основная
кнопка на экране одна, капс — только у служебных подписей, теней нет.

Из анимаций оставлены только те, что показывают реальный процесс
(прогресс, §11.4): прозрачности в Tk нет, а декоративное движение
«Стемница» и так не использует (§11.6).
"""

from __future__ import annotations

import math
import time
import tkinter as tk
import tkinter.font
from collections.abc import Callable, Sequence

import customtkinter as ctk

from .. import theme

# =============================================================================
# Текст
# =============================================================================


def text(
    master,
    value: str = "",
    *,
    font: ctk.CTkFont | None = None,
    color: str = theme.TXT,
    wrap: int = 0,
    anchor: str = "w",
    justify: str = "left",
    height: int = 0,
    **kwargs,
) -> ctk.CTkLabel:
    """Надпись без собственных полей: высота равна высоте строки."""
    return ctk.CTkLabel(
        master,
        text=value,
        font=font or theme.sans(13),
        text_color=color,
        wraplength=wrap,
        anchor=anchor,
        justify=justify,
        width=0,
        height=height,
        **kwargs,
    )


def caps_text(
    master,
    value: str,
    *,
    size: int = 11,
    tracking: float = 0.12,
    color: str = theme.FAINT,
    font: ctk.CTkFont | None = None,
    **kwargs,
) -> ctk.CTkLabel:
    """Служебная подпись: моноширинный капс с разрядкой (§4.3)."""
    return text(
        master, theme.caps(value, tracking), font=font or theme.mono(size), color=color, **kwargs
    )


def sec_label(master, value: str, **kwargs) -> ctk.CTkLabel:
    """Подпись раздела панели (§9.3)."""
    return caps_text(master, value, size=10, tracking=0.16, **kwargs)


def field_label(master, value: str, **kwargs) -> ctk.CTkLabel:
    """Подпись поля или группы сегментов."""
    return caps_text(master, value, size=10, tracking=0.14, **kwargs)


def set_caps(label: ctk.CTkLabel, value: str, tracking: float = 0.12) -> None:
    label.configure(text=theme.caps(value, tracking))


class _Elastic(ctk.CTkLabel):
    """Надпись, которая не диктует ширину своей колонке.

    Метка Tk запрашивает ширину своего текста, и эта ширина уходит вверх по
    сетке. Для переносимого или обрезаемого текста это петля: колонка
    подстраивается под текст, текст — под колонку, и раскладка качается.
    Поэтому внутренняя метка просит ширину в один символ и растягивается
    на всё отведённое место.
    """

    def _elastic_init(self) -> None:
        self._label.configure(width=1)
        self._create_grid()

    def _create_grid(self) -> None:
        super()._create_grid()
        if hasattr(self, "_label"):
            self._label.grid(sticky="nsew")
            self.grid_columnconfigure(0, weight=1)


class Para(_Elastic):
    """Абзац, который переносится по ширине своего места в сетке.

    ``max_width`` ограничивает строку (вступление главной — 505 px).
    Виджет нужно класть с ``sticky="ew"`` в колонку, ширину которой
    определяет не он сам.
    """

    def __init__(
        self,
        master,
        value: str = "",
        *,
        font: ctk.CTkFont | None = None,
        color: str = theme.DIM,
        max_width: int | None = None,
        justify: str = "left",
        **kwargs,
    ) -> None:
        super().__init__(
            master,
            text=value,
            font=font or theme.sans(12),
            text_color=color,
            anchor="w" if justify == "left" else "center",
            justify=justify,
            wraplength=max_width or 360,
            width=0,
            height=0,
            **kwargs,
        )
        self._elastic_init()
        self._max_width = max_width
        self._last_wrap = 0
        self._pending_width = 0
        self._wrap_job: str | None = None
        tk.Frame.bind(self, "<Configure>", self._on_configure, add="+")

    def _on_configure(self, event) -> None:
        # За один проход раскладки ширина может смениться несколько раз;
        # переносим один раз, когда проход закончится, — иначе каждая
        # промежуточная ширина запускает новый пересчёт всей страницы.
        self._pending_width = event.width
        if self._wrap_job is None:
            self._wrap_job = self.after_idle(self._rewrap)

    def _rewrap(self) -> None:
        self._wrap_job = None
        if not self.winfo_exists():
            return
        width = self._pending_width / theme.widget_scale(self)
        if self._max_width:
            width = min(width, self._max_width)
        width = max(40, int(width))
        if abs(width - self._last_wrap) > 2:
            self._last_wrap = width
            self.configure(wraplength=width)

    def destroy(self) -> None:
        if self._wrap_job is not None:
            self.after_cancel(self._wrap_job)
            self._wrap_job = None
        super().destroy()


class Line(_Elastic):
    """Однострочная надпись, обрезаемая многоточием по ширине места (§4.3).

    Полный текст хранится отдельно и возвращается, когда места хватает.
    """

    def __init__(
        self, master, value: str = "", *, font: ctk.CTkFont | None = None, color: str = theme.TXT, **kwargs
    ) -> None:
        self._line_font = font or theme.sans(13)
        super().__init__(
            master,
            text=value,
            font=self._line_font,
            text_color=color,
            anchor="w",
            justify="left",
            width=1,
            height=0,
            **kwargs,
        )
        self._elastic_init()
        self._full = value
        self._available = 0
        tk.Frame.bind(self, "<Configure>", self._on_configure, add="+")

    @property
    def full_text(self) -> str:
        return self._full

    def set(self, value: str, color: str | None = None) -> None:
        if color is not None:
            self.configure(text_color=color)
        if value != self._full:
            self._full = value
            self._fit()

    def _on_configure(self, event) -> None:
        if event.width != self._available:
            self._available = event.width
            self._fit()

    def _fit(self) -> None:
        width = self._available / theme.widget_scale(self)
        value = self._full
        measure = self._line_font.measure
        if width > 4 and measure(value) > width:
            low, high = 0, len(value)
            while low < high:
                middle = (low + high + 1) // 2
                if measure(value[:middle].rstrip() + "…") <= width:
                    low = middle
                else:
                    high = middle - 1
            value = value[:low].rstrip() + "…"
        if self.cget("text") != value:
            self.configure(text=value)


class Hero(tk.Canvas):
    """Заголовок главной (§4.2): Display, интерлиньяж ×1.1, слово-акцент янтарём.

    Рисуется на холсте: метка Tk берёт высоту строки из метрик шрифта, а у
    Unbounded она почти полтора кегля — строки разъезжаются.
    """

    CAP_HEIGHT = 0.75  # высота прописных Unbounded, доля кегля
    DESCENT = 0.27  # запас под выносные элементы (у, д)
    LEADING = 1.1

    def __init__(self, master, lines: Sequence[Sequence[tuple[str, str]]], *, size: int = 50) -> None:
        super().__init__(master, bg=surface_of(master), highlightthickness=0, bd=0, width=1, height=1)
        self._lines = lines
        self._size = size
        self._font = tkinter.font.Font(self, family=theme.family("display"), size=-size)
        ctk.ScalingTracker.add_widget(self._rescale, self)
        self._render()

    def set_size(self, size: int) -> None:
        if size != self._size:
            self._size = size
            self._render()

    def _rescale(self, _widget_scaling, _window_scaling) -> None:
        self._render()

    def destroy(self) -> None:
        ctk.ScalingTracker.remove_widget(self._rescale, self)
        super().destroy()

    def _render(self) -> None:
        px = max(1, round(self._size * theme.widget_scale(self)))
        self._font.configure(size=-px)
        self.delete("all")
        ascent = self._font.metrics("ascent")
        cap = round(px * self.CAP_HEIGHT) + 1
        step = round(px * self.LEADING)
        width = 0
        for index, line in enumerate(self._lines):
            x = 0
            y = cap + index * step - ascent  # якорь nw: базовая линия на ascent ниже
            for part, color in line:
                self.create_text(x, y, text=part, fill=color, font=self._font, anchor="nw")
                x += self._font.measure(part)
            width = max(width, x)
        height = cap + (len(self._lines) - 1) * step + round(px * self.DESCENT)
        self.configure(width=width, height=height)


def hline(master, color: str = theme.LINE) -> tk.Frame:
    """Волосяная линия: 1 физический пиксель при любом масштабе (§13)."""
    return tk.Frame(master, height=1, bg=color, highlightthickness=0, bd=0)


def vline(master, color: str = theme.LINE) -> tk.Frame:
    return tk.Frame(master, width=1, bg=color, highlightthickness=0, bd=0)


def box(master, **kwargs) -> ctk.CTkFrame:
    """Прозрачный контейнер без собственного размера.

    У CTkFrame размер по умолчанию 200 × 200, и пустой контейнер (ряд
    кнопок, который заполнится позже) иначе раздувает сетку.
    """
    kwargs.setdefault("fg_color", "transparent")
    kwargs.setdefault("width", 0)
    kwargs.setdefault("height", 0)
    return ctk.CTkFrame(master, **kwargs)


class Column(ctk.CTkFrame):
    """Прозрачная колонка: виджеты складываются сверху вниз."""

    def __init__(self, master, **kwargs) -> None:
        kwargs.setdefault("fg_color", "transparent")
        kwargs.setdefault("width", 0)
        kwargs.setdefault("height", 0)
        super().__init__(master, **kwargs)
        self.grid_columnconfigure(0, weight=1)
        self._next_row = 0

    def add(self, widget, *, pady=0, padx=0, sticky: str = "ew"):
        widget.grid(row=self._next_row, column=0, sticky=sticky, pady=pady, padx=padx)
        self._next_row += 1
        return widget

    @property
    def count(self) -> int:
        return self._next_row

    def clear(self) -> None:
        for child in self.winfo_children():
            child.destroy()
        self._next_row = 0

    def rewind(self) -> None:
        """Начать раскладку сначала, не удаляя виджеты (для перестановки строк)."""
        self._next_row = 0


def surface_of(widget) -> str:
    """Цвет, на котором лежит виджет (первый непрозрачный предок)."""
    current = widget
    while current is not None:
        try:
            color = current.cget("fg_color")
        except (ValueError, tk.TclError, AttributeError):
            color = None
        if isinstance(color, (list, tuple)):
            color = color[-1]
        if isinstance(color, str) and color and color != "transparent":
            return color
        if isinstance(current, ctk.CTkScrollableFrame):
            return theme.BG
        current = current.master
    return theme.BG


# =============================================================================
# Кнопки (§9.1)
# =============================================================================

#: Размер -> (высота, горизонтальное поле, кегль).
_BTN_SIZES = {"lg": (46, 22, 12), "md": (38, 22, 12), "sm": (30, 12, 11), "tool": (24, 0, 12)}


class Btn(ctk.CTkButton):
    """Кнопка: ``primary`` | ``ghost`` | ``danger`` | ``quiet`` | ``tool``.

    * основная — янтарная заливка, на экране одна;
    * обычная — рамка, при наведении рамка и текст янтарные;
    * опасная — красный текст, при наведении красная рамка;
    * тихая — без рамки, при наведении подложка;
    * ``tool`` — квадратная 24 × 24 для строк списка (§9.7).

    Текст переводится в капс сам; ширина по умолчанию — текст плюс поля.
    """

    def __init__(
        self,
        master,
        text: str = "",
        command: Callable[[], None] | None = None,
        *,
        kind: str = "ghost",
        size: str = "md",
        icon: str = "",
        width: int | None = None,
        **kwargs,
    ) -> None:
        if kind == "tool":
            size = "tool"
        height, self._pad, font_size = _BTN_SIZES[size]
        self._kind = kind
        self._icon = icon
        self._auto_width = width is None and kind != "tool"
        self._btn_font = theme.mono(font_size)
        label = self._compose(text)
        if kind == "tool":
            width = height
        super().__init__(
            master,
            text=label,
            command=command,
            width=self._measure(label) if width is None else width,
            height=height,
            corner_radius=3,
            border_width=1,
            border_spacing=0,
            font=self._btn_font,
            **kwargs,
        )
        self._surface = self._apply_appearance_mode(self._bg_color)
        self._colors = self._palette()
        self._enabled = self._state != tk.DISABLED
        self._restyle()
        self.bind("<Button-1>", self._on_press)

    # -- оформление ----------------------------------------------------------
    def _compose(self, value: str) -> str:
        if self._kind == "tool":
            return value
        label = theme.caps(value, 0.12)
        return f"{self._icon} {label}" if self._icon else label

    def _measure(self, label: str) -> int:
        return self._btn_font.measure(label) + 2 * self._pad + 2

    def _palette(self) -> dict[str, str]:
        s = self._surface
        kind = self._kind
        if kind == "primary":
            off = theme.mix(theme.BG2, theme.AMBER, 0.42)
            return {
                "fill": theme.AMBER, "border": theme.AMBER, "text": theme.ON_AMBER,
                "hover_fill": theme.AMBER2, "hover_border": theme.AMBER2, "hover_text": theme.ON_AMBER,
                "press": theme.AMBER_DEEP,
                "off_fill": off, "off_border": off, "off_text": theme.mix(off, theme.ON_AMBER, 0.75),
            }
        if kind == "danger":
            return {
                "fill": s, "border": s, "text": theme.ERR,
                "hover_fill": s, "hover_border": theme.ERR, "hover_text": theme.ERR,
                "press": theme.ERR_BG,
                "off_fill": s, "off_border": s, "off_text": theme.mix(s, theme.ERR, 0.4),
            }
        if kind == "quiet":
            return {
                "fill": s, "border": s, "text": theme.DIM,
                "hover_fill": theme.mix(s, theme.BG3, 0.7), "hover_border": theme.mix(s, theme.BG3, 0.7),
                "hover_text": theme.TXT,
                "press": theme.mix(s, theme.BG3, 0.3),
                "off_fill": s, "off_border": s, "off_text": theme.FAINT,
            }
        if kind == "tool":
            return {
                "fill": s, "border": theme.LINE2, "text": theme.DIM,
                "hover_fill": s, "hover_border": theme.DIM, "hover_text": theme.TXT,
                "press": theme.BG3,
                "off_fill": s, "off_border": theme.mix(s, theme.LINE2, 0.6),
                "off_text": theme.mix(s, theme.DIM, 0.4),
            }
        return {  # ghost
            "fill": s, "border": theme.LINE2, "text": theme.TXT,
            "hover_fill": s, "hover_border": theme.AMBER, "hover_text": theme.AMBER,
            "press": theme.BG3,
            "off_fill": s, "off_border": theme.mix(s, theme.LINE2, 0.6),
            "off_text": theme.mix(s, theme.TXT, 0.4),
        }

    def _restyle(self) -> None:
        c = self._colors
        on = self._enabled
        super().configure(
            fg_color=c["fill"] if on else c["off_fill"],
            hover_color=c["hover_fill"],
            border_color=c["border"] if on else c["off_border"],
            text_color=c["text"],
            text_color_disabled=c["off_text"],
        )

    def _paint(self, fill: str, border: str, fg: str) -> None:
        self._canvas.itemconfig("inner_parts", fill=fill, outline=fill)
        self._canvas.itemconfig("border_parts", fill=border, outline=border)
        if self._text_label is not None:
            self._text_label.configure(bg=fill, fg=fg)

    # -- состояния мыши ------------------------------------------------------
    def _on_enter(self, event=None) -> None:
        self._mouse_inside = True
        if self._state == tk.NORMAL:
            c = self._colors
            self._paint(c["hover_fill"], c["hover_border"], c["hover_text"])

    def _on_leave(self, event=None) -> None:
        self._mouse_inside = False
        self._click_animation_running = False
        c = self._colors
        if self._state == tk.NORMAL:
            self._paint(c["fill"], c["border"], c["text"])
        else:
            self._paint(c["off_fill"], c["off_border"], c["off_text"])

    def _on_press(self, _event=None) -> None:
        if self._state == tk.NORMAL:
            c = self._colors
            self._paint(c["press"], c["hover_border"], c["hover_text"])

    def _on_release(self, event=None) -> None:
        # Без «анимации щелчка» CustomTkinter: её отложенный вызов падает,
        # если команда кнопки уничтожила саму кнопку (строка списка, уведомление).
        if self._mouse_inside and self._state != tk.DISABLED:
            self._on_enter()
            if self._command is not None:
                self._command()

    # -- настройка -----------------------------------------------------------
    def configure(self, require_redraw: bool = False, **kwargs) -> None:
        if "text" in kwargs:
            label = self._compose(kwargs.pop("text"))
            kwargs["text"] = label
            if self._auto_width:
                kwargs.setdefault("width", self._measure(label))
        state = kwargs.get("state")
        new_surface = "bg_color" in kwargs
        super().configure(require_redraw=require_redraw, **kwargs)
        if not hasattr(self, "_colors"):
            return
        if new_surface:
            # Подложка сменилась (строка списка выделена) — пересчитать палитру.
            self._surface = self._apply_appearance_mode(self._bg_color)
            self._colors = self._palette()
        if state is not None:
            self._enabled = state != tk.DISABLED
        if new_surface or state is not None:
            self._restyle()

    config = configure

    def set_enabled(self, enabled: bool) -> None:
        if enabled != self._enabled:
            self.configure(state=tk.NORMAL if enabled else tk.DISABLED)


# =============================================================================
# Сегменты (§9.2)
# =============================================================================


class _SegCell(ctk.CTkButton):
    def __init__(self, master, title: str, *, font, height: int, radius: int, surface: str, command) -> None:
        super().__init__(
            master,
            text=theme.caps(title, 0.05),
            font=font,
            command=command,
            width=1,
            height=height,
            corner_radius=radius,
            border_width=0,
            border_spacing=0,
            fg_color=surface,
            hover=False,
            text_color=theme.DIM,
            text_color_disabled=theme.mix(surface, theme.FAINT, 0.6),
        )
        self._surface = surface
        self.selected = False

    def _on_enter(self, event=None) -> None:
        self._mouse_inside = True
        if self._state == tk.NORMAL and not self.selected and self._text_label is not None:
            self._text_label.configure(fg=theme.TXT)

    def _on_leave(self, event=None) -> None:
        self._mouse_inside = False
        self._click_animation_running = False
        if self._state == tk.NORMAL and not self.selected and self._text_label is not None:
            self._text_label.configure(fg=theme.DIM)

    def set_selected(self, selected: bool) -> None:
        self.selected = selected
        self.configure(
            fg_color=theme.BG3 if selected else self._surface,
            text_color=theme.AMBER if selected else theme.DIM,
        )


class Seg(ctk.CTkFrame):
    """Сегментный переключатель: рамка, ячейки поровну, выбранная — янтарём."""

    def __init__(
        self,
        master,
        options: Sequence[tuple[str, str]],
        *,
        value: str | None = None,
        command: Callable[[str], None] | None = None,
        height: int = 36,
        width: int | None = None,
    ) -> None:
        super().__init__(
            master,
            fg_color="transparent",
            border_width=1,
            border_color=theme.LINE2,
            corner_radius=3,
            height=height,
            width=width or 1,
        )
        self._command = command
        self._value: str | None = None
        self._cells: dict[str, _SegCell] = {}
        surface = surface_of(master)
        font = theme.mono(11 if height >= 30 else 10)
        count = len(options)
        column = 0
        for index, (key, title) in enumerate(options):
            if index:
                vline(self, theme.LINE2).grid(row=0, column=column, sticky="ns", pady=1)
                column += 1
            edge = index in (0, count - 1)
            cell = _SegCell(
                self,
                title,
                font=font,
                height=height - 2,
                radius=2 if edge else 0,
                surface=surface,
                command=lambda k=key: self._click(k),
            )
            cell.grid(
                row=0,
                column=column,
                sticky="nsew",
                padx=(1 if index == 0 else 0, 1 if index == count - 1 else 0),
                pady=1,
            )
            self.grid_columnconfigure(column, weight=1, uniform="cells")
            self._cells[key] = cell
            column += 1
        if width:
            self.grid_propagate(False)
            self.grid_rowconfigure(0, weight=1)
        if value is not None:
            self.set(value)

    def _click(self, key: str) -> None:
        if key == self._value:
            return
        self.set(key)
        if self._command is not None:
            self._command(key)

    def get(self) -> str | None:
        return self._value

    def set(self, key: str | None) -> None:
        self._value = key if key in self._cells else None
        for cell_key, cell in self._cells.items():
            if cell.selected != (cell_key == self._value):
                cell.set_selected(cell_key == self._value)

    def set_enabled(self, key: str, enabled: bool) -> None:
        cell = self._cells.get(key)
        if cell is not None:
            cell.configure(state=tk.NORMAL if enabled else tk.DISABLED)

    def options(self) -> list[str]:
        return list(self._cells)


# =============================================================================
# Чип, флажок, тумблер, поля
# =============================================================================

LED_COLORS = {"on": theme.AMBER, "off": theme.FAINT, "warn": theme.WARN, "error": theme.ERR}


class Chip(ctk.CTkFrame):
    """Чип шапки (§9.4): рамка, светодиод и капс-подпись.

    С ``command`` чип кликабелен: при наведении рамка становится янтарной.
    """

    def __init__(self, master, value: str = "", *, led: str | None = None, command=None) -> None:
        super().__init__(
            master, fg_color="transparent", border_width=1, border_color=theme.LINE2, corner_radius=3
        )
        self._command = command
        self._dot = ctk.CTkFrame(self, width=6, height=6, corner_radius=3, fg_color=theme.FAINT)
        self._label = caps_text(self, "", size=11, tracking=0.09, color=theme.DIM, height=24)
        self._label.grid(row=0, column=1, pady=1)
        self.set(value, led)
        for widget in (self, self._label, self._dot):
            widget.bind("<Button-1>", self._click)
            widget.bind("<Enter>", self._hover_in)
            widget.bind("<Leave>", self._hover_out)

    def set(self, value: str, led: str | None = None, command=...) -> None:
        if command is not ...:
            self._command = command
        set_caps(self._label, value, 0.09)
        if led is None:
            self._dot.grid_remove()
            self._label.grid(padx=(11, 11))
        else:
            self._dot.configure(fg_color=LED_COLORS.get(led, theme.FAINT))
            self._dot.grid(row=0, column=0, padx=(11, 0), pady=1)
            self._label.grid(padx=(7, 11))
        cursor = "hand2" if self._command else ""
        self._label.configure(cursor=cursor)
        if not self._command:
            self.configure(border_color=theme.LINE2)

    def _click(self, _event=None) -> None:
        if self._command is not None:
            self._command()

    def _hover_in(self, _event=None) -> None:
        if self._command is not None:
            self.configure(border_color=theme.AMBER)

    def _hover_out(self, _event=None) -> None:
        # Leave приходит и при переходе на дочерний виджет — проверяем курсор.
        self.after(20, self._check_pointer)

    def _check_pointer(self) -> None:
        try:
            x, y = self.winfo_pointerxy()
            inside = (
                self.winfo_rootx() <= x < self.winfo_rootx() + self.winfo_width()
                and self.winfo_rooty() <= y < self.winfo_rooty() + self.winfo_height()
            )
        except tk.TclError:
            return
        if not inside:
            self.configure(border_color=theme.LINE2)


def check(master, value: str, command=None, *, checked: bool = False, **kwargs) -> ctk.CTkCheckBox:
    """Флажок 14 × 14 (§9.5)."""
    box = ctk.CTkCheckBox(
        master,
        text=value,
        command=command,
        checkbox_width=14,
        checkbox_height=14,
        corner_radius=2,
        border_width=1,
        width=0,
        height=20,
        hover=False,
        font=theme.sans(13),
        **kwargs,
    )
    if checked:
        box.select()
    return box


def toggle(master, value: str, command=None, *, checked: bool = False, **kwargs) -> ctk.CTkSwitch:
    """Тумблер 36 × 20 с ручкой ⌀16 (§9.6)."""
    switch = ctk.CTkSwitch(
        master,
        text=value,
        command=command,
        switch_width=36,
        switch_height=20,
        width=0,
        height=24,
        font=theme.sans(14),
        **kwargs,
    )
    if checked:
        switch.select()
    return switch


class Field(ctk.CTkEntry):
    """Поле ввода (§9.18): моноширинный текст, рамка янтарная при наведении и в фокусе."""

    def __init__(self, master, *, height: int = 32, font_size: int = 12, **kwargs) -> None:
        super().__init__(
            master,
            height=height,
            font=theme.mono(font_size),
            corner_radius=3,
            border_width=1,
            fg_color=theme.BG,
            border_color=theme.LINE2,
            text_color=theme.TXT,
            placeholder_text_color=theme.FAINT,
            **kwargs,
        )
        self._hovered = False
        self._focused = False
        self.bind("<Enter>", lambda _e: self._set_flag(hovered=True))
        self.bind("<Leave>", lambda _e: self._set_flag(hovered=False))
        self.bind("<FocusIn>", lambda _e: self._set_flag(focused=True))
        self.bind("<FocusOut>", lambda _e: self._set_flag(focused=False))

    def _draw(self, no_color_updates: bool = False) -> None:
        super()._draw(no_color_updates)
        # CustomTkinter при каждой перерисовке красит курсор цветом текста.
        self._entry.configure(
            insertbackground=theme.AMBER,
            insertwidth=2,
            selectbackground=theme.AMBER,
            selectforeground=theme.ON_AMBER,
        )

    def _set_flag(self, *, hovered: bool | None = None, focused: bool | None = None) -> None:
        if hovered is not None:
            self._hovered = hovered
        if focused is not None:
            self._focused = focused
        active = (self._hovered or self._focused) and self.cget("state") != tk.DISABLED
        self.configure(border_color=theme.AMBER if active else theme.LINE2)

    def set_text(self, value: str) -> None:
        state = self.cget("state")
        if state == tk.DISABLED:
            self.configure(state=tk.NORMAL)
        self.delete(0, "end")
        if value:
            self.insert(0, value)
        elif not self._has_focus():
            # CustomTkinter до первого ухода фокуса считает поле «в фокусе»
            # и после очистки не возвращает подсказку сам.
            self._activate_placeholder()
        if state == tk.DISABLED:
            self.configure(state=tk.DISABLED)

    def _has_focus(self) -> bool:
        try:
            return self.focus_get() is self._entry
        except (KeyError, tk.TclError):
            return False

    def set_enabled(self, enabled: bool) -> None:
        self.configure(
            state=tk.NORMAL if enabled else tk.DISABLED,
            text_color=theme.TXT if enabled else theme.FAINT,
        )


class Dropdown(ctk.CTkFrame):
    """Выпадающий список в рамке поля ввода — для длинных перечней (форматы, браузеры)."""

    def __init__(
        self,
        master,
        values: Sequence[str],
        *,
        command: Callable[[str], None] | None = None,
        height: int = 32,
        width: int = 200,
    ) -> None:
        super().__init__(
            master,
            fg_color=theme.BG,
            border_width=1,
            border_color=theme.LINE2,
            corner_radius=3,
            height=height,
            width=width,
        )
        self.grid_columnconfigure(0, weight=1)
        self.menu = ctk.CTkOptionMenu(
            self,
            values=list(values) or [""],
            command=command,
            height=height - 2,
            width=max(40, width - 2),
            corner_radius=2,
            fg_color=theme.BG,
            button_color=theme.BG,
            button_hover_color=theme.BG,
            text_color=theme.TXT,
            text_color_disabled=theme.FAINT,
            font=theme.mono(12),
            dropdown_font=theme.sans(13),
            dropdown_fg_color=theme.BG2,
            dropdown_hover_color=theme.BG3,
            dropdown_text_color=theme.TXT,
            dynamic_resizing=False,
            anchor="w",
        )
        self.menu.grid(row=0, column=0, sticky="ew", padx=1, pady=1)
        for widget in (self, self.menu):
            widget.bind("<Enter>", lambda _e: self._hover(True))
            widget.bind("<Leave>", lambda _e: self._hover(False))

    def _hover(self, inside: bool) -> None:
        active = inside and self.menu.cget("state") != tk.DISABLED
        self.configure(border_color=theme.AMBER if active else theme.LINE2)

    def get(self) -> str:
        return self.menu.get()

    def set(self, value: str) -> None:
        self.menu.set(value)

    def set_values(self, values: Sequence[str], selected: str | None = None) -> None:
        values = list(values) or [""]
        self.menu.configure(values=values)
        self.menu.set(selected if selected is not None else values[0])

    def set_enabled(self, enabled: bool) -> None:
        self.menu.configure(state=tk.NORMAL if enabled else tk.DISABLED)


class Panel(ctk.CTkFrame):
    """Приподнятая плоскость (§7.1): BG2, волосяная рамка, радиус 5."""

    def __init__(self, master, **kwargs) -> None:
        kwargs.setdefault("fg_color", theme.BG2)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", theme.LINE)
        kwargs.setdefault("corner_radius", 5)
        super().__init__(master, **kwargs)
        self.grid_columnconfigure(0, weight=1)


class Notice(ctk.CTkFrame):
    """Плашка-уведомление в панели (§9.16): тонированная заливка и кнопка справа."""

    def __init__(
        self,
        master,
        value: str,
        *,
        color: str = theme.ERR,
        action: str = "",
        command: Callable[[], None] | None = None,
        primary: bool = False,
    ) -> None:
        surface = surface_of(master)
        super().__init__(
            master,
            fg_color=theme.mix(theme.BG, color, 0.07),
            border_width=1,
            border_color=theme.mix(surface, color, 0.45),
            corner_radius=3,
        )
        self.grid_columnconfigure(0, weight=1)
        self.label = Para(self, value, font=theme.sans(12), color=theme.TXT)
        self.label.grid(row=0, column=0, sticky="ew", padx=12, pady=11)
        self.button: Btn | None = None
        if action:
            self.button = Btn(
                self, action, command, kind="primary" if primary else "ghost", size="sm"
            )
            self.button.grid(row=0, column=1, padx=(0, 12), pady=11)

    def set_text(self, value: str) -> None:
        self.label.configure(text=value)


# =============================================================================
# Сворачиваемый раздел (§9.14)
# =============================================================================


class _Chevron(tk.Canvas):
    SIZE = 10

    def __init__(self, master, *, bg: str) -> None:
        self._scale = theme.widget_scale(master)
        side = round(self.SIZE * self._scale)
        super().__init__(master, width=side, height=side, bg=bg, highlightthickness=0, bd=0)
        self._open = False
        self._color = theme.FAINT
        self._draw()
        ctk.ScalingTracker.add_widget(self._rescale, self)

    def _rescale(self, new_widget_scaling, _new_window_scaling) -> None:
        self._scale = theme.widget_scale(self.master)
        side = round(self.SIZE * self._scale)
        self.configure(width=side, height=side)
        self._draw()

    def destroy(self) -> None:
        ctk.ScalingTracker.remove_widget(self._rescale, self)
        super().destroy()

    def _draw(self) -> None:
        self.delete("all")
        s = self._scale
        c = 5 * s
        if self._open:  # «›», повёрнутый на 90°
            points = (c - 3.5 * s, c - 1.8 * s, c, c + 1.8 * s, c + 3.5 * s, c - 1.8 * s)
        else:
            points = (c - 1.8 * s, c - 3.5 * s, c + 1.8 * s, c, c - 1.8 * s, c + 3.5 * s)
        self.create_line(*points, fill=self._color, width=max(1.0, 1.3 * s), capstyle="round")

    def set(self, opened: bool, color: str) -> None:
        self._open = opened
        self._color = color
        self._draw()


class Fold(ctk.CTkFrame):
    """Сворачиваемый раздел: капс-заголовок, сводка справа и шеврон.

    Содержимое кладут в :attr:`body`. Сводка при раскрытии гаснет до 40 %.
    """

    def __init__(
        self,
        master,
        title: str,
        *,
        summary: str = "",
        opened: bool = False,
        on_toggle: Callable[[bool], None] | None = None,
    ) -> None:
        super().__init__(master, fg_color="transparent", width=0, height=0)
        self.grid_columnconfigure(0, weight=1)
        self._surface = surface_of(master)
        self._on_toggle = on_toggle
        self._hovered = False

        self.header = box(self, cursor="hand2")
        self.header.grid(row=0, column=0, sticky="ew")
        self.header.grid_columnconfigure(1, weight=1)
        self._title = caps_text(self.header, title, size=10, tracking=0.16, cursor="hand2")
        self._title.grid(row=0, column=0, sticky="w")
        self._summary = text(
            self.header, summary, font=theme.mono(11), color=theme.DIM, anchor="e", cursor="hand2"
        )
        self._summary.grid(row=0, column=1, sticky="e", padx=(12, 10))
        self._chevron = _Chevron(self.header, bg=self._surface)
        self._chevron.grid(row=0, column=2, sticky="e")

        for widget in (self.header, self._title, self._summary, self._chevron):
            widget.bind("<Button-1>", lambda _e: self.toggle())
            widget.bind("<Enter>", lambda _e: self._hover(True))
            widget.bind("<Leave>", lambda _e: self._hover(False))

        self.body = box(self)
        self.body.grid_columnconfigure(0, weight=1)
        self.opened = not opened
        self.set_open(opened)

    def _hover(self, inside: bool) -> None:
        self._hovered = inside
        self._paint()

    def _paint(self) -> None:
        self._title.configure(text_color=theme.DIM if self._hovered else theme.FAINT)
        self._summary.configure(
            text_color=theme.mix(self._surface, theme.DIM, 0.4) if self.opened else theme.DIM
        )
        self._chevron.set(self.opened, theme.DIM if self._hovered else theme.FAINT)

    def toggle(self) -> None:
        self.set_open(not self.opened)
        if self._on_toggle is not None:
            self._on_toggle(self.opened)

    def set_open(self, opened: bool) -> None:
        if opened == self.opened:
            return
        self.opened = opened
        if opened:
            self.body.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        else:
            self.body.grid_remove()
        self._paint()

    def set_summary(self, value: str) -> None:
        self._summary.configure(text=value)


# =============================================================================
# Прогресс (§9.11)
# =============================================================================


def _loop_ease(t: float) -> float:
    """Приближение cubic-bezier(.4, 0, .6, 1) — кривая ``loop``."""
    return t * t * (3 - 2 * t)


class ProgressBar(ctk.CTkFrame):
    """Полоса прогресса без скругления.

    Определённый режим ведёт ширину **линейно** от прошлого значения к
    новому за время между отчётами (0.05…1 с) и не забегает вперёд.
    Неопределённый — четверть ширины, цикл 1.6 с.
    """

    FPS_DELAY = 33

    def __init__(
        self, master, *, height: int = 8, color: str = theme.DIM, trough: str = theme.BG3
    ) -> None:
        super().__init__(master, height=height, corner_radius=0, fg_color=trough)
        self._fill = tk.Frame(self, bg=color, highlightthickness=0, bd=0)
        self._value = 0.0
        self._from = 0.0
        self._to = 0.0
        self._t0 = 0.0
        self._duration = 0.0
        self._last_report: float | None = None
        self._job: str | None = None
        self._indeterminate = False

    def set_color(self, color: str) -> None:
        self._fill.configure(bg=color)

    def set(self, fraction: float, *, animate: bool = True) -> None:
        fraction = max(0.0, min(1.0, float(fraction)))
        now = time.monotonic()
        if self._indeterminate:
            self.stop()
        if not animate or self._last_report is None or fraction <= self._value:
            self._cancel()
            self._value = self._to = fraction
            self._place_fill(fraction)
        else:
            self._from = self._value
            self._to = fraction
            self._t0 = now
            self._duration = max(0.05, min(1.0, now - self._last_report))
            if self._job is None:
                self._tick()
        self._last_report = now

    def reset(self) -> None:
        self.stop()
        self._last_report = None
        self.set(0.0, animate=False)

    def _tick(self) -> None:
        progress = min(1.0, (time.monotonic() - self._t0) / self._duration)
        self._value = self._from + (self._to - self._from) * progress
        self._place_fill(self._value)
        self._job = self.after(self.FPS_DELAY, self._tick) if progress < 1.0 else None

    def _cancel(self) -> None:
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None

    def _place_fill(self, value: float) -> None:
        if value <= 0:
            self._fill.place_forget()
        else:
            self._fill.place(x=0, y=0, relx=0, relheight=1, relwidth=value)

    # -- неопределённый режим ----------------------------------------------
    def start(self) -> None:
        if self._indeterminate:
            return
        self._cancel()
        self._indeterminate = True
        self._t0 = time.monotonic()
        self._spin()

    def stop(self) -> None:
        if not self._indeterminate:
            return
        self._indeterminate = False
        self._cancel()
        self._place_fill(self._value)

    def _spin(self) -> None:
        phase = ((time.monotonic() - self._t0) / 1.6) % 1.0
        self._fill.place(x=0, y=0, relheight=1, relwidth=0.25, relx=-0.25 + 1.25 * _loop_ease(phase))
        self._job = self.after(self.FPS_DELAY, self._spin)

    def destroy(self) -> None:
        self._cancel()
        super().destroy()


# =============================================================================
# Пунктирная зона (§9.17)
# =============================================================================


class DashedBox(ctk.CTkFrame):
    """Пустое состояние: рамка, пунктир внутри и текст по центру."""

    def __init__(self, master, value: str, *, height: int = 240, outer: bool = True) -> None:
        surface = surface_of(master)
        super().__init__(
            master,
            height=height,
            corner_radius=5 if outer else 3,
            border_width=1 if outer else 0,
            border_color=theme.LINE,
            fg_color=surface,
        )
        self.grid_propagate(False)
        self._outer = outer
        self._color = theme.LINE2
        self._drawn: tuple[int, int, str] | None = None
        self._redraw_job: str | None = None
        self._dash_canvas = tk.Canvas(self, bg=surface, highlightthickness=0, bd=0)
        self._dash_canvas.place(x=3, y=3, relwidth=1, relheight=1, width=-6, height=-6)
        self._dash_canvas.bind("<Configure>", lambda _e: self._schedule_redraw())
        self.label = text(
            self, value, font=theme.sans(15), color=theme.DIM, justify="center", anchor="center"
        )
        self.label.place(relx=0.5, rely=0.5, anchor="center")

    def set_text(self, value: str) -> None:
        self.label.configure(text=value)

    def set_active(self, active: bool) -> None:
        self._color = theme.AMBER if active else theme.LINE2
        self._schedule_redraw()

    def _schedule_redraw(self) -> None:
        # Пунктир — сотни отрезков: рисуем один раз после раскладки, а не на
        # каждый промежуточный размер.
        if self._redraw_job is None:
            self._redraw_job = self.after_idle(self._redraw)

    def destroy(self) -> None:
        if self._redraw_job is not None:
            self.after_cancel(self._redraw_job)
            self._redraw_job = None
        super().destroy()

    def _redraw(self) -> None:
        self._redraw_job = None
        canvas = self._dash_canvas
        if not canvas.winfo_exists():
            return
        width = canvas.winfo_width() - 1
        height = canvas.winfo_height() - 1
        if self._drawn == (width, height, self._color):
            return
        self._drawn = (width, height, self._color)
        canvas.delete("all")
        s = theme.widget_scale(self)
        inset = (10 * s - 3) if self._outer else 0
        x0, y0, x1, y1 = inset, inset, width - inset, height - inset
        if x1 <= x0 or y1 <= y0:
            return
        dash, gap = max(2, round(5 * s)), max(2, round(4 * s))
        for (ax, ay, bx, by) in ((x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)):
            length = math.hypot(bx - ax, by - ay)
            dx, dy = (bx - ax) / length, (by - ay) / length
            position = 0.0
            while position < length:
                end = min(length, position + dash)
                canvas.create_line(
                    ax + dx * position, ay + dy * position, ax + dx * end, ay + dy * end,
                    fill=self._color,
                )
                position += dash + gap


# =============================================================================
# Страницы
# =============================================================================


class PageTitle(ctk.CTkFrame):
    """Заголовок страницы (§7.2): Display 30, подзаголовок и кнопки справа."""

    def __init__(self, master, title: str, subtitle: str = "") -> None:
        super().__init__(master, fg_color="transparent", width=0, height=0)
        self.grid_columnconfigure(0, weight=1)
        self.title = text(self, title, font=theme.display(30), color=theme.TXT)
        self.title.grid(row=0, column=0, sticky="w")
        self.subtitle = text(self, subtitle, font=theme.mono(11), color=theme.FAINT)
        self.subtitle.grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.actions = box(self)
        self.actions.grid(row=0, column=1, rowspan=2, sticky="e")
        self._actions = 0

    def add_action(self, widget) -> None:
        widget.grid(row=0, column=self._actions, padx=(16 if self._actions else 0, 0))
        self._actions += 1


class SectionTitle(ctk.CTkLabel):
    """Заголовок раздела настроек: Display 17."""

    def __init__(self, master, value: str) -> None:
        super().__init__(
            master,
            text=value,
            font=theme.display(17),
            text_color=theme.TXT,
            anchor="w",
            width=0,
            height=0,
        )


class MonoRow(ctk.CTkFrame):
    """Строка «название — значение» (§7.4): 40 px, линия снизу."""

    def __init__(self, master, name: str, value: str = "") -> None:
        super().__init__(master, fg_color="transparent", height=40)
        self.grid_propagate(False)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        text(self, name, font=theme.sans(12), color=theme.DIM).grid(row=0, column=0, sticky="w")
        self.value = text(self, value, font=theme.mono(12), color=theme.TXT, anchor="e")
        self.value.grid(row=0, column=1, sticky="e", padx=(16, 0))
        self.actions = box(self)
        self.actions.grid(row=0, column=2, sticky="e")
        self._actions = 0
        hline(self).place(relx=0, rely=1.0, relwidth=1, anchor="sw")

    def add_action(self, widget) -> None:
        widget.grid(row=0, column=self._actions, padx=(12, 0))
        self._actions += 1

    def set_value(self, value: str, color: str = theme.TXT) -> None:
        self.value.configure(text=value, text_color=color)
