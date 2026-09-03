"""Загрузка и кэширование превью (обложек) видео.

Картинки скачиваются во временный каталог и переиспользуются при повторном
запросе того же URL — раздел «превью видео» из требований пользователя.
"""

from __future__ import annotations

import logging
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .filesystem_service import FilesystemService

log = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15
MAX_BYTES = 15 * 1024 * 1024
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ytdlp-gui/1.0"

# thumbnail_url приходит из JSON-метаданных, которые yt-dlp извлёк с
# сайта видео, — фактически это внешние, не полностью доверенные данные.
# urllib по умолчанию понимает и file://, что позволило бы обложке с
# вредоносного/скомпрометированного сайта заставить приложение прочитать
# произвольный локальный файл вместо картинки. Ограничиваем протокол.
_ALLOWED_SCHEMES = {"http", "https"}

# Превью из yt-dlp приходит в исходном формате источника (обычно JPEG или
# WebP) и кэшируется как есть — расширение файла сохранения решает, во что
# его перекодировать.
_SAVE_FORMATS = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG"}


class ThumbnailSaveError(Exception):
    pass


class ThumbnailService:
    def __init__(self, filesystem: FilesystemService | None = None) -> None:
        self.filesystem = filesystem or FilesystemService()

    def fetch(self, url: str) -> Path | None:
        """Скачивает превью по URL и возвращает путь к локальному файлу."""
        if not url:
            return None
        scheme = urllib.parse.urlsplit(url).scheme.lower()
        if scheme not in _ALLOWED_SCHEMES:
            log.warning("Заблокирован недопустимый протокол превью (%s): %s", scheme or "—", url)
            return None
        cache_path = self.filesystem.thumbnail_cache_path(url)
        if cache_path.is_file() and cache_path.stat().st_size > 0:
            return cache_path

        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                data = response.read(MAX_BYTES)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            log.warning("Не удалось загрузить превью %s: %s", url, exc)
            return None

        try:
            cache_path.write_bytes(data)
        except OSError as exc:
            log.warning("Не удалось сохранить превью в кэш: %s", exc)
            return None
        return cache_path

    def save_as(self, url: str, dest_path: Path) -> Path:
        """Скачивает (если нужно) и сохраняет превью в указанный файл,
        перекодируя в PNG/JPEG по расширению ``dest_path``."""
        if not url:
            raise ThumbnailSaveError("У этого видео нет превью")

        cached = self.fetch(url)
        if cached is None:
            raise ThumbnailSaveError("Не удалось загрузить превью")

        try:
            from PIL import Image
        except ImportError as exc:
            raise ThumbnailSaveError("Для сохранения превью нужен пакет Pillow") from exc

        dest_path = Path(dest_path)
        pil_format = _SAVE_FORMATS.get(dest_path.suffix.lower().lstrip("."), "PNG")

        try:
            with Image.open(cached) as image:
                if pil_format == "JPEG":
                    image = image.convert("RGB")
                    image.save(dest_path, pil_format, quality=95)
                else:
                    image.save(dest_path, pil_format)
        except Exception as exc:  # noqa: BLE001 - показываем пользователю любую ошибку конвертации/сохранения
            raise ThumbnailSaveError(f"Не удалось сохранить файл: {exc}") from exc
        return dest_path
