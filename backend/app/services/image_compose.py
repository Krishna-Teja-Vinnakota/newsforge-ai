import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from app.agents.provider import GeneratedImage, ImageGenerationError

DISCLOSURE = "AI-generated image — illustrative purposes only."
OUTPUT_WIDTH = 1600
OUTPUT_HEIGHT = 900
# Pillow's built-in font has no em dash, so the exact disclosure text needs a real font (DejaVu Sans, free licence).
FONT_PATH = Path(__file__).resolve().parents[1] / "assets" / "fonts" / "DejaVuSans.ttf"
ALLOWED_TYPES = {"image/png", "image/jpeg", "image/webp"}
# Refuse absurd inputs before decoding; Pillow itself also raises on decompression bombs.
MAX_SOURCE_PIXELS = 40_000_000
Image.MAX_IMAGE_PIXELS = MAX_SOURCE_PIXELS


class InvalidImageError(ImageGenerationError):
    status_code = 502
    user_message = "The image model returned an unusable image. Please try again."


def load_disclosure_font(size: int):
    return ImageFont.truetype(str(FONT_PATH), size)


def compose_hero(generated: GeneratedImage, *, max_bytes: int) -> GeneratedImage:
    """Validate, normalise to 16:9 and stamp the AI disclosure onto the bottom edge."""
    if generated.content_type not in ALLOWED_TYPES:
        raise InvalidImageError()
    if not generated.data or len(generated.data) > max_bytes:
        raise InvalidImageError()
    try:
        source = Image.open(io.BytesIO(generated.data))
        source.load()
    except Exception as error:  # noqa: BLE001 - corrupt data or a decompression bomb
        raise InvalidImageError() from error

    image = ImageOps.exif_transpose(source).convert("RGB")
    image = ImageOps.fit(image, (OUTPUT_WIDTH, OUTPUT_HEIGHT), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))

    # Translucent band across the bottom edge; the prompt asks the model to keep that area calm.
    band_height = round(OUTPUT_HEIGHT * 0.075)
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rectangle((0, OUTPUT_HEIGHT - band_height, OUTPUT_WIDTH, OUTPUT_HEIGHT), fill=(10, 14, 22, 205))
    font = load_disclosure_font(round(band_height * 0.45))
    _, top, right, bottom = draw.textbbox((0, 0), DISCLOSURE, font=font)
    text_x = round(OUTPUT_WIDTH * 0.02)
    text_y = OUTPUT_HEIGHT - band_height + (band_height - (bottom - top)) // 2 - top
    draw.text((text_x, text_y), DISCLOSURE, font=font, fill=(255, 255, 255, 255))
    image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")

    output = io.BytesIO()
    image.save(output, format="JPEG", quality=90, optimize=True)
    return GeneratedImage(data=output.getvalue(), content_type="image/jpeg")
