"""Значок приложения в стиле «Стемницы» (design-system §10.2).

Скруглённый квадрат цвета ``BG2`` с волосяной рамкой ``LINE2``, на нём
янтарная стрелка вниз на светлую черту — значок «скачать» из набора
интерфейса. Рисуется с четырёхкратным запасом и уменьшается под каждый
размер, чтобы края оставались гладкими.

    python tools/make_icon.py

Результат — ``ytdlp_gui/resources/app.ico`` (16…256 px).
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "ytdlp_gui" / "resources" / "app.ico"

BG2 = (0x1B, 0x18, 0x15, 255)
LINE2 = (0x3B, 0x34, 0x2D, 255)
AMBER = (0xE8, 0xA3, 0x3D, 255)
TXT = (0xE8, 0xE1, 0xD3, 255)

SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
SUPERSAMPLE = 4


def draw(size: int) -> Image.Image:
    scale = size * SUPERSAMPLE / 256
    canvas = Image.new("RGBA", (round(256 * scale),) * 2, (0, 0, 0, 0))
    pen = ImageDraw.Draw(canvas)

    def box(*values: float) -> list[float]:
        return [value * scale for value in values]

    # Мелким размерам рамка только мешает — остаётся одна плашка.
    border = 8 if size >= 32 else 0
    pen.rounded_rectangle(box(4, 4, 252, 252), radius=56 * scale, fill=LINE2 if border else BG2)
    if border:
        inner = box(4 + border, 4 + border, 252 - border, 252 - border)
        pen.rounded_rectangle(inner, radius=50 * scale, fill=BG2)

    # Стрелка: толще на мелких размерах, чтобы читалась.
    stem = 30 if size >= 32 else 40
    pen.rounded_rectangle(box(128 - stem / 2, 52, 128 + stem / 2, 150), radius=stem / 2 * scale, fill=AMBER)
    pen.polygon(box(70, 120, 186, 120, 128, 180), fill=AMBER)
    bar = 20 if size >= 32 else 28
    pen.rounded_rectangle(box(62, 198, 194, 198 + bar), radius=bar / 2 * scale, fill=TXT)

    return canvas.resize((size, size), Image.LANCZOS)


def main() -> None:
    images = [draw(size) for size in SIZES]
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    images[-1].save(TARGET, format="ICO", sizes=[(s, s) for s in SIZES], append_images=images[:-1])
    print(f"{TARGET} — {', '.join(map(str, SIZES))} px")


if __name__ == "__main__":
    main()
