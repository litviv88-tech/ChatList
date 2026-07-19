"""Генерация app.ico: красный круг на синем фоне."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

SIZES: list[tuple[int, int]] = [
    (256, 256),
    (128, 128),
    (64, 64),
    (48, 48),
    (32, 32),
    (16, 16),
]

BACKGROUND_COLOR = (0, 102, 204, 255)
CIRCLE_COLOR = (220, 20, 20, 255)
OUTPUT_NAME = "app.ico"


def create_icon_image(size: tuple[int, int]) -> Image.Image:
    width, height = size
    image = Image.new("RGBA", size, BACKGROUND_COLOR)
    draw = ImageDraw.Draw(image)

    margin = max(1, min(width, height) // 8)
    draw.ellipse(
        (margin, margin, width - margin - 1, height - margin - 1),
        fill=CIRCLE_COLOR,
    )
    return image


def save_app_icon(output_path: Path | None = None) -> Path:
    target = output_path or Path(__file__).resolve().parent / OUTPUT_NAME
    images = [create_icon_image(size) for size in SIZES]

    images[0].save(
        target,
        format="ICO",
        sizes=[(image.width, image.height) for image in images],
        append_images=images[1:],
    )
    return target


def main() -> None:
    icon_path = save_app_icon()
    print(f"Иконка создана: {icon_path}")
    print("Размеры:", ", ".join(f"{w}x{h}" for w, h in SIZES))


if __name__ == "__main__":
    main()
