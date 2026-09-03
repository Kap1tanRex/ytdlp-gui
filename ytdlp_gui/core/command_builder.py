"""Сборка аргументов командной строки yt-dlp из :class:`Job`.

Не запускает процессы — только строит список аргументов. Выполнением
занимается ``services.process_manager``.
"""

from __future__ import annotations

from .models import DownloadMode, Job, SubtitleMode

# Префиксы, которыми помечаются служебные строки в stdout, чтобы их можно
# было надёжно отличить от обычных информационных строк yt-dlp.
PROGRESS_PREFIX = "YTGUI-PROG:"
POSTPROCESS_PREFIX = "YTGUI-POST:"


class CommandBuildError(Exception):
    pass


def command_to_string(command: list[str]) -> str:
    parts = []
    for part in command:
        if " " in part or part == "":
            parts.append(f'"{part}"')
        else:
            parts.append(part)
    return " ".join(parts)


def _video_format_string(job: Job) -> str:
    opts = job.options
    video_id = (opts.video_format_id or "").strip()
    audio_id = (opts.audio_format_id or "").strip()

    if video_id and audio_id:
        return f"{video_id}+{audio_id}/{video_id}/best"
    if video_id:
        return f"{video_id}+bestaudio/{video_id}/best"

    height_filter = f"[height<={opts.max_height}]" if opts.max_height else ""
    if audio_id:
        return f"bestvideo{height_filter}+{audio_id}/best{height_filter}"

    quality = (opts.quality or "best").lower()
    if quality == "worst":
        return f"worstvideo+worstaudio/worst"
    return f"bestvideo{height_filter}+bestaudio/best{height_filter}"


def build(
    job: Job,
    base_command: list[str],
    output_template: str,
    network_args: list[str] | None = None,
    final_path_file: str | None = None,
) -> list[str]:
    """Возвращает полную командную строку для запуска.

    ``final_path_file``, если указан, — путь к файлу, куда yt-dlp допишет
    точный путь итогового файла после слияния/постобработки (событие
    ``after_move``). Раньше этот путь печатался в stdout через ``--print``
    вместе с прогрессом — из-за особенности yt-dlp это заставляло его
    буферизовать ВЕСЬ стандартный вывод (включая прогресс загрузки) до
    самого события ``after_move``, из-за чего прогресс-бар в GUI не
    обновлялся всю загрузку и «прыгал» на 100% лишь в конце.
    ``--print-to-file`` пишет в отдельный файл, не трогая stdout, поэтому
    прогресс снова стримится нормально.
    """
    if not job.url.strip():
        raise CommandBuildError("Не указана ссылка на видео")

    opts = job.options
    args: list[str] = list(base_command)
    args += ["--newline", "--no-warnings", "--no-color"]
    args += ["--progress-template", f"download:{PROGRESS_PREFIX}%(progress)j"]
    args += ["--progress-template", f"postprocess:{POSTPROCESS_PREFIX}%(progress)j"]
    if final_path_file:
        args += ["--print-to-file", "after_move:%(filepath)s", final_path_file]
    args += ["-o", output_template]
    args += ["--yes-playlist"] if opts.playlist else ["--no-playlist"]

    if opts.mode == DownloadMode.AUDIO.value:
        args += ["-x", "--audio-format", opts.audio_format]
        if opts.audio_format != "best":
            args += ["--audio-quality", str(opts.audio_quality)]
        args += ["-f", opts.audio_format_id or "bestaudio/best"]
    else:
        args += ["-f", _video_format_string(job)]
        if opts.container:
            args += ["--merge-output-format", opts.container]

    _add_subtitle_args(args, opts)

    if opts.embed_thumbnail:
        args.append("--embed-thumbnail")
    if opts.embed_metadata:
        args.append("--embed-metadata")
    if opts.embed_chapters:
        args.append("--embed-chapters")

    if job.overwrite_policy == "overwrite":
        args.append("--force-overwrites")
    else:
        args.append("--no-overwrites")

    if network_args:
        args += network_args

    args.append(job.url)
    return args


def _add_subtitle_args(args: list[str], opts) -> None:
    mode = opts.subtitle_mode
    if mode == SubtitleMode.NONE.value:
        return

    langs = ",".join(opts.subtitle_langs) if opts.subtitle_langs else "all"
    args += ["--sub-langs", langs, "--sub-format", opts.subtitle_format or "srt/best"]
    if opts.include_auto_subs:
        args.append("--write-auto-subs")

    if mode == SubtitleMode.EMBED.value:
        args += ["--write-subs", "--embed-subs"]
    elif mode == SubtitleMode.EXTERNAL.value:
        args.append("--write-subs")
    elif mode == SubtitleMode.BOTH.value:
        args += ["--write-subs", "--embed-subs"]


def build_probe_args(url: str, playlist: bool = False) -> list[str]:
    args = ["-J", "--no-warnings"]
    args += ["--yes-playlist"] if playlist else ["--no-playlist"]
    args.append(url)
    return args
