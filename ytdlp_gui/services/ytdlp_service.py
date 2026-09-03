"""Поиск и низкоуровневый запуск бинарников yt-dlp и FFmpeg.

Порядок поиска:
1. путь, указанный пользователем в настройках;
2. каталог приложения, его родитель (папка ``yt-dlp`` с готовым
   ``yt-dlp.exe``), их подкаталоги ``bin`` и содержимое собранного
   onefile-бандла (``sys._MEIPASS``);
3. переменная окружения ``PATH``;
4. стандартные каталоги системы.

Локальные каталоги проверяются раньше ``PATH``: копия, положенная рядом с
приложением или вшитая в сборку, — это осознанный выбор пользователя, а
случайный ``yt-dlp`` из ``PATH`` может оказаться заметно старше.

Ничего не загружается из сети — только поиск уже установленных бинарников.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

_APP_ROOT = Path(__file__).resolve().parent.parent

_STANDARD_DIRS_WINDOWS = [r"C:\ffmpeg\bin", r"C:\Program Files\ffmpeg\bin"]
_STANDARD_DIRS_POSIX = ["/usr/bin", "/usr/local/bin", "/opt/homebrew/bin", "/snap/bin"]

_YTDLP_NAME = "yt-dlp.exe" if sys.platform == "win32" else "yt-dlp"
_FFMPEG_NAME = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"


def creation_flags() -> int:
    """Флаг для subprocess, чтобы не мелькало консольное окно на Windows."""
    if sys.platform == "win32":
        return subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    return 0


#: Служебные переменные окружения загрузчика PyInstaller.
_PYINSTALLER_ENV_PREFIXES = ("_PYI", "_MEIPASS")


def subprocess_env() -> dict:
    """Окружение для дочерних процессов yt-dlp/FFmpeg.

    Во-первых, форсирует UTF-8 stdout/stderr у вложенного интерпретатора
    yt-dlp: без этого на системах с не-UTF8 консольной кодовой страницей
    (например, cp1251) вывод с кириллицей/эмодзи в названиях видео роняет
    процесс с ``OSError: [Errno 22] Invalid argument``.

    Во-вторых, вычищает служебные переменные загрузчика PyInstaller
    (``_PYI_*``, ``_MEIPASS2``): наш .exe собран PyInstaller и запускает
    ``yt-dlp.exe``, который тоже собран PyInstaller. Передавать чужому
    загрузчику координаты нашего бандла незачем — документация PyInstaller
    прямо предупреждает, что дочернее собранное приложение может принять их
    за свои.
    """
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    for name in [key for key in env if key.startswith(_PYINSTALLER_ENV_PREFIXES)]:
        del env[name]
    return env


def bundle_dir() -> Path | None:
    """Каталог с распакованным содержимым onefile-сборки.

    PyInstaller распаковывает вшитые файлы во временный каталог и кладёт
    путь к нему в ``sys._MEIPASS``; вне сборки атрибута нет.
    """
    meipass = getattr(sys, "_MEIPASS", None)
    return Path(meipass) if meipass else None


def _local_dirs() -> list[Path]:
    """Каталоги приложения — проверяются раньше ``PATH``."""
    dirs = [_APP_ROOT, _APP_ROOT.parent, _APP_ROOT / "bin", _APP_ROOT.parent / "bin"]
    if getattr(sys, "frozen", False):
        # В собранном PyInstaller-экзешнике __file__ модулей указывает
        # внутрь распакованного бандла (_MEIPASS/_internal), а не туда,
        # где реально лежит .exe, — поэтому _APP_ROOT там больше не
        # указывает на папку проекта рядом с yt-dlp.exe. sys.executable,
        # в отличие от __file__, всегда указывает на настоящее
        # расположение запущенного .exe.
        exe_dir = Path(sys.executable).resolve().parent
        dirs = [exe_dir, exe_dir / "bin", exe_dir.parent, exe_dir.parent / "bin", *dirs]
    bundle = bundle_dir()
    if bundle is not None:
        # Вшитая в сборку копия — последний из «своих» каталогов: копия,
        # положенная рядом с .exe, должна иметь приоритет над встроенной.
        dirs += [bundle, bundle / "bin"]
    return dirs


def _system_dirs() -> list[Path]:
    """Стандартные каталоги ОС — проверяются последними."""
    if sys.platform == "win32":
        return [Path(p) for p in _STANDARD_DIRS_WINDOWS]
    return [Path(p) for p in _STANDARD_DIRS_POSIX]


def _find_binary(name: str, user_path: str | None) -> Path | None:
    if user_path:
        candidate = Path(user_path)
        if candidate.is_dir():
            candidate = candidate / name
        if candidate.is_file():
            return candidate

    for directory in _local_dirs():
        candidate = directory / name
        if candidate.is_file():
            return candidate

    found = shutil.which(name)
    if found:
        return Path(found)

    for directory in _system_dirs():
        candidate = directory / name
        if candidate.is_file():
            return candidate
    return None


def _version_of(binary: Path, args: tuple[str, ...] = ("--version",)) -> str:
    try:
        result = subprocess.run(
            [str(binary), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            creationflags=creation_flags(),
            env=subprocess_env(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("Не удалось получить версию %s: %s", binary, exc)
        return ""
    return (result.stdout or "").strip().splitlines()[0] if result.stdout else ""


@dataclass
class Binaries:
    ytdlp: Path | None = None
    ffmpeg: Path | None = None
    ytdlp_version: str = ""
    ffmpeg_version: str = ""

    @property
    def ytdlp_available(self) -> bool:
        return self.ytdlp is not None

    @property
    def ffmpeg_available(self) -> bool:
        return self.ffmpeg is not None


class YtdlpService:
    """Локализация бинарников и низкоуровневые вызовы yt-dlp."""

    def __init__(self, ytdlp_path: str | None = None, ffmpeg_path: str | None = None) -> None:
        self.binaries = Binaries()
        self.locate(ytdlp_path, ffmpeg_path)

    @property
    def available(self) -> bool:
        return self.binaries.ytdlp_available

    def locate(self, ytdlp_path: str | None = None, ffmpeg_path: str | None = None) -> Binaries:
        ytdlp = _find_binary(_YTDLP_NAME, ytdlp_path)
        ffmpeg = _find_binary(_FFMPEG_NAME, ffmpeg_path)

        binaries = Binaries(ytdlp=ytdlp, ffmpeg=ffmpeg)
        if ytdlp:
            binaries.ytdlp_version = _version_of(ytdlp)
        if ffmpeg:
            binaries.ffmpeg_version = _version_of(ffmpeg, ("-version",))
            if binaries.ffmpeg_version:
                binaries.ffmpeg_version = (
                    binaries.ffmpeg_version.replace("ffmpeg version ", "").split(" ")[0]
                )
        self.binaries = binaries
        return binaries

    # ------------------------------------------------------------------
    def base_command(self) -> list[str]:
        if not self.binaries.ytdlp:
            raise RuntimeError("yt-dlp не найден")
        command = [str(self.binaries.ytdlp)]
        if self.binaries.ffmpeg:
            command += ["--ffmpeg-location", str(self.binaries.ffmpeg.parent)]
        return command

    def run(self, args: list[str], timeout: float | None = 60) -> subprocess.CompletedProcess:
        command = self.base_command() + args
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=creation_flags(),
            env=subprocess_env(),
        )
