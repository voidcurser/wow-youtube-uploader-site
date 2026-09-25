from pathlib import Path
from PIL import Image, ImageDraw, ImageOps

BASE = Path(r'C:\Users\giova\Desktop\desktopApp\YouTubeUploader')
SOURCE = BASE / 'assets' / 'keys' / 'keys_gold.png'
DEST = BASE / 'assets' / 'keys' / 'gold'
# Source artwork measured at 2048 x 682. Boundaries are manual, not equal-width cells.
ROWS = [
    ([2, 4, 5, 6, 7, 8, 9], [0, 306, 582, 859, 1138, 1440, 1719, 2048], (0, 350)),
    ([10, 11, 12, 13, 14, 15, 16, 17], [0, 257, 491, 761, 1009, 1265, 1519, 1773, 2048], (350, 682)),
]

def extract_keys():
    if not SOURCE.is_file():
        raise FileNotFoundError(f'Sheet not found: {SOURCE}')
    with Image.open(SOURCE) as source:
        if source.size != (2048, 682):
            raise ValueError(f'Expected 2048 x 682 sheet, got {source.size}. Use original PNG.')
        sheet = source.convert('RGBA')
    DEST.mkdir(parents=True, exist_ok=True)
    for keys, boundaries, (top, bottom) in ROWS:
        for index, level in enumerate(keys):
            left, right = boundaries[index:index+2]
            tile = sheet.crop((left, top, right, bottom))
            box = tile.getchannel('A').getbbox()
            if not box:
                raise ValueError(f'No pixels detected for +{level}')
            tile = tile.crop(box)
            out = DEST / f'{level}.png'
            tile.save(out)
            print(f'+{level}: {tile.width}x{tile.height} -> {out}')
    print('Done. Check every output PNG before connecting the uploader.')

if __name__ == '__main__':
    extract_keys()
