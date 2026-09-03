"""Получение сведений о видео/плейлисте через ``yt-dlp -J``.

Аналог ffprobe_service.py из ffmpeg_gui: превращает JSON-вывод внешнего
инструмента в доменную модель (core.models.VideoInfo).
"""

from __future__ import annotations

import json
import logging
import subprocess

from ..core.models import MediaFormat, SubtitleTrack, VideoInfo
from .ytdlp_service import YtdlpService, creation_flags, subprocess_env

log = logging.getLogger(__name__)

PROBE_TIMEOUT = 60


class InfoService:
    def __init__(self, ytdlp: YtdlpService) -> None:
        self.ytdlp = ytdlp

    def probe(self, url: str, playlist: bool = False, extra_args: list[str] | None = None) -> VideoInfo:
        url = url.strip()
        if not self.ytdlp.available:
            return VideoInfo(url=url, probe_error="yt-dlp не найден")

        args = ["-J", "--no-warnings"]
        args += ["--yes-playlist"] if playlist else ["--no-playlist"]
        if extra_args:
            args += extra_args
        args.append(url)

        try:
            result = subprocess.run(
                self.ytdlp.base_command() + args,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=PROBE_TIMEOUT,
                creationflags=creation_flags(),
                env=subprocess_env(),
            )
        except subprocess.TimeoutExpired:
            return VideoInfo(url=url, probe_error="Превышено время ожидания ответа")
        except OSError as exc:
            return VideoInfo(url=url, probe_error=str(exc))

        if result.returncode != 0 or not result.stdout.strip():
            message = _last_error_line(result.stderr) or "Не удалось получить сведения о видео"
            return VideoInfo(url=url, probe_error=message)

        try:
            data = json.loads(result.stdout)
        except (json.JSONDecodeError, ValueError) as exc:
            return VideoInfo(url=url, probe_error=f"Некорректный ответ yt-dlp: {exc}")

        return parse_info(url, data)


def _last_error_line(stderr: str) -> str:
    for line in reversed((stderr or "").splitlines()):
        line = line.strip()
        if line.startswith("ERROR:"):
            return line[len("ERROR:") :].strip()
        if line:
            return line
    return ""


def parse_info(url: str, data: dict) -> VideoInfo:
    entries = data.get("entries")
    if isinstance(entries, list) and data.get("_type") in ("playlist", "multi_video"):
        return VideoInfo(
            url=url,
            id=str(data.get("id") or ""),
            title=data.get("title") or "",
            webpage_url=data.get("webpage_url") or url,
            extractor=data.get("extractor") or "",
            is_playlist=True,
            playlist_count=data.get("playlist_count") or len([e for e in entries if e]),
            playlist_title=data.get("title") or "",
            raw=data,
        )

    formats = [_parse_format(item) for item in data.get("formats") or []]
    formats = [fmt for fmt in formats if fmt is not None]

    subtitles: dict[str, list[SubtitleTrack]] = {}
    for lang, tracks in (data.get("subtitles") or {}).items():
        subtitles.setdefault(lang, []).extend(_parse_subtitle_tracks(lang, tracks, auto=False))
    for lang, tracks in (data.get("automatic_captions") or {}).items():
        subtitles.setdefault(lang, []).extend(_parse_subtitle_tracks(lang, tracks, auto=True))

    thumbnail = data.get("thumbnail") or ""
    if not thumbnail:
        thumbs = data.get("thumbnails") or []
        if thumbs:
            thumbnail = thumbs[-1].get("url", "")

    return VideoInfo(
        url=url,
        id=str(data.get("id") or ""),
        title=data.get("title") or "",
        webpage_url=data.get("webpage_url") or url,
        extractor=data.get("extractor") or "",
        duration=data.get("duration"),
        uploader=data.get("uploader") or data.get("channel") or "",
        upload_date=data.get("upload_date") or "",
        view_count=data.get("view_count"),
        thumbnail_url=thumbnail,
        description=data.get("description") or "",
        formats=formats,
        subtitles=subtitles,
        raw=data,
    )


def _parse_format(item: dict) -> MediaFormat | None:
    format_id = item.get("format_id")
    if not format_id:
        return None
    return MediaFormat(
        format_id=str(format_id),
        ext=item.get("ext") or "",
        vcodec=item.get("vcodec"),
        acodec=item.get("acodec"),
        width=item.get("width"),
        height=item.get("height"),
        fps=item.get("fps"),
        tbr=item.get("tbr"),
        vbr=item.get("vbr") or None,
        abr=item.get("abr") or None,
        filesize=item.get("filesize"),
        filesize_approx=item.get("filesize_approx"),
        format_note=item.get("format_note") or "",
        language=item.get("language"),
        protocol=item.get("protocol") or "",
        dynamic_range=item.get("dynamic_range"),
        asr=item.get("asr"),
    )


def _parse_subtitle_tracks(lang: str, tracks: list[dict], auto: bool) -> list[SubtitleTrack]:
    seen_ext: set[str] = set()
    result = []
    for track in tracks:
        ext = track.get("ext") or "srt"
        if ext in seen_ext:
            continue
        seen_ext.add(ext)
        result.append(SubtitleTrack(lang=lang, name=track.get("name") or "", ext=ext, auto=auto))
    return result
