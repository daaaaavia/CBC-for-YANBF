"""Backdrop for the HOME Menu preview window: a 3DS top screen at its native 400x240.

If home_bg_screenshot.py is present (a screenshot of the real HOME Menu - Nintendo's
artwork, so it isn't in the repository), that is used. Otherwise a plain backdrop is
drawn in the same colours and layout: pale grey, a faint grid of rounded tiles and the
darker top and bottom strips, with no Nintendo artwork.
"""

from PIL import Image, ImageDraw

SIZE = (400, 240)


def load():
    try:
        import home_bg_screenshot
    except ImportError:
        return drawn()
    return home_bg_screenshot.load()


def drawn():
    w, h = SIZE
    img = Image.new("RGB", SIZE)
    d = ImageDraw.Draw(img)
    for y in range(h):  # soft vertical gradient, lighter at the top
        t = y / (h - 1)
        d.line((0, y, w, y), fill=tuple(round(a + (b - a) * t) for a, b in zip((246, 247, 250), (229, 230, 236))))
    # the tile pattern behind the HOME Menu icons
    tile, gap = 44, 12
    for row in range(-1, h // (tile + gap) + 2):
        for col in range(-1, w // (tile + gap) + 2):
            x = col * (tile + gap) + (row % 2) * (tile + gap) // 2 - 6
            y = row * (tile + gap) + 14
            d.rounded_rectangle((x, y, x + tile, y + tile), radius=9, outline=(222, 223, 230), width=2)
    # status bar (top) and button strip (bottom)
    d.rectangle((0, 0, w, 19), fill=(236, 237, 242))
    d.line((0, 20, w, 20), fill=(214, 215, 222))
    d.rectangle((0, h - 22, w, h), fill=(233, 234, 239))
    d.line((0, h - 23, w, h - 23), fill=(214, 215, 222))
    return img
