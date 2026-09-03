"""Модель обновлений: версии, сведения о релизе и разбор описания.

Чистый слой без ввода-вывода: сюда приходит текст (тег версии, тело
релиза в Markdown), отсюда уходят данные, которые окно умеет показать.
Повторяет ``domain/version.py`` и ``domain/release_notes.py`` ZapretGUI.

Версии yt-dlp — календарные (``2026.08.19``), у ночных сборок добавляется
четвёртая часть (``2026.08.19.232815``), поэтому сравнение покомпонентное,
а не лексикографическое: «2026.9.1» новее «2026.08.19», хотя строкой
меньше.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from functools import total_ordering

# ---------------------------------------------------------------------------
# Версия
# ---------------------------------------------------------------------------

_VERSION_PATTERN = re.compile(
    r"""^\s*v?
    (?P<major>\d+)
    (?:\.(?P<minor>\d+))?
    (?:\.(?P<patch>\d+))?
    (?:\.(?P<build>\d+))?
    (?:[-+](?P<pre>[0-9A-Za-z.\-+]+))?
    \s*$""",
    re.VERBOSE,
)


@total_ordering
@dataclass(frozen=True, slots=True)
class Version:
    major: int
    minor: int = 0
    patch: int = 0
    build: int = 0
    pre: str = ""
    raw: str = ""

    @classmethod
    def parse(cls, text: str) -> "Version | None":
        """Возвращает ``None`` вместо исключения: неразбираемая версия —
        это данные, а не ошибка программы."""
        if not text:
            return None
        match = _VERSION_PATTERN.match(text.strip())
        if not match:
            return None
        return cls(
            major=int(match["major"]),
            minor=int(match["minor"] or 0),
            patch=int(match["patch"] or 0),
            build=int(match["build"] or 0),
            pre=(match["pre"] or "").lower(),
            raw=text.strip(),
        )

    @property
    def _key(self) -> tuple[int, int, int, int]:
        return (self.major, self.minor, self.patch, self.build)

    @property
    def is_prerelease(self) -> bool:
        return bool(self.pre)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return self._key == other._key and self.pre == other.pre

    def __lt__(self, other: "Version") -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        if self._key != other._key:
            return self._key < other._key
        # Предрелиз идёт раньше финальной версии: 2026.8.19-rc1 < 2026.8.19.
        if self.pre and not other.pre:
            return True
        if not self.pre and other.pre:
            return False
        return self.pre < other.pre

    def __hash__(self) -> int:
        return hash((self._key, self.pre))

    def __str__(self) -> str:
        text = f"{self.major}.{self.minor}.{self.patch}"
        if self.build:
            text += f".{self.build}"
        if self.pre:
            text += f"-{self.pre}"
        return text


def is_newer(candidate: str, current: str) -> bool:
    """Строго ли ``candidate`` новее ``current``.

    Неразбираемая текущая версия означает «неизвестно» — тогда побеждает
    любая разобранная версия-кандидат.
    """
    new = Version.parse(candidate)
    if new is None:
        return False
    old = Version.parse(current)
    return old is None or new > old


# ---------------------------------------------------------------------------
# Сведения о релизе
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ReleaseInfo:
    """Один релиз yt-dlp: что за версия, когда вышла и что в ней."""

    tag: str
    version: Version | None = None
    published_at: datetime | None = None
    notes: str = ""
    html_url: str = ""
    asset_name: str = ""
    asset_url: str = ""
    asset_size: int = 0
    #: Ожидаемая SHA-256 из файла контрольных сумм релиза (если он есть).
    sha256: str = ""
    prerelease: bool = False

    @property
    def version_text(self) -> str:
        """Тег как есть: «2026.09.01», а не нормализованное «2026.9.1».

        Сравниваем версии разобранными, а показываем — опубликованные:
        пользователь ищет глазами ровно ту строку, что стоит в релизе.
        """
        return self.tag or (str(self.version) if self.version else "")

    @property
    def date_text(self) -> str:
        return self.published_at.strftime("%Y-%m-%d") if self.published_at else ""

    @property
    def is_installable(self) -> bool:
        return bool(self.asset_url)

    def sections(self) -> "tuple[NoteSection, ...]":
        return parse_release_notes(self.notes)


# ---------------------------------------------------------------------------
# Разбор описания релиза (GitHub-flavoured Markdown)
# ---------------------------------------------------------------------------

#: Вложенность глубже этой схлопывается: окно — не многоуровневый план.
MAX_LEVEL = 1
#: Дальше описание перестают читать и начинают пролистывать.
MAX_ITEMS = 40

_HEADING = re.compile(r"^#{1,6}\s+(?P<title>.+?)\s*#*$")
#: Тело релиза — не веб-страница: теги в нём это обёртки, а не содержание.
#: yt-dlp прячет changelog в <details><summary><h3>…</h3></summary>, и без
#: этих двух правил окно показывало бы разметку вместо списка изменений.
_HTML_HEADING = re.compile(r"<\s*(summary|h[1-6])\b[^>]*>", re.IGNORECASE)
_HTML_TAG = re.compile(r"<[^>\n]{1,200}>")
#: Картинки-бейджи («Installation», «Discord», «Donate») — украшение шапки.
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_BULLET = re.compile(r"^(?P<indent>[ \t]*)[-*+]\s+(?P<text>.+)$")
_LINK = re.compile(r"\[(?P<text>[^\]]*)\]\((?P<url>[^)]*)\)")
_BARE_URL = re.compile(r"https?://\S+")
#: Курсив/жирный звёздочками и код в обратных кавычках. Подчёркивания трогаем
#: только вокруг слова целиком: «ip_id» и «--no-cookies» — это имена, не курсив.
_EMPHASIS = re.compile(r"(\*\*\*|\*\*|\*|`)")
_UNDERSCORE_EMPHASIS = re.compile(r"(?<!\w)(__?)(?=\S)(.+?)(?<=\S)\1(?!\w)")
_WHITESPACE = re.compile(r"\s+")
#: «by @someone in https://…/pull/123» — автора оставляем, ссылку убираем.
_TRAILING_REF = re.compile(r"\s+in\s+https?://\S+$", re.IGNORECASE)
#: Строки, существующие только ради ссылки в другое место.
_LINK_ONLY_LINE = re.compile(r"^\**\s*(full changelog|changelog|see also)\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class NoteItem:
    """Одна строка описания; ``level`` — глубина вложенности."""

    text: str
    level: int = 0


@dataclass(frozen=True, slots=True)
class NoteSection:
    """Заголовок и строки под ним. У преамбулы ``title`` пустой."""

    title: str
    items: tuple[NoteItem, ...] = field(default_factory=tuple)

    def __bool__(self) -> bool:
        return bool(self.items)


def parse_release_notes(markdown: str, *, max_items: int = MAX_ITEMS) -> tuple[NoteSection, ...]:
    """Делит тело релиза на показываемые разделы. Не бросает исключений."""
    sections: list[tuple[str, list[NoteItem]]] = []
    current: tuple[str, list[NoteItem]] = ("", [])
    sections.append(current)
    total = 0

    for raw_line in (markdown or "").splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue

        stripped = line.strip()
        heading = _HEADING.match(stripped)
        if heading:
            current = (clean_text(heading.group("title")), [])
            sections.append(current)
            continue

        # <summary><h3>Changelog</h3></summary> — тоже заголовок раздела.
        if _HTML_HEADING.search(stripped):
            title = clean_text(stripped)
            if title:
                current = (title, [])
                sections.append(current)
            continue

        if total >= max_items:
            break
        item = _as_item(line)
        if item is not None:
            current[1].append(item)
            total += 1

    return tuple(NoteSection(title, tuple(items)) for title, items in sections if items)


def clean_text(text: str) -> str:
    """Markdown до слов: без выделения, кавычек кода, тегов и голых ссылок."""
    without_images = _IMAGE.sub("", text)
    without_tags = _HTML_TAG.sub("", without_images)
    # От ссылки остаётся только её текст. Ссылка без текста — это остаток
    # картинки-бейджа в шапке релиза; подставлять вместо неё адрес значило
    # бы показывать в списке изменений строку вида "Discord" из title.
    without_links = _LINK.sub(lambda m: m.group("text"), without_tags)
    without_refs = _TRAILING_REF.sub("", without_links)
    plain = _UNDERSCORE_EMPHASIS.sub(lambda m: m.group(2), without_refs)
    plain = _EMPHASIS.sub("", plain)
    plain = _BARE_URL.sub("", plain)
    return _WHITESPACE.sub(" ", plain).strip(" -–—:;,")


def summarize(sections: tuple[NoteSection, ...], limit: int = 3) -> str:
    """Первые несколько строк — для строки состояния."""
    lines = [item.text for section in sections for item in section.items][:limit]
    return "   •   ".join(lines)


def _as_item(line: str) -> NoteItem | None:
    bullet = _BULLET.match(line)
    if bullet:
        indent = bullet.group("indent").replace("\t", "  ")
        level = min(len(indent) // 2, MAX_LEVEL)
        text = clean_text(bullet.group("text"))
    else:
        stripped = line.strip()
        if _LINK_ONLY_LINE.match(stripped):
            return None
        level = 0
        text = clean_text(stripped)
    # Остатки разметки — одинокая решётка, линия из дефисов, звёздочки —
    # это оформление, а не содержание.
    return NoteItem(text=text, level=level) if _has_words(text) else None


def _has_words(text: str) -> bool:
    return any(char.isalnum() for char in text)
