"""Числа, размеры и время так, как их пишет интерфейс (design-system §4.3).

Между числом и единицей — неразрывный пробел, единицы русские, минус
типографский, разделитель в строках данных — средняя точка. Ядро
(``core.models``) форматирует по-своему для логов и отчётов; здесь —
только то, что видит пользователь.
"""

from __future__ import annotations

#: Между числом и единицей. Документ «Стемницы» просит узкий пробел, но в
#: IBM Plex Mono его нет, и Tk подставляет почти невидимый глиф из другого
#: шрифта — поэтому неразрывный пробел обычной ширины.
THIN = "\u00a0"
MINUS = "\u2212"
DOT = " · "

_SIZE_UNITS = ("Б", "КБ", "МБ", "ГБ", "ТБ")


def size(num_bytes: float | None) -> str:
    """``704.6 МБ``; пустое или нулевое — прочерк."""
    if not num_bytes:
        return "—"
    value = float(num_bytes)
    for unit in _SIZE_UNITS:
        if abs(value) < 1024 or unit == _SIZE_UNITS[-1]:
            return f"{int(value)}{THIN}{unit}" if unit == "Б" else f"{value:.1f}{THIN}{unit}"
        value /= 1024
    return "—"  # pragma: no cover - цикл всегда возвращает значение


def speed(bytes_per_second: float | None) -> str:
    return f"{size(bytes_per_second)}/с" if bytes_per_second else "—"


def clock(seconds: float | None) -> str:
    """``3:33`` или ``1:02:03``."""
    if seconds is None:
        return "—"
    total = max(0, int(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def remaining(seconds: float | None) -> str:
    """``осталось 0:11`` или ``осталось 2 ч 05 мин``."""
    if seconds is None:
        return ""
    total = max(0, int(seconds))
    if total >= 3600:
        hours, rest = divmod(total, 3600)
        return f"осталось {hours}{THIN}ч {rest // 60:02d}{THIN}мин"
    return f"осталось {clock(total)}"


def percent(fraction: float) -> str:
    return f"{max(0.0, min(1.0, fraction)) * 100:.0f}{THIN}%"


def plural_word(count: int, one: str, few: str, many: str) -> str:
    """Форма слова для числа: файл / файла / файлов."""
    tail = abs(count) % 100
    if 11 <= tail <= 14:
        return many
    if tail % 10 == 1:
        return one
    if 2 <= tail % 10 <= 4:
        return few
    return many


def plural(count: int, one: str, few: str, many: str) -> str:
    """Число со словом: 1 файл, 2 файла, 5 файлов."""
    return f"{count} {plural_word(count, one, few, many)}"


def date(yyyymmdd: str) -> str:
    """``20260512`` → ``12.05.2026``; иначе пустая строка."""
    if len(yyyymmdd or "") != 8 or not yyyymmdd.isdigit():
        return ""
    return f"{yyyymmdd[6:8]}.{yyyymmdd[4:6]}.{yyyymmdd[0:4]}"


def grouped(number: int) -> str:
    """``1 234 567`` — разряды через узкий пробел."""
    return f"{number:,}".replace(",", THIN)


def join(*parts: str) -> str:
    """Склеивает непустые части через среднюю точку."""
    return DOT.join(part for part in parts if part)
