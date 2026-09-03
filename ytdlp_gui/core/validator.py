"""Проверка задания перед постановкой в очередь."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from .models import DownloadMode, Job, SubtitleMode


@dataclass
class Issue:
    field: str
    message: str


@dataclass
class ValidationResult:
    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def validate(job: Job) -> ValidationResult:
    result = ValidationResult()
    url = job.url.strip()
    if not url:
        result.errors.append(Issue("url", "Не указана ссылка на видео"))
    elif "://" not in url and not url.startswith("www."):
        result.errors.append(Issue("url", "Ссылка выглядит некорректно"))

    if not job.output_dir:
        result.errors.append(Issue("output_dir", "Не указана папка загрузки"))
    else:
        try:
            os.makedirs(job.output_dir, exist_ok=True)
            if not os.access(job.output_dir, os.W_OK):
                result.errors.append(Issue("output_dir", "Нет прав записи в папку загрузки"))
        except OSError as exc:
            result.errors.append(Issue("output_dir", f"Папка загрузки недоступна: {exc}"))

    opts = job.options
    if opts.mode not in (DownloadMode.VIDEO.value, DownloadMode.AUDIO.value):
        result.errors.append(Issue("mode", "Некорректный режим загрузки"))
    if opts.subtitle_mode not in (
        SubtitleMode.NONE.value,
        SubtitleMode.EMBED.value,
        SubtitleMode.EXTERNAL.value,
        SubtitleMode.BOTH.value,
    ):
        result.errors.append(Issue("subtitle_mode", "Некорректный режим субтитров"))

    return result
