"""Классификация типовых ошибок yt-dlp по логу stderr."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ErrorCategory(str, Enum):
    UNSUPPORTED_URL = "unsupported_url"
    UNAVAILABLE = "unavailable"
    NETWORK = "network"
    FORBIDDEN = "forbidden"
    RATE_LIMITED = "rate_limited"
    FFMPEG_MISSING = "ffmpeg_missing"
    LOGIN_REQUIRED = "login_required"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


_PATTERNS: tuple[tuple[str, ErrorCategory, str], ...] = (
    ("Unsupported URL", ErrorCategory.UNSUPPORTED_URL, "Эта ссылка не поддерживается yt-dlp."),
    ("is not a valid URL", ErrorCategory.UNSUPPORTED_URL, "Некорректная ссылка."),
    ("Video unavailable", ErrorCategory.UNAVAILABLE, "Видео недоступно (удалено или скрыто)."),
    ("This video is private", ErrorCategory.UNAVAILABLE, "Видео приватное."),
    ("This live event", ErrorCategory.UNAVAILABLE, "Трансляция ещё не началась или уже завершена."),
    ("Sign in to confirm", ErrorCategory.LOGIN_REQUIRED, "Требуется авторизация — укажите cookies в настройках (из браузера или файлом)."),
    ("age-restricted", ErrorCategory.LOGIN_REQUIRED, "Видео с возрастным ограничением — нужны cookies (из браузера или файлом)."),
    ("HTTP Error 403", ErrorCategory.FORBIDDEN, "Доступ запрещён сервером (403)."),
    ("HTTP Error 429", ErrorCategory.RATE_LIMITED, "Слишком много запросов — попробуйте позже."),
    ("Too Many Requests", ErrorCategory.RATE_LIMITED, "Слишком много запросов — попробуйте позже."),
    ("ffmpeg not found", ErrorCategory.FFMPEG_MISSING, "Не найден FFmpeg — укажите путь в настройках."),
    ("Postprocessing: ffprobe", ErrorCategory.FFMPEG_MISSING, "Не найден FFmpeg/FFprobe."),
    ("Unable to download webpage", ErrorCategory.NETWORK, "Нет соединения с сервером."),
    ("getaddrinfo failed", ErrorCategory.NETWORK, "Ошибка сети: не удалось определить адрес сервера."),
    ("Connection", ErrorCategory.NETWORK, "Проблема с сетевым соединением."),
)


@dataclass
class AnalyzedError:
    category: ErrorCategory
    reason: str
    raw: str = ""

    def report(self) -> str:
        if self.raw and self.raw != self.reason:
            return f"{self.reason}\n\n{self.raw}"
        return self.reason


def analyze(stderr_text: str, returncode: int) -> AnalyzedError:
    tail_lines = [line for line in (stderr_text or "").splitlines() if line.strip()]
    error_lines = [line for line in tail_lines if "ERROR" in line]
    haystack = "\n".join(error_lines or tail_lines[-10:])

    for pattern, category, message in _PATTERNS:
        if pattern.lower() in haystack.lower():
            return AnalyzedError(category, message, raw="\n".join(error_lines[-5:]) or haystack)

    last_error = error_lines[-1] if error_lines else (tail_lines[-1] if tail_lines else f"Код выхода {returncode}")
    return AnalyzedError(ErrorCategory.UNKNOWN, last_error, raw="\n".join(tail_lines[-10:]))
