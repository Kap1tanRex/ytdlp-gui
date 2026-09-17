"""Миниатюры видео: фоновая загрузка, кэш и виджет-рамка.

Обложка скачивается один раз (кэш — в ``ThumbnailService``), картинка
обрезается «по заполнению» под пропорции места — как миниатюра строки
очереди у «Стемницы» (фон ``PIT``, радиус 2), только вместо волны кадр.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

import customtkinter as ctk

from ...core.models import VideoInfo
from .. import theme

log = logging.getLogger(__name__)

try:
    from PIL import Image

    PIL_AVAILABLE = True
except ImportError:  # pragma: no cover
    PIL_AVAILABLE = False

ImageCallback = Callable[["ctk.CTkImage | None"], None]


class ThumbnailLoader:
    """Отдаёт обложку нужного размера; сеть и декодирование — в фоне.

    ``post`` переносит вызов в поток Tk (очередь событий главного окна).
    """

    def __init__(self, app, post: Callable[..., None]) -> None:
        self._app = app
        self._post = post
        self._images: dict[str, object | None] = {}
        self._scaled: dict[tuple[str, int, int], ctk.CTkImage] = {}
        self._waiting: dict[str, list[tuple[tuple[int, int], ImageCallback]]] = {}

    def request(self, info: VideoInfo | None, size: tuple[int, int], callback: ImageCallback) -> None:
        url = info.thumbnail_url if info is not None else ""
        if not url or not PIL_AVAILABLE:
            callback(None)
            return
        if url in self._images:
            callback(self._fit(url, size))
            return
        waiting = self._waiting.setdefault(url, [])
        waiting.append((size, callback))
        if len(waiting) == 1:
            threading.Thread(target=self._load, args=(info, url), daemon=True).start()

    def _load(self, info: VideoInfo, url: str) -> None:
        image = None
        try:
            path = self._app.thumbnail_path(info)
            if path is not None:
                # Файл пришёл из сети: любой сбой разбора — просто «нет обложки».
                with Image.open(path) as source:
                    image = source.convert("RGB")
                if image.width <= 0 or image.height <= 0:
                    image = None
        except Exception as exc:  # noqa: BLE001
            log.warning("Не удалось открыть превью %s: %s", url, exc)
            image = None
        self._post(self._loaded, url, image)

    def _loaded(self, url: str, image) -> None:
        self._images[url] = image
        for size, callback in self._waiting.pop(url, []):
            callback(self._fit(url, size))

    def _fit(self, url: str, size: tuple[int, int]) -> ctk.CTkImage | None:
        image = self._images.get(url)
        if image is None:
            return None
        key = (url, *size)
        cached = self._scaled.get(key)
        if cached is None:
            cached = ctk.CTkImage(light_image=_cover(image, size), size=size)
            self._scaled[key] = cached
        return cached


def _cover(image, size: tuple[int, int]):
    """Обрезка по центру до пропорций ``size`` без искажения."""
    target = size[0] / size[1]
    ratio = image.width / image.height
    if ratio > target:
        width = round(image.height * target)
        left = (image.width - width) // 2
        return image.crop((left, 0, left + width, image.height))
    height = round(image.width / target)
    top = (image.height - height) // 2
    return image.crop((0, top, image.width, top + height))


class Thumb(ctk.CTkLabel):
    """Рамка под миниатюру: пока картинки нет — просто «дно» ``PIT``."""

    def __init__(self, master, width: int, height: int, *, radius: int = 2) -> None:
        super().__init__(
            master, text="", width=width, height=height, fg_color=theme.PIT, corner_radius=radius
        )
        self._size = (width, height)
        self._token = 0

    def load(self, loader: ThumbnailLoader, info: VideoInfo | None) -> None:
        self._token += 1
        token = self._token
        self.clear()
        loader.request(info, self._size, lambda image: self._apply(image, token))

    def clear(self) -> None:
        self.configure(image=None)
        self._label.configure(image="")

    def _apply(self, image, token: int) -> None:
        if token != self._token or not self.winfo_exists():
            return
        if image is None:
            self.clear()
        else:
            self.configure(image=image)
