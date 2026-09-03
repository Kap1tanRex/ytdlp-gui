"""Доменная модель приложения.

Модуль не должен зависеть ни от GUI, ни от subprocess — только чистые
структуры данных и функции форматирования, аналогично core/models.py
в ffmpeg_gui.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

# ---------------------------------------------------------------------------
# Форматирование
# ---------------------------------------------------------------------------


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "--:--:--"
    seconds = max(0.0, float(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours >= 1:
        return f"{int(hours):02d}:{int(minutes):02d}:{int(secs):02d}"
    return f"{int(minutes):02d}:{int(secs):02d}"


def format_size(num_bytes: int | float | None) -> str:
    if not num_bytes:
        return "—"
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024.0 or unit == "TB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def format_speed(bytes_per_second: float | None) -> str:
    if not bytes_per_second:
        return "—"
    return f"{format_size(bytes_per_second)}/s"


def format_eta(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    return format_duration(seconds)


def format_bitrate_kbps(kbps: float | None) -> str:
    if not kbps:
        return "—"
    if kbps >= 1000:
        return f"{kbps / 1000:.2f} Mbps"
    return f"{kbps:.0f} kbps"


# ---------------------------------------------------------------------------
# Информация о видео (результат `yt-dlp -J <url>`)
# ---------------------------------------------------------------------------


@dataclass
class MediaFormat:
    """Один доступный формат (строка из массива ``formats`` yt-dlp)."""

    format_id: str
    ext: str = ""
    vcodec: str | None = None
    acodec: str | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    tbr: float | None = None  # суммарный битрейт, kbps
    vbr: float | None = None
    abr: float | None = None
    filesize: int | None = None
    filesize_approx: int | None = None
    format_note: str = ""
    language: str | None = None
    protocol: str = ""
    dynamic_range: str | None = None
    asr: int | None = None

    @property
    def has_video(self) -> bool:
        return bool(self.vcodec) and self.vcodec != "none"

    @property
    def has_audio(self) -> bool:
        return bool(self.acodec) and self.acodec != "none"

    @property
    def is_video_only(self) -> bool:
        return self.has_video and not self.has_audio

    @property
    def is_audio_only(self) -> bool:
        return self.has_audio and not self.has_video

    @property
    def is_progressive(self) -> bool:
        """И видео, и аудио уже смешаны в одном потоке."""
        return self.has_video and self.has_audio

    @property
    def size(self) -> int | None:
        return self.filesize or self.filesize_approx

    @property
    def resolution_text(self) -> str:
        if self.has_video and self.width and self.height:
            label = f"{self.width}×{self.height}"
            if self.fps:
                label += f" {self.fps:g}fps"
            if self.dynamic_range and self.dynamic_range != "SDR":
                label += f" {self.dynamic_range}"
            return label
        if self.has_audio and not self.has_video:
            return "аудио"
        return "—"

    @property
    def bitrate_text(self) -> str:
        rate = self.tbr or self.vbr or self.abr
        return format_bitrate_kbps(rate)

    def describe(self) -> str:
        """Строка для выпадающего списка выбора формата."""
        parts = [f"{self.format_id}", self.ext.upper() or "?"]
        if self.has_video:
            parts.append(self.resolution_text)
            if self.vcodec:
                parts.append(self.vcodec.split(".")[0])
        if self.has_audio:
            if self.language:
                parts.append(f"[{self.language}]")
            if self.acodec:
                parts.append(self.acodec.split(".")[0])
            if self.abr:
                parts.append(f"{self.abr:.0f}k")
        if self.format_note:
            parts.append(f"({self.format_note})")
        size = self.size
        if size:
            parts.append(format_size(size))
        return " ".join(str(p) for p in parts if p)


@dataclass
class SubtitleTrack:
    lang: str
    name: str = ""
    ext: str = "srt"
    auto: bool = False

    def describe(self) -> str:
        kind = " (авто)" if self.auto else ""
        return f"{self.name or self.lang} [{self.lang}]{kind}"


@dataclass
class VideoInfo:
    """Результат разбора JSON-вывода ``yt-dlp -J``."""

    url: str
    id: str = ""
    title: str = ""
    webpage_url: str = ""
    extractor: str = ""
    duration: float | None = None
    uploader: str = ""
    upload_date: str = ""
    view_count: int | None = None
    thumbnail_url: str = ""
    description: str = ""
    formats: list[MediaFormat] = field(default_factory=list)
    subtitles: dict[str, list[SubtitleTrack]] = field(default_factory=dict)
    is_playlist: bool = False
    playlist_count: int | None = None
    playlist_title: str = ""
    raw: dict = field(default_factory=dict)
    probe_error: str | None = None

    @property
    def is_valid(self) -> bool:
        return self.probe_error is None and (bool(self.formats) or self.is_playlist)

    @property
    def video_formats(self) -> list[MediaFormat]:
        return [f for f in self.formats if f.has_video]

    @property
    def audio_formats(self) -> list[MediaFormat]:
        return [f for f in self.formats if f.is_audio_only]

    @property
    def progressive_formats(self) -> list[MediaFormat]:
        return [f for f in self.formats if f.is_progressive]

    @property
    def has_subtitles(self) -> bool:
        return any(not track.auto for tracks in self.subtitles.values() for track in tracks)

    @property
    def has_auto_subtitles(self) -> bool:
        return any(track.auto for tracks in self.subtitles.values() for track in tracks)

    @property
    def subtitle_languages(self) -> list[str]:
        return sorted(self.subtitles.keys())

    def duration_text(self) -> str:
        return format_duration(self.duration)

    def summary_line(self) -> str:
        if self.probe_error:
            return f"{self.url}   •   ошибка: {self.probe_error}"
        if self.is_playlist:
            count = self.playlist_count if self.playlist_count is not None else "?"
            return f"{self.playlist_title or self.title or self.url}   •   плейлист, {count} видео"
        parts = [self.title or self.id or self.url]
        if self.uploader:
            parts.append(self.uploader)
        parts.append(self.duration_text())
        return "   ".join(parts)


# ---------------------------------------------------------------------------
# Параметры и задание загрузки
# ---------------------------------------------------------------------------


class DownloadMode(str, Enum):
    VIDEO = "video"
    AUDIO = "audio"


class SubtitleMode(str, Enum):
    NONE = "none"
    EMBED = "embed"
    EXTERNAL = "external"
    BOTH = "both"


class OverwritePolicy(str, Enum):
    OVERWRITE = "overwrite"
    SKIP = "skip"
    ASK = "ask"


class JobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    POSTPROCESSING = "POSTPROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SKIPPED = "SKIPPED"


@dataclass
class DownloadOptions:
    mode: str = DownloadMode.VIDEO.value

    # видео
    quality: str = "best"  # best | manual (используется, когда video_format_id пуст)
    max_height: int | None = None
    video_format_id: str | None = None
    audio_format_id: str | None = None  # выбор звуковой дорожки (язык) для видео-режима
    container: str | None = None  # merge-output-format: mp4 | mkv | webm

    # аудио (режим "только аудио")
    audio_format: str = "mp3"  # mp3 | m4a | opus | flac | wav | best
    audio_quality: str = "192"  # kbps, "0" = лучшее

    # субтитры
    subtitle_mode: str = SubtitleMode.NONE.value
    subtitle_langs: list[str] = field(default_factory=list)
    include_auto_subs: bool = False
    subtitle_format: str = "srt/best"

    # доп. вложения
    embed_thumbnail: bool = False
    embed_metadata: bool = True
    embed_chapters: bool = True

    output_template: str | None = None
    playlist: bool = False


@dataclass
class Job:
    """Единица работы очереди загрузок."""

    url: str
    options: DownloadOptions = field(default_factory=DownloadOptions)

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    label: str = ""
    output_dir: str = ""

    source: VideoInfo | None = None
    overwrite_policy: str = OverwritePolicy.ASK.value

    status: str = JobStatus.PENDING.value
    stage_text: str = ""
    progress: float = 0.0
    downloaded_bytes: int | None = None
    total_bytes: int | None = None
    speed: float | None = None
    eta: float | None = None

    error: str | None = None
    error_category: str | None = None
    command: list[str] = field(default_factory=list)
    log_path: str | None = None
    output_files: list[str] = field(default_factory=list)

    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    finished_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.label:
            self.label = (self.source.title if self.source and self.source.title else self.url)

    @property
    def is_active(self) -> bool:
        return self.status in (JobStatus.RUNNING.value, JobStatus.POSTPROCESSING.value)

    @property
    def is_finished(self) -> bool:
        return self.status in (
            JobStatus.COMPLETED.value,
            JobStatus.FAILED.value,
            JobStatus.CANCELLED.value,
            JobStatus.SKIPPED.value,
        )

    def status_title(self) -> str:
        titles = {
            JobStatus.PENDING.value: "Ожидание",
            JobStatus.RUNNING.value: "Загрузка",
            JobStatus.POSTPROCESSING.value: "Обработка",
            JobStatus.COMPLETED.value: "Завершено",
            JobStatus.FAILED.value: "Ошибка",
            JobStatus.CANCELLED.value: "Отменено",
            JobStatus.SKIPPED.value: "Пропущено",
        }
        return titles.get(self.status, self.status)

    def primary_output(self) -> Path | None:
        return Path(self.output_files[0]) if self.output_files else None


@dataclass
class ProgressInfo:
    """Разобранный JSON-блок из ``--progress-template``."""

    status: str = ""
    downloaded_bytes: int | None = None
    total_bytes: int | None = None
    fragment_index: int | None = None
    fragment_count: int | None = None
    speed: float | None = None
    eta: float | None = None
    elapsed: float | None = None
    filename: str | None = None
    fraction: float = 0.0

    def human(self) -> str:
        size = (
            f"{format_size(self.downloaded_bytes)} / {format_size(self.total_bytes)}"
            if self.total_bytes
            else format_size(self.downloaded_bytes)
        )
        percent = f"{self.fraction * 100:.1f}%" if self.total_bytes else ""
        lines = [percent] if percent else []
        lines.append(size)
        lines.append(f"Скорость: {format_speed(self.speed)}")
        lines.append(f"Осталось: {format_eta(self.eta)}")
        return "\n".join(lines)


@dataclass
class ResultInfo:
    """Итоговая сводка по завершённой загрузке."""

    output_files: list[str] = field(default_factory=list)
    total_size: int = 0
    processing_time: float = 0.0
    average_speed: float | None = None
    title: str = ""

    def report(self) -> str:
        speed = format_speed(self.average_speed)
        lines = ["✓ Готово!", ""]
        lines.append(f"{'Название:':<14}{self.title or '—'}")
        lines.append(f"{'Размер:':<14}{format_size(self.total_size)}")
        lines.append(f"{'Время:':<14}{format_duration(self.processing_time)}")
        lines.append(f"{'Скорость:':<14}{speed}")
        if self.output_files:
            lines.append("")
            lines.append("Файлы:")
            for path in self.output_files:
                lines.append(f"  - {Path(path).name}")
        return "\n".join(lines)
