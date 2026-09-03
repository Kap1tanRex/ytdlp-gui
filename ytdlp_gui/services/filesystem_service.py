"""Пути, временные файлы и выходные шаблоны имён.

Временные файлы (кэш превью, логи) хранятся в
``%TEMP%/YtDlpGUI/{previews,cache,logs}``, аналогично ffmpeg_gui.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class FilesystemService:
    def __init__(self, temp_root: Path | None = None) -> None:
        self.temp_root = Path(temp_root) if temp_root else Path(tempfile.gettempdir()) / "YtDlpGUI"

    @property
    def previews_dir(self) -> Path:
        path = self.temp_root / "previews"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def cache_dir(self) -> Path:
        path = self.temp_root / "cache"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def logs_dir(self) -> Path:
        path = self.temp_root / "logs"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def cleanup_temp(self) -> None:
        directory = self.temp_root / "cache"
        if not directory.is_dir():
            return
        for item in directory.iterdir():
            try:
                if item.is_file():
                    item.unlink()
                else:
                    shutil.rmtree(item, ignore_errors=True)
            except OSError as exc:
                log.debug("Не удалось удалить временный файл %s: %s", item, exc)

    # -- выходные пути ---------------------------------------------------
    def default_download_dir(self) -> Path:
        home = Path.home()
        downloads = home / "Downloads"
        return downloads if downloads.is_dir() else home

    def output_template(self, output_dir: str | Path, template: str | None = None) -> str:
        """Строит шаблон ``-o`` для yt-dlp с учётом каталога назначения."""
        directory = Path(output_dir) if output_dir else self.default_download_dir()
        directory.mkdir(parents=True, exist_ok=True)
        name_template = template or "%(title).200B [%(id)s].%(ext)s"
        return str(directory / name_template)

    def free_space(self, path: Path) -> int:
        path = Path(path)
        while not path.exists() and path != path.parent:
            path = path.parent
        try:
            return shutil.disk_usage(path).free
        except OSError:
            return 0

    def thumbnail_cache_path(self, url: str) -> Path:
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
        return self.previews_dir / f"{digest}.img"


def sanitize_filename(name: str) -> str:
    return _INVALID_CHARS.sub("_", name).strip() or "download"


def open_folder(path: Path) -> None:
    """Открывает системный проводник в папке файла (или сам путь)."""
    target = path if path.is_dir() else path.parent
    try:
        if sys.platform == "win32":
            os.startfile(str(target))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(target)], check=False)
        else:
            subprocess.run(["xdg-open", str(target)], check=False)
    except OSError as exc:
        log.warning("Не удалось открыть папку %s: %s", target, exc)
