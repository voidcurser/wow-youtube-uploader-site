
import os
from PIL import Image, ImageDraw, ImageFont, ImageOps

# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = r"C:\Users\giova\Desktop\desktopApp\YouTubeUploader"

TEMPLATES_FOLDER = os.path.join(BASE_DIR, "templates")
ICONS_FOLDER = os.path.join(BASE_DIR, "icons")

SPEC_ASSETS_FOLDER = os.path.join(
    BASE_DIR, "assets", "specs"
)

KEY_ASSETS_FOLDER = os.path.join(
    BASE_DIR, "assets", "keys", "gold"
)

OUTPUT_FOLDER = os.path.join(
    BASE_DIR, "generated_thumbnails"
)

WIDTH = 1280
HEIGHT = 720


# ============================================================
# COLOR THEMES
# ============================================================

# Each color palette contains:
#
# dark  = shadows and outlines
# mid   = main lettering color
# light = bright highlights
#
# The original theme keeps the existing PNG colors.

COLOR_THEMES = {

    "original": {
        "key": None,
        "spec": None,
    },

    "frost": {
        "key": {
            "dark": "#151B32",
            "mid": "#929CC6",
            "light": "#F5F7FF",
        },
        "spec": {
            "dark": "#21163F",
            "mid": "#9274E2",
            "light": "#F0E8FF",
        },
    },

    "ruby": {
        "key": {
            "dark": "#410D16",
            "mid": "#D93E4D",
            "light": "#FFE1A9",
        },
        "spec": {
            "dark": "#35200D",
            "mid": "#DAA048",
            "light": "#FFF4CE",
        },
    },
}


# ============================================================
# PER-DUNGEON LAYOUTS AND THEMES
# ============================================================

# Change the theme of an individual dungeon here.
#
# Available themes:
# original
# frost
# ruby

LAYOUTS = {

    "AltarOfFangs": {
        "theme": "original",
        "key_center": (890, 492),
        "spec_center": (877, 615),
        "icon_center": (675, 620),
    },

    "BlindingVale": {
        "theme": "frost",
        "key_center": (900, 492),
        "spec_center": (887, 615),
        "icon_center": (685, 620),
    },

    "DenOfNalorakk": {
        "theme": "original",
        "key_center": (892, 492),
        "spec_center": (879, 615),
        "icon_center": (677, 620),
    },

    "KingsRest": {
        "theme": "frost",
        "key_center": (900, 492),
        "spec_center": (887, 615),
        "icon_center": (685, 620),
    },

    "MurderRow": {
        "theme": "original",
        "key_center": (890, 492),
        "spec_center": (877, 615),
        "icon_center": (675, 620),
    },

    "RubyLifePools": {
        "theme": "original",
        "key_center": (902, 492),
        "spec_center": (889, 615),
        "icon_center": (687, 620),
    },

    "TempleOfSethraliss": {
        "theme": "frost",
        "key_center": (902, 492),
        "spec_center": (889, 615),
        "icon_center": (687, 620),
    },

    "VoidscarArena": {
        "theme": "ruby",
        "key_center": (895, 492),
        "spec_center": (882, 615),
        "icon_center": (680, 620),
    },
}


DEFAULT_LAYOUT = {
    "theme": "original",
    "key_center": (890, 492),
    "spec_center": (877, 615),
    "icon_center": (675, 620),
}


# ============================================================
# FONT HELPERS
# ============================================================

def get_font(size, style="impact"):

    fonts = {
        "impact": r"C:\Windows\Fonts\impact.ttf",
        "bold": r"C:\Windows\Fonts\arialbd.ttf",
        "regular": r"C:\Windows\Fonts\arial.ttf",
    }

    font_path = fonts.get(style, fonts["bold"])

    if os.path.exists(font_path):
        return ImageFont.truetype(font_path, size)

    return ImageFont.load_default()


# ============================================================
# CENTERED TEXT - FALLBACK
# ============================================================

def draw_centered_text(
    image,
    text,
    area,
    max_font_size,
    color,
    stroke_color,
    stroke_width=2,
    font_style="impact"
):

    draw = ImageDraw.Draw(image)

    x1, y1, x2, y2 = area

    available_width = x2 - x1 - 10
    available_height = y2 - y1 - 6

    font = None
    bbox = None

    for size in range(max_font_size, 10, -1):

        font = get_font(size, font_style)

        bbox = draw.textbbox(
            (0, 0),
            text,
            font=font,
            stroke_width=stroke_width
        )

        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        if (
            text_width <= available_width
            and text_height <= available_height
        ):
            break

    center_x = (x1 + x2) / 2
    center_y = (y1 + y2) / 2

    text_x = center_x - (bbox[0] + bbox[2]) / 2
    text_y = center_y - (bbox[1] + bbox[3]) / 2

    draw.text(
        (round(text_x), round(text_y)),
        text,
        font=font,
        fill=color,
        stroke_width=stroke_width,
        stroke_fill=stroke_color
    )


