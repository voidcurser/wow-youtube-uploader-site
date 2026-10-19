"""Place Blizzard's original logo onto the approved generated background."""
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent


def compose():
    with Image.open(ROOT / "JourneyTo60-v2-background.png") as source:
        background = source.convert("RGBA")
    with Image.open(ROOT / "references" / "Forever-official-logo.png") as source:
        logo = source.convert("RGBA")
    # Keep original lettering, crest, infinity symbol, colors and aspect ratio.
    # Only resize the supplied logo and alpha-composite it; do not regenerate it.
    logo.thumbnail((round(background.width * 0.27), round(background.height * 0.40)), Image.Resampling.LANCZOS)
    position = (round(background.width * 0.755 - logo.width / 2), round(background.height * 0.025))
    background.alpha_composite(logo, position)
    result = background.convert("RGB")
    result.save(ROOT / "JourneyTo60-v2.png")
    return result


if __name__ == "__main__":
    result = compose()
    print(f"Saved {ROOT / 'JourneyTo60-v2.png'} ({result.width} x {result.height})")
