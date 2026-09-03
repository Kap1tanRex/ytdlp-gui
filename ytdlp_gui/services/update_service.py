"""Поиск и установка обновлений yt-dlp через GitHub Releases.

Повторяет подсистему обновлений ZapretGUI (``infrastructure/net``):
клиент релизов с кэшем, скачивание с проверкой размера и SHA-256,
атомарная замена файла. Отличие в предмете: ZapretGUI обновляет ядро
zapret, здесь обновляется ``yt-dlp`` — инструмент, который ломается чаще
всего остального, потому что YouTube меняется постоянно.

Что важно знать о безопасности этого модуля: он скачивает и кладёт на
диск исполняемый файл. Поэтому — только https, только домены GitHub,
ограничение размера, обязательная сверка SHA-256 с файлом контрольных
сумм того же релиза (без него установка не выполняется) и запись через
временный файл с ``os.replace``.

Ничего не устанавливается само: сеть трогается только по явной команде
пользователя (кнопка «Проверить обновления» или включённая им проверка
при запуске), а установка — только по кнопке «Скачать».
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import ssl
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from ..core.updates import ReleaseInfo, Version, is_newer

log = logging.getLogger(__name__)

#: Репозиторий, за релизами которого следим.
REPO = "yt-dlp/yt-dlp"
RELEASES_URL = f"https://api.github.com/repos/{REPO}/releases"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"

#: Куда разрешено ходить. Всё остальное — отказ, даже если так сказал ответ
#: GitHub: ссылки на файлы приходят из сети и доверенными данными не являются.
_ALLOWED_HOSTS = {
    "api.github.com",
    "github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
}

REQUEST_TIMEOUT = 20
#: Ответ со списком релизов — это JSON с описаниями, не файлы.
MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_TEXT_BYTES = 1 * 1024 * 1024
#: yt-dlp.exe весит ~18 МБ; запас на рост, но не безграничный.
MAX_ASSET_BYTES = 150 * 1024 * 1024
#: Ответ GitHub кэшируется — повторная проверка не тратит лимит запросов.
CACHE_TTL_S = 900.0

USER_AGENT = "ytdlp-gui (+https://github.com/yt-dlp/yt-dlp)"

#: Имя файла релиза для текущей платформы.
_ASSET_NAMES = {"win32": "yt-dlp.exe", "darwin": "yt-dlp_macos"}
_SUMS_ASSET = "SHA2-256SUMS"


class UpdateError(Exception):
    """Обновление не получилось — с текстом, который можно показать."""


ProgressCallback = Callable[[int, int], None]


def asset_name_for_platform() -> str:
    return _ASSET_NAMES.get(sys.platform, "yt-dlp")


class UpdateService:
    """Клиент GitHub Releases и установщик нового ``yt-dlp``."""

    def __init__(self, repo: str = REPO) -> None:
        self.repo = repo
        self._releases_url = f"https://api.github.com/repos/{repo}/releases"
        self._cache: dict[str, tuple[float, object]] = {}
        self._context = ssl.create_default_context()

    # -- чтение релизов ------------------------------------------------------
    def history(self, limit: int = 10, *, prerelease: bool = False) -> list[ReleaseInfo]:
        """Последние релизы, новые первыми. Материал для окна «что нового»."""
        payload = self._get_json(f"{self._releases_url}?per_page={max(1, min(limit, 30))}")
        if not isinstance(payload, list):
            raise UpdateError("GitHub вернул неожиданный ответ.")

        releases: list[ReleaseInfo] = []
        for entry in payload:
            if not isinstance(entry, dict) or entry.get("draft"):
                continue
            if entry.get("prerelease") and not prerelease:
                continue
            info = self._to_info(entry)
            if info is not None:
                releases.append(info)
            if len(releases) >= limit:
                break
        return releases

    def latest(self, *, prerelease: bool = False) -> ReleaseInfo | None:
        releases = self.history(limit=5, prerelease=prerelease)
        return releases[0] if releases else None

    def check(self, current_version: str, *, prerelease: bool = False) -> ReleaseInfo | None:
        """Релиз новее установленного — или ``None``, если обновлять нечего."""
        latest = self.latest(prerelease=prerelease)
        if latest is None:
            return None
        return latest if is_newer(latest.tag, current_version) else None

    def newer_than(self, releases: list[ReleaseInfo], current_version: str) -> list[ReleaseInfo]:
        return [r for r in releases if is_newer(r.tag, current_version)]

    def _to_info(self, entry: dict) -> ReleaseInfo | None:
        tag = str(entry.get("tag_name") or "")
        if not tag:
            return None
        asset = self._pick_asset(entry.get("assets") or [])
        return ReleaseInfo(
            tag=tag,
            version=Version.parse(tag),
            published_at=_parse_time(entry.get("published_at")),
            notes=str(entry.get("body") or "")[:20000],
            html_url=str(entry.get("html_url") or RELEASES_PAGE),
            asset_name=str(asset.get("name", "")) if asset else "",
            asset_url=str(asset.get("browser_download_url", "")) if asset else "",
            asset_size=int(asset.get("size", 0)) if asset else 0,
            prerelease=bool(entry.get("prerelease")),
        )

    @staticmethod
    def _pick_asset(assets: list) -> dict | None:
        """Файл ровно для текущей платформы — без «похожих» имён.

        В релизе лежат и ``yt-dlp_x86.exe``, и архивы; подстановочный
        поиск легко выбрал бы не тот файл, поэтому сравнение точное.
        """
        wanted = asset_name_for_platform()
        for asset in assets:
            if isinstance(asset, dict) and str(asset.get("name", "")) == wanted:
                return asset
        return None

    # -- установка -----------------------------------------------------------
    def download(
        self,
        info: ReleaseInfo,
        destination: Path,
        *,
        progress: ProgressCallback | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> Path:
        """Скачивает файл релиза, сверяет SHA-256 и кладёт по адресу.

        Возвращает путь установленного файла. Любая проблема — исключение
        :class:`UpdateError` с текстом для пользователя.
        """
        if not info.is_installable:
            raise UpdateError(
                f"В релизе {info.version_text} нет файла {asset_name_for_platform()} "
                "для этой системы."
            )

        expected = self._expected_sha256(info)
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)

        # Скачиваем рядом с целью: перемещение в пределах одного тома
        # атомарно, а через %TEMP% файл мог бы поехать между дисками.
        handle, temp_name = tempfile.mkstemp(
            prefix=".ytdlp-update-", suffix=".part", dir=str(destination.parent)
        )
        os.close(handle)
        temp_path = Path(temp_name)
        try:
            digest, size = self._stream(info, temp_path, progress=progress, cancelled=cancelled)
            if info.asset_size and size != info.asset_size:
                raise UpdateError(
                    f"Размер загруженного файла ({size} Б) не совпадает с заявленным "
                    f"({info.asset_size} Б)."
                )
            if digest != expected:
                raise UpdateError(
                    "Контрольная сумма загруженного файла не совпадает с опубликованной "
                    "в релизе — файл не установлен."
                )
            if sys.platform != "win32":
                temp_path.chmod(0o755)
            os.replace(temp_path, destination)
        except UpdateError:
            temp_path.unlink(missing_ok=True)
            raise
        except PermissionError as exc:
            temp_path.unlink(missing_ok=True)
            raise UpdateError(
                f"Нет доступа к {destination}: возможно, файл занят запущенным yt-dlp. "
                "Дождитесь завершения загрузок и повторите."
            ) from exc
        except (OSError, urllib.error.URLError) as exc:
            temp_path.unlink(missing_ok=True)
            raise UpdateError(f"Не удалось сохранить файл: {exc}") from exc
        log.info("yt-dlp %s установлен в %s (sha256=%s)", info.version_text, destination, digest)
        return destination

    def _expected_sha256(self, info: ReleaseInfo) -> str:
        """SHA-256 нужного файла из ``SHA2-256SUMS`` того же релиза.

        Без контрольной суммы установка не выполняется: подменённый
        исполняемый файл — это выполнение чужого кода на машине
        пользователя, и «наверное, всё в порядке» здесь не годится.
        """
        if info.sha256:
            return info.sha256.lower()
        sums_url = f"https://github.com/{self.repo}/releases/download/{info.tag}/{_SUMS_ASSET}"
        try:
            text = self._get_text(sums_url)
        except UpdateError as exc:
            raise UpdateError(
                f"Не удалось получить контрольные суммы релиза ({exc}). "
                "Без них обновление не устанавливается."
            ) from exc
        for line in text.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1].lstrip("*") == info.asset_name:
                return parts[0].strip().lower()
        raise UpdateError(
            f"В контрольных суммах релиза нет строки для {info.asset_name} — "
            "обновление не устанавливается."
        )

    def _stream(
        self,
        info: ReleaseInfo,
        target: Path,
        *,
        progress: ProgressCallback | None,
        cancelled: Callable[[], bool] | None,
    ) -> tuple[str, int]:
        request = self._request(info.asset_url)
        digest = hashlib.sha256()
        received = 0
        try:
            with urllib.request.urlopen(
                request, timeout=REQUEST_TIMEOUT, context=self._context
            ) as response:
                total = info.asset_size or int(response.headers.get("Content-Length") or 0)
                with target.open("wb") as file:
                    while True:
                        if cancelled is not None and cancelled():
                            raise UpdateError("Загрузка отменена.")
                        chunk = response.read(256 * 1024)
                        if not chunk:
                            break
                        received += len(chunk)
                        if received > MAX_ASSET_BYTES:
                            raise UpdateError("Файл обновления неожиданно большой — загрузка прервана.")
                        digest.update(chunk)
                        file.write(chunk)
                        if progress is not None:
                            progress(received, total)
        except urllib.error.URLError as exc:
            raise UpdateError(f"Не удалось скачать обновление: {exc.reason}") from exc
        return digest.hexdigest(), received

    # -- HTTP ----------------------------------------------------------------
    def _request(self, url: str) -> urllib.request.Request:
        parts = urllib.parse.urlsplit(url)
        if parts.scheme != "https" or parts.hostname not in _ALLOWED_HOSTS:
            raise UpdateError(f"Недопустимый адрес обновления: {url}")
        return urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

    def _read(self, url: str, max_bytes: int) -> bytes:
        request = self._request(url)
        try:
            with urllib.request.urlopen(
                request, timeout=REQUEST_TIMEOUT, context=self._context
            ) as response:
                data = response.read(max_bytes + 1)
        except urllib.error.HTTPError as exc:
            if exc.code == 403:
                raise UpdateError(
                    "GitHub временно ограничил число запросов. Попробуйте позже."
                ) from exc
            raise UpdateError(f"GitHub ответил ошибкой {exc.code}.") from exc
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise UpdateError(f"Нет связи с GitHub: {exc}") from exc
        if len(data) > max_bytes:
            raise UpdateError("Ответ GitHub неожиданно большой — прерываем.")
        return data

    def _get_text(self, url: str) -> str:
        return self._read(url, MAX_TEXT_BYTES).decode("utf-8", errors="replace")

    def _get_json(self, url: str) -> object:
        cached = self._cache.get(url)
        if cached and time.monotonic() - cached[0] < CACHE_TTL_S:
            return cached[1]
        try:
            payload = json.loads(self._read(url, MAX_JSON_BYTES).decode("utf-8", errors="replace"))
        except ValueError as exc:
            raise UpdateError("GitHub вернул неразбираемый ответ.") from exc
        self._cache[url] = (time.monotonic(), payload)
        return payload


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
