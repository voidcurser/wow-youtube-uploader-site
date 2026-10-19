"""Grade the original logo to match the forest and move it into the corner."""
from pathlib import Path
from PIL import Image, ImageEnhance, ImageFilter

ROOT = Path(__file__).resolve().parent


def compose():
    with Image.open(ROOT / "JourneyTo60-v2-background.png") as source:
        background = source.convert("RGBA")
    with Image.open(ROOT / "references" / "Forever-official-logo.png") as source:
        logo = source.convert("RGBA")

    logo.thumbnail(
        (round(background.width * 0.245), round(background.height * 0.36)),
        Image.Resampling.LANCZOS,
    )
    alpha = logo.getchannel("A")
    color = ImageEnhance.Color(logo.convert("RGB")).enhance(0.84)
    color = ImageEnhance.Brightness(color).enhance(0.78)
    red, green, blue = color.split()
    # Restrained warmth echoes the sunlight without changing the logo design.
    color = Image.merge("RGB", (
        red.point(lambda value: min(255, round(value * 1.035))),
        green,
        blue.point(lambda value: round(value * 0.96)),
    ))
    logo = color.convert("RGBA")
    logo.putalpha(alpha.point(lambda value: round(value * 0.96)))
    logo = logo.filter(ImageFilter.GaussianBlur(0.20))
    position = (
        background.width - logo.width - round(background.width * 0.025),
        round(background.height * 0.018),
    )
    background.alpha_composite(logo, position)
    result = background.convert("RGB")
    result.save(ROOT / "JourneyTo60-v3.png")
    return result


if __name__ == "__main__":
    result = compose()
    print(f"Saved {ROOT / 'JourneyTo60-v3.png'} ({result.width} x {result.height})")
