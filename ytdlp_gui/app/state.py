"""Настройки приложения (``config.json``) и состояние сессии.

| ОС | Каталог |
|---|---|
| Windows | ``%APPDATA%\\YtDlpGUI`` |
| Linux | ``~/.config/YtDlpGUI`` |
| macOS | ``~/Library/Application Support/YtDlpGUI`` |

Неизвестные и повреждённые значения заменяются значениями по умолчанию,
а не приводят к падению приложения.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

log = logging.getLogger(__name__)

APP_VERSION = "2.0.0"
SETTINGS_VERSION = 1


def _default_config_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "YtDlpGUI"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "YtDlpGUI"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "YtDlpGUI"


@dataclass
class Settings:
    version: int = SETTINGS_VERSION
    language: str = "ru"
    theme: str = "System"
    #: Масштаб интерфейса, 0.8…1.6 (см. ytdlp_gui.gui.theme).
    ui_scale: float = 1.0

    ytdlp_path: str = ""
    ffmpeg_path: str = ""
    output_directory: str = ""
    output_template: str = "%(title).200B [%(id)s].%(ext)s"

    overwrite_policy: str = "skip"  # overwrite | skip
    parallel_jobs: int = 1
    download_playlists: bool = False
    restrict_filenames: bool = False

    proxy: str = ""
    cookies_file: str = ""
    #: Имя браузера для ``--cookies-from-browser`` (пустая строка — не использовать).
    cookies_from_browser: str = ""
    limit_rate: str = ""

    default_video_quality: str = "best"  # best | worst
    default_container: str = "mp4"
    default_audio_format: str = "mp3"
    default_audio_quality: str = "192"

    embed_metadata_default: bool = True
    embed_chapters_default: bool = True
    embed_thumbnail_default: bool = False

    subtitle_langs_default: list[str] = field(default_factory=lambda: ["ru", "en"])
    include_auto_subs_default: bool = False

    show_tooltips: bool = True

    #: Проверять обновления yt-dlp при запуске. По умолчанию выключено:
    #: приложение не ходит в сеть, пока его об этом не попросили.
    check_updates_on_start: bool = False
    #: Время последней проверки (ISO) и тег версии, о которой уже сообщили, —
    #: чтобы одно и то же обновление не показывалось при каждом запуске.
    last_update_check: str = ""
    last_notified_release: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        known_fields = {f.name for f in fields(cls)}
        defaults = cls()
        clean: dict = {}
        for name in known_fields:
            if name not in data:
                continue
            value = data[name]
            default_value = getattr(defaults, name)
            if isinstance(default_value, float) and isinstance(value, int) and not isinstance(value, bool):
                value = float(value)
            if isinstance(default_value, list) and isinstance(value, list):
                clean[name] = [str(v) for v in value]
                continue
            if not isinstance(value, type(default_value)):
                continue
            clean[name] = value
        clean["version"] = SETTINGS_VERSION
        return cls(**clean)


class SettingsStore:
    def __init__(self, settings_dir: Path | None = None) -> None:
        self.directory = Path(settings_dir) if settings_dir else _default_config_dir()

    @property
    def config_path(self) -> Path:
        return self.directory / "config.json"

    @property
    def logs_dir(self) -> Path:
        return self.directory / "logs"

    def load(self) -> Settings:
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            log.warning("Не удалось создать каталог настроек: %s", exc)

        if not self.config_path.is_file():
            return Settings()
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            log.warning("config.json повреждён, используются значения по умолчанию: %s", exc)
            return Settings()
        if not isinstance(data, dict):
            return Settings()
        return Settings.from_dict(data)

    def save(self, settings: Settings) -> None:
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            self.config_path.write_text(
                json.dumps(settings.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as exc:
            log.warning("Не удалось сохранить настройки: %s", exc)


class AppState:
    """Список запрошенных видео/плейлистов и текущий выбор (сессия)."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.items: list = []
        self.selected_index: int = -1

    def add_item(self, info) -> bool:
        if any(existing.url == info.url for existing in self.items):
            return False
        self.items.append(info)
        return True

    def remove_at(self, index: int) -> bool:
        if not 0 <= index < len(self.items):
            return False
        del self.items[index]
        if self.selected_index >= len(self.items):
            self.selected_index = len(self.items) - 1
        return True

    def select(self, index: int):
        if 0 <= index < len(self.items):
            self.selected_index = index
            return self.items[index]
        self.selected_index = -1
        return None

    def clear(self) -> None:
        self.items.clear()
        self.selected_index = -1
