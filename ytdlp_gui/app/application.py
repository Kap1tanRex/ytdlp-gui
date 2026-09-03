"""Application Controller.

Связывает GUI со слоями модели, сервисов и очереди. GUI обращается
только к этому классу, а не к сервисам напрямую — как и в ffmpeg_gui.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import sys
import threading
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from ..core.command_builder import CommandBuildError, build as build_command, command_to_string
from ..core.updates import ReleaseInfo
from ..core.models import (
    DownloadMode,
    DownloadOptions,
    Job,
    SubtitleMode,
    VideoInfo,
)
from ..core.validator import ValidationResult, validate as validate_job
from ..services.filesystem_service import FilesystemService, open_folder
from ..services.info_service import InfoService
from ..services.process_manager import ProcessManager
from ..services.queue_manager import QueueCallbacks, QueueManager
from ..services.thumbnail_service import ThumbnailSaveError, ThumbnailService
from ..services.update_service import UpdateError, UpdateService, asset_name_for_platform
from ..services.ytdlp_service import YtdlpService, bundle_dir
from .events import Event, EventBus
from .state import APP_VERSION, AppState, SettingsStore

log = logging.getLogger(__name__)

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
TRANSLATIONS_DIR = PACKAGE_ROOT / "resources" / "translations"


class Translator:
    """Локализация интерфейса."""

    def __init__(self, language: str = "ru") -> None:
        self.language = language
        self._strings: dict[str, str] = {}
        self.load(language)

    def load(self, language: str) -> None:
        self.language = language
        path = TRANSLATIONS_DIR / f"{language}.json"
        try:
            self._strings = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            log.warning("Перевод %s не загружен: %s", language, exc)
            self._strings = {}

    def __call__(self, key: str, default: str | None = None) -> str:
        return self._strings.get(key, default if default is not None else key)

    @staticmethod
    def available_languages() -> list[str]:
        if not TRANSLATIONS_DIR.is_dir():
            return ["ru"]
        return sorted(path.stem for path in TRANSLATIONS_DIR.glob("*.json"))


@dataclass
class SystemInfo:
    app_version: str = ""
    ytdlp_version: str = ""
    ffmpeg_version: str = ""
    ytdlp_path: str = ""
    ffmpeg_path: str = ""
    free_disk_space: int = 0
    recent_errors: list[str] = field(default_factory=list)

    def to_text(self) -> str:
        from ..core.models import format_size

        lines = [
            f"yt-dlp GUI {self.app_version}",
            "",
            f"yt-dlp: {self.ytdlp_version or 'не найден'}",
            f"FFmpeg: {self.ffmpeg_version or 'не найден (слияние видео/аудио и субтитры недоступны)'}",
            f"Путь yt-dlp: {self.ytdlp_path or '—'}",
            f"Путь FFmpeg: {self.ffmpeg_path or '—'}",
            f"Свободно места: {format_size(self.free_disk_space)}",
        ]
        if self.recent_errors:
            lines.append("")
            lines.append("Последние ошибки:")
            lines.extend(f"  - {error}" for error in self.recent_errors)
        return "\n".join(lines)


class Application:
    """Фасад приложения."""

    def __init__(self, settings_dir: Path | None = None) -> None:
        self.bus = EventBus()
        self.store = SettingsStore(settings_dir)
        self.settings = self.store.load()
        self.state = AppState(settings=self.settings)
        self.translator = Translator(self.settings.language)

        self._setup_logging()

        self.ytdlp = YtdlpService(self.settings.ytdlp_path, self.settings.ffmpeg_path)
        self.filesystem = FilesystemService()
        self.thumbnails = ThumbnailService(self.filesystem)
        self.info = InfoService(self.ytdlp)
        self.updates = UpdateService()

        self.processes = ProcessManager(self.store.logs_dir)
        self.queue = QueueManager(
            self.ytdlp,
            self.processes,
            self.filesystem,
            network_args_provider=self._network_args,
            callbacks=QueueCallbacks(
                on_job_added=lambda job: self.bus.publish(Event.JOB_ADDED, job),
                on_job_started=lambda job: self.bus.publish(Event.JOB_STARTED, job),
                on_job_progress=lambda job, info: self.bus.publish(Event.JOB_PROGRESS, job, info),
                on_job_stage=lambda job, text: self.bus.publish(Event.JOB_STAGE, job, text),
                on_job_finished=self._on_job_finished,
                on_job_log=lambda job, line: self.bus.publish(Event.JOB_LOG, job, line),
                on_queue_changed=lambda: self.bus.publish(Event.QUEUE_CHANGED),
                on_queue_idle=lambda: self.bus.publish(Event.QUEUE_IDLE),
            ),
            parallel_jobs=self.settings.parallel_jobs,
        )
        self._recent_errors: list[str] = []

    # -- инициализация -------------------------------------------------
    def _setup_logging(self) -> None:
        logs_dir = self.store.logs_dir
        try:
            logs_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            return
        root = logging.getLogger()
        if any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers):
            return
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

        # Создание файловых хендлеров — I/O, которое теоретически может
        # упасть (файл лога заблокирован другим процессом, антивирус,
        # диск переполнен и т.п.). В собранном .exe без консоли это иначе
        # роняло бы приложение ещё до появления окна, без единого
        # сообщения пользователю — поэтому не даём такой ошибке всплыть.
        try:
            app_handler = logging.handlers.RotatingFileHandler(
                logs_dir / "app.log", maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
            )
            app_handler.setFormatter(formatter)
            root.addHandler(app_handler)
            root.setLevel(logging.INFO)

            ytdlp_handler = logging.handlers.RotatingFileHandler(
                logs_dir / "ytdlp.log", maxBytes=4 * 1024 * 1024, backupCount=3, encoding="utf-8"
            )
            ytdlp_handler.setFormatter(formatter)
            ytdlp_logger = logging.getLogger("ytdlp")
            ytdlp_logger.addHandler(ytdlp_handler)
            ytdlp_logger.propagate = False
        except OSError:
            pass

    def initialize(self) -> None:
        self.filesystem.cleanup_temp()
        if not self.ytdlp.available:
            self.bus.publish(Event.YTDLP_MISSING)
            return
        self.bus.publish(Event.TOOLS_READY, self.ytdlp.binaries)
        if self.settings.check_updates_on_start:
            self.check_updates(announce_only_new=True)

    def set_tool_paths(self, ytdlp_path: str, ffmpeg_path: str) -> bool:
        self.ytdlp.locate(ytdlp_path, ffmpeg_path)
        if not self.ytdlp.available:
            self.bus.publish(Event.YTDLP_MISSING)
            return False
        self.settings.ytdlp_path = str(self.ytdlp.binaries.ytdlp)
        self.settings.ffmpeg_path = str(self.ytdlp.binaries.ffmpeg or "")
        self.store.save(self.settings)
        self.bus.publish(Event.TOOLS_READY, self.ytdlp.binaries)
        return True

    def _network_args(self) -> list[str]:
        args: list[str] = []
        if self.settings.proxy:
            args += ["--proxy", self.settings.proxy]
        # Браузер и файл — взаимоисключающие источники cookies: выбранный
        # браузер отменяет файл, иначе в jar попали бы cookies из обоих
        # источников, и понять, какие из них сработали, было бы нельзя.
        if self.settings.cookies_from_browser:
            args += ["--cookies-from-browser", self.settings.cookies_from_browser]
        elif self.settings.cookies_file:
            args += ["--cookies", self.settings.cookies_file]
        if self.settings.limit_rate:
            args += ["--limit-rate", self.settings.limit_rate]
        if self.settings.restrict_filenames:
            args.append("--restrict-filenames")
        return args

    # -- получение сведений о видео -------------------------------------
    def fetch_url(self, url: str, playlist: bool | None = None, async_probe: bool = True) -> None:
        url = url.strip().strip('"').strip("'")
        if not url:
            return
        use_playlist = self.settings.download_playlists if playlist is None else playlist
        self.bus.publish(Event.FETCH_STARTED, url)
        if async_probe:
            threading.Thread(target=self._fetch_one, args=(url, use_playlist), daemon=True).start()
        else:
            self._fetch_one(url, use_playlist)

    def fetch_urls(self, urls: Iterable[str], playlist: bool | None = None) -> None:
        for url in urls:
            self.fetch_url(url, playlist=playlist)

    def _fetch_one(self, url: str, playlist: bool) -> None:
        info = self.info.probe(url, playlist=playlist, extra_args=self._network_args())
        added = self.state.add_item(info)
        self.bus.publish(Event.ITEMS_CHANGED, self.state.items)
        self.bus.publish(Event.FETCH_FINISHED, info, added)

    def remove_item(self, index: int) -> None:
        if self.state.remove_at(index):
            self.bus.publish(Event.ITEMS_CHANGED, self.state.items)

    def clear_items(self) -> None:
        self.state.clear()
        self.bus.publish(Event.ITEMS_CHANGED, self.state.items)

    def select_item(self, index: int) -> VideoInfo | None:
        info = self.state.select(index)
        self.bus.publish(Event.ITEM_SELECTED, info)
        return info

    def thumbnail_path(self, info: VideoInfo) -> Path | None:
        if not info or not info.thumbnail_url:
            return None
        return self.thumbnails.fetch(info.thumbnail_url)

    def save_thumbnail(self, info: VideoInfo, dest_path: Path) -> Path:
        """Сохраняет превью видео как PNG/JPEG в указанный файл.

        Может вызываться из фонового потока (см. InfoTab) — не трогает GUI.
        """
        if not info or not info.thumbnail_url:
            raise ThumbnailSaveError("У этого видео нет превью")
        return self.thumbnails.save_as(info.thumbnail_url, Path(dest_path))

    # -- построение заданий -----------------------------------------------
    def build_job(
        self,
        info: VideoInfo,
        mode: str = DownloadMode.VIDEO.value,
        video_format_id: str | None = None,
        audio_format_id: str | None = None,
        container: str | None = None,
        max_height: int | None = None,
        audio_format: str | None = None,
        audio_quality: str | None = None,
        subtitle_mode: str = SubtitleMode.NONE.value,
        subtitle_langs: list[str] | None = None,
        include_auto_subs: bool = False,
        embed_thumbnail: bool | None = None,
        output_dir: str | None = None,
    ) -> Job:
        options = DownloadOptions(
            mode=mode,
            quality=self.settings.default_video_quality,
            max_height=max_height,
            video_format_id=video_format_id or None,
            audio_format_id=audio_format_id or None,
            container=container or (self.settings.default_container if mode == DownloadMode.VIDEO.value else None),
            audio_format=audio_format or self.settings.default_audio_format,
            audio_quality=audio_quality or self.settings.default_audio_quality,
            subtitle_mode=subtitle_mode,
            subtitle_langs=subtitle_langs or [],
            include_auto_subs=include_auto_subs,
            embed_thumbnail=self.settings.embed_thumbnail_default if embed_thumbnail is None else embed_thumbnail,
            embed_metadata=self.settings.embed_metadata_default,
            embed_chapters=self.settings.embed_chapters_default,
            playlist=info.is_playlist,
            output_template=self.settings.output_template or None,
        )
        job = Job(
            url=info.url,
            options=options,
            label=info.title or info.url,
            output_dir=output_dir or self.settings.output_directory or str(self.filesystem.default_download_dir()),
            source=info,
            overwrite_policy=self.settings.overwrite_policy,
        )
        return job

    def validate(self, job: Job) -> ValidationResult:
        return validate_job(job)

    def preview_command(self, job: Job) -> str:
        try:
            base_command = self.ytdlp.base_command()
            output_template = self.filesystem.output_template(job.output_dir, job.options.output_template)
            command = build_command(job, base_command, output_template, self._network_args())
        except (CommandBuildError, RuntimeError, OSError) as exc:
            return f"# {exc}"
        job.command = command
        text = command_to_string(command)
        self.bus.publish(Event.COMMAND_CHANGED, text)
        return text

    # -- очередь ------------------------------------------------------------
    def enqueue(self, job: Job, autostart: bool = True) -> Job:
        self.queue.add(job)
        if autostart:
            self.queue.start()
        return job

    def enqueue_many(self, jobs: list[Job], autostart: bool = True) -> None:
        for job in jobs:
            self.queue.add(job)
        if autostart and jobs:
            self.queue.start()

    def _on_job_finished(self, job: Job) -> None:
        if job.error:
            self._recent_errors.append(f"{job.label}: {job.error.splitlines()[0]}")
            del self._recent_errors[:-10]
        self.bus.publish(Event.JOB_FINISHED, job)

    def open_output_folder(self, job: Job) -> None:
        path = job.primary_output() or Path(job.output_dir)
        open_folder(path)

    # -- обновления yt-dlp ----------------------------------------------------
    def check_updates(self, announce_only_new: bool = False) -> None:
        """Спрашивает GitHub о новых релизах yt-dlp (в фоновом потоке).

        ``announce_only_new`` — режим автопроверки: о версии, про которую
        уже сообщали, второй раз не напоминаем.
        """
        self.bus.publish(Event.UPDATE_CHECK_STARTED)
        threading.Thread(target=self._check_updates, args=(announce_only_new,), daemon=True).start()

    def _check_updates(self, announce_only_new: bool) -> None:
        try:
            release = self.updates.check(self.ytdlp.binaries.ytdlp_version)
        except UpdateError as exc:
            self._remember_error(f"Проверка обновлений: {exc}")
            self.bus.publish(Event.UPDATE_FAILED, str(exc))
            return
        self.update_settings(last_update_check=datetime.now(UTC).isoformat())
        if release is None:
            self.bus.publish(Event.UPDATE_UP_TO_DATE, self.ytdlp.binaries.ytdlp_version)
            return
        if announce_only_new and self.settings.last_notified_release == release.tag:
            log.info("Обновление %s уже показывали, молчим", release.tag)
            return
        self.update_settings(last_notified_release=release.tag)
        self.bus.publish(Event.UPDATE_AVAILABLE, release)

    def load_release_history(self, limit: int = 10, only_new: bool = False) -> None:
        """Готовит список релизов для окна «что нового» (в фоновом потоке)."""
        threading.Thread(
            target=self._load_release_history, args=(limit, only_new), daemon=True
        ).start()

    def _load_release_history(self, limit: int, only_new: bool) -> None:
        try:
            releases = self.updates.history(limit=limit)
        except UpdateError as exc:
            self.bus.publish(Event.UPDATE_FAILED, str(exc))
            return
        if only_new:
            fresh = self.updates.newer_than(releases, self.ytdlp.binaries.ytdlp_version)
            # Ничего нового? Показываем последний релиз: пользователь
            # открыл окно, чтобы что-то прочитать, а не увидеть пустоту.
            releases = fresh or releases[:1]
        self.bus.publish(Event.UPDATE_HISTORY, releases, only_new)

    def update_target_path(self) -> Path:
        """Куда класть скачанный yt-dlp.

        Если текущий бинарник лежит в обычном каталоге — обновляем его на
        месте. Если он взят из вшитой в .exe копии, то писать туда
        бессмысленно (каталог временный и исчезнет), поэтому файл
        кладётся в ``bin`` рядом с приложением: этот каталог приложение
        просматривает раньше вшитой копии.
        """
        current = self.ytdlp.binaries.ytdlp
        bundle = bundle_dir()
        inside_bundle = bool(
            current and bundle and str(current).lower().startswith(str(bundle).lower())
        )
        if current and not inside_bundle:
            return Path(current)
        base = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else PACKAGE_ROOT.parent
        return base / "bin" / asset_name_for_platform()

    def install_update(self, release: ReleaseInfo) -> None:
        """Скачивает и ставит выбранный релиз (в фоновом потоке)."""
        threading.Thread(target=self._install_update, args=(release,), daemon=True).start()

    def _install_update(self, release: ReleaseInfo) -> None:
        target = self.update_target_path()
        try:
            path = self.updates.download(
                release,
                target,
                progress=lambda done, total: self.bus.publish(Event.UPDATE_PROGRESS, done, total),
            )
        except UpdateError as exc:
            self._remember_error(f"Обновление yt-dlp: {exc}")
            self.bus.publish(Event.UPDATE_FAILED, str(exc))
            return
        # Явно закрепляем новый путь в настройках: иначе после перезапуска
        # мог бы снова подхватиться прежний бинарник из другого каталога.
        self.set_tool_paths(str(path), self.settings.ffmpeg_path)
        self.bus.publish(Event.UPDATE_INSTALLED, release, str(path))

    def _remember_error(self, message: str) -> None:
        self._recent_errors.append(message)
        del self._recent_errors[:-10]

    # -- настройки ------------------------------------------------------------
    def update_settings(self, **changes) -> None:
        for key, value in changes.items():
            if hasattr(self.settings, key):
                setattr(self.settings, key, value)
        self.store.save(self.settings)
        self.queue.set_parallel_jobs(self.settings.parallel_jobs)
        if self.translator.language != self.settings.language:
            self.translator.load(self.settings.language)
        self.bus.publish(Event.SETTINGS_CHANGED, self.settings)

    # -- диагностика ------------------------------------------------------------
    def diagnostics(self) -> SystemInfo:
        return SystemInfo(
            app_version=APP_VERSION,
            ytdlp_version=self.ytdlp.binaries.ytdlp_version,
            ffmpeg_version=self.ytdlp.binaries.ffmpeg_version,
            ytdlp_path=str(self.ytdlp.binaries.ytdlp or ""),
            ffmpeg_path=str(self.ytdlp.binaries.ffmpeg or ""),
            free_disk_space=self.filesystem.free_space(
                Path(self.settings.output_directory) if self.settings.output_directory else Path.home()
            ),
            recent_errors=list(self._recent_errors),
        )

    # -- завершение ------------------------------------------------------------
    def shutdown(self) -> None:
        self.queue.shutdown()
        self.store.save(self.settings)
        self.filesystem.cleanup_temp()
