"""Виджет превью (обложки) видео."""

from __future__ import annotations

import logging
from pathlib import Path

import customtkinter as ctk

from .. import theme

log = logging.getLogger(__name__)

try:
    from PIL import Image

    PIL_AVAILABLE = True
except ImportError:  # pragma: no cover
    PIL_AVAILABLE = False


class ThumbnailView(ctk.CTkFrame):
    """Показывает картинку-превью с сохранением пропорций либо заглушку."""

    def __init__(self, master, width: int = 320, height: int = 180) -> None:
        super().__init__(
            master,
            width=width,
            height=height,
            fg_color=theme.color("bg.elevated"),
            border_color=theme.color("border"),
            border_width=1,
            corner_radius=theme.RADIUS["sm"],
        )
        self.grid_propagate(False)
        self.pack_propagate(False)
        self._width = width
        self._height = height
        self._image_ref: ctk.CTkImage | None = None

        self.label = ctk.CTkLabel(
            self, text="Нет превью", text_color=theme.color("fg.secondary"), font=theme.font("small")
        )
        self.label.pack(fill="both", expand=True)

    def clear(self, placeholder: str = "Нет превью") -> None:
        self._image_ref = None
        self.label.configure(image=None, text=placeholder)

    def show_loading(self) -> None:
        self._image_ref = None
        self.label.configure(image=None, text="Загрузка превью…")

    def show_path(self, path: Path | None) -> None:
        if path is None or not PIL_AVAILABLE:
            self.clear("Превью недоступно" if not PIL_AVAILABLE else "Нет превью")
            return
        # Файл превью приходит из сети (см. thumbnail_service) — весь разбор
        # картинки, включая вычисление размеров, обёрнут одним try/except:
        # повреждённый файл или, например, изображение с нулевой шириной
        # не должны ронять необработанным исключением обработчик события.
        try:
            image = Image.open(path)
            image = image.convert("RGB")
            if image.width <= 0 or image.height <= 0:
                raise ValueError("Некорректные размеры изображения")
            ratio = min(self._width / image.width, self._height / image.height)
            size = (max(1, int(image.width * ratio)), max(1, int(image.height * ratio)))
            ctk_image = ctk.CTkImage(light_image=image, dark_image=image, size=size)
        except Exception as exc:  # noqa: BLE001 - повреждённый/неполный/аномальный файл превью
            log.warning("Не удалось открыть превью %s: %s", path, exc)
            self.clear()
            return

        self._image_ref = ctk_image
        self.label.configure(image=ctk_image, text="")