# ============================================================
# IMAGE HELPERS
# ============================================================

def load_artwork(path):

    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"Artwork not found: {path}"
        )

    image = Image.open(path).convert("RGBA")

    # Remove transparent padding.
    bbox = image.getchannel("A").getbbox()

    if bbox:
        image = image.crop(bbox)

    return image


def resize_artwork(
    artwork,
    max_width,
    max_height
):

    artwork = artwork.copy()

    artwork.thumbnail(
        (max_width, max_height),
        Image.Resampling.LANCZOS
    )

    return artwork


def paste_centered(
    background,
    artwork,
    center_x,
    center_y
):

    x = round(
        center_x - artwork.width / 2
    )

    y = round(
        center_y - artwork.height / 2
    )

    background.paste(
        artwork,
        (x, y),
        artwork
    )


# ============================================================
# RECOLOR ARTWORK
# ============================================================

def recolor_artwork(artwork, palette):

    # Keep the original artwork when no palette is supplied.
    if palette is None:
        return artwork

    artwork = artwork.convert("RGBA")

    # Preserve the original transparency.
    alpha = artwork.getchannel("A")

    # Convert the visible artwork to grayscale.
    #
    # The grayscale retains the original shading,
    # scratches, highlights and lettering details.

    grayscale = ImageOps.grayscale(
        artwork.convert("RGB")
    )

    # Recolor the artwork using a three-color gradient.
    #
    # Dark areas remain dark.
    # Midtones receive the main theme color.
    # Highlights receive the brightest theme color.

    recolored = ImageOps.colorize(
        grayscale,
        black=palette["dark"],
        mid=palette["mid"],
        white=palette["light"],
        blackpoint=0,
        midpoint=130,
        whitepoint=255
    )

    recolored = recolored.convert("RGBA")

    # Restore transparency.
    recolored.putalpha(alpha)

    return recolored


# ============================================================
# THUMBNAIL GENERATION
# ============================================================

def generate_thumbnail(
    character,
    dungeon,
    key_level,
    spec
):

    # --------------------------------------------------------
    # 1. LOAD DUNGEON TEMPLATE
    # --------------------------------------------------------

    # First, try the character-specific template.
    template_path = os.path.join(
        TEMPLATES_FOLDER,
        character,
        dungeon + ".png"
    )

    # If unavailable, use the dungeon-only template.
    if not os.path.isfile(template_path):

        print(
            f"No custom template for {character}. "
            f"Using default template for {dungeon}."
        )

        template_path = os.path.join(
            TEMPLATES_FOLDER,
            "Default",
            dungeon + ".png"
        )

    # Stop if neither template exists.
    if not os.path.isfile(template_path):
        raise FileNotFoundError(
            f"No template found for {dungeon}: {template_path}"
        )
    
    image = Image.open(
        template_path
    ).convert("RGB")

    image = ImageOps.fit(
        image,
        (WIDTH, HEIGHT),
        method=Image.Resampling.LANCZOS
    )

    # --------------------------------------------------------
    # 2. LOAD DUNGEON LAYOUT AND COLOR THEME
    # --------------------------------------------------------

    layout = LAYOUTS.get(
        dungeon,
        DEFAULT_LAYOUT
    )

    key_center_x, key_center_y = (
        layout["key_center"]
    )

    spec_center_x, spec_center_y = (
        layout["spec_center"]
    )

    icon_center_x, icon_center_y = (
        layout["icon_center"]
    )

    theme_name = layout["theme"]

    theme = COLOR_THEMES[theme_name]

    print()
    print(f"Dungeon: {dungeon}")
    print(f"Color theme: {theme_name}")

    # --------------------------------------------------------
    # 3. KEY LEVEL ARTWORK
    # --------------------------------------------------------

    key_path = os.path.join(
        KEY_ASSETS_FOLDER,
        f"{key_level}.png"
    )

    if os.path.isfile(key_path):

        key_image = load_artwork(key_path)

        key_image = resize_artwork(
            key_image,
            max_width=460,
            max_height=260
        )

        # Apply the dungeon's key color palette.
        key_image = recolor_artwork(
            key_image,
            theme["key"]
        )

        paste_centered(
            background=image,
            artwork=key_image,
            center_x=key_center_x,
            center_y=key_center_y
        )

    else:

        print(
            f"WARNING: Key artwork not found: {key_path}"
        )

        # Fallback for key levels without a PNG.
        draw_centered_text(
            image=image,
            text=f"+{key_level}",
            area=(
                key_center_x - 240,
                key_center_y - 60,
                key_center_x + 240,
                key_center_y + 60
            ),
            max_font_size=110,
            color=(
                theme["key"]["mid"]
                if theme["key"]
                else "#FFD54A"
            ),
            stroke_color="#1A1010",
            stroke_width=4,
            font_style="impact"
        )

    # --------------------------------------------------------
    # 4. SPECIALIZATION ARTWORK
    # --------------------------------------------------------

    spec_filename = (
        spec.replace(" ", "") + ".png"
    )

    spec_asset_path = os.path.join(
        SPEC_ASSETS_FOLDER,
        spec_filename
    )

    if os.path.isfile(spec_asset_path):

        spec_image = load_artwork(
            spec_asset_path
        )

        spec_image = resize_artwork(
            spec_image,
            max_width=360,
            max_height=105
        )

        # Apply the dungeon's specialization palette.
        spec_image = recolor_artwork(
            spec_image,
            theme["spec"]
        )

        paste_centered(
            background=image,
            artwork=spec_image,
            center_x=spec_center_x,
            center_y=spec_center_y
        )

    else:

        print(
            f"WARNING: Spec artwork not found: "
            f"{spec_asset_path}"
        )

        draw_centered_text(
            image=image,
            text=spec.upper(),
            area=(
                spec_center_x - 180,
                spec_center_y - 45,
                spec_center_x + 180,
                spec_center_y + 45
            ),
            max_font_size=34,
            color=(
                theme["spec"]["light"]
                if theme["spec"]
                else "#EAF6FF"
            ),
            stroke_color="#102040",
            stroke_width=2,
            font_style="bold"
        )

    # --------------------------------------------------------
    # 5. SPECIALIZATION ICON
    # --------------------------------------------------------

    icon_path = os.path.join(
        ICONS_FOLDER,
        spec_filename
    )

    if os.path.isfile(icon_path):

        icon = load_artwork(icon_path)

        icon = resize_artwork(
            icon,
            max_width=96,
            max_height=96
        )

        # Keep icon colors unchanged.
        paste_centered(
            background=image,
            artwork=icon,
            center_x=icon_center_x,
            center_y=icon_center_y
        )

    else:

        print(
            f"WARNING: Spec icon not found: {icon_path}"
        )

    # --------------------------------------------------------
    # 6. SAVE FINAL THUMBNAIL
    # --------------------------------------------------------

    os.makedirs(
        OUTPUT_FOLDER,
        exist_ok=True
    )

    filename = (
        f"{character}_"
        f"{dungeon}_"
        f"{spec.replace(' ', '')}_"
        f"{key_level}.jpg"
    )

    output_path = os.path.join(
        OUTPUT_FOLDER,
        filename
    )

    for quality in (92, 85, 75, 65, 55, 45):

        image.save(
            output_path,
            "JPEG",
            quality=quality,
            optimize=True
        )

        if os.path.getsize(output_path) <= 2_000_000:
            break

    if os.path.getsize(output_path) > 2_000_000:
        raise ValueError(
            "Generated thumbnail exceeds 2 MB."
        )

    print(
        f"Thumbnail generated: "
        f"{character} | {dungeon} | "
        f"+{key_level} | {spec}"
    )

    print(
        f"Saved to: {output_path}"
    )

    return output_path


# ============================================================
# TEST ALL EIGHT DUNGEONS
# ============================================================

if __name__ == "__main__":

    dungeons = [
          "AltarOfFangs",
        # "BlindingVale",
        #  "DenOfNalorakk",
        # "KingsRest",
        # "MurderRow",
        # "RubyLifePools",
        # "TempleOfSethraliss",
        # "VoidscarArena",
    ]

    for dungeon in dungeons:

        try:

             generate_thumbnail(
        character="VoidHammer",
        dungeon="AltarOfFangs",
        key_level=12,
        spec="Protection Paladin"
    )

        except Exception as e:

            print(
                f"ERROR generating {dungeon}: {e}"
            )