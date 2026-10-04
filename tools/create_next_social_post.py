from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[1]
BACKGROUND = Path('/Users/samyushgautam/.codex/generated_images/01a0afe9-a02e-7b43-a604-931bcf3390ee/exec-31521aae-00e7-4949-87c5-b0d302779f63.png')
OUTPUT = ROOT / 'output/social/ivory-arvena-dream-space.png'

im = Image.open(BACKGROUND).convert('RGBA')
w, h = im.size
draw = ImageDraw.Draw(im)
white = '#fffaf4'
ink = '#332d29'

def font(name, size):
    return ImageFont.truetype(name, size)

avenir = '/System/Library/Fonts/Avenir Next.ttc'
helvetica = '/System/Library/Fonts/HelveticaNeue.ttc'
fraunces = '/Users/samyushgautam/Library/Application Support/Claude/local-agent-mode-sessions/skills-plugin/6ffd7260-72be-4d71-ab00-b8845ed6edfd/c4c0b788-3685-4979-a803-058c90ba8168/skills/morning/assets/fonts/fraunces-latin-600-normal.woff2'

def centered(text, y, fnt, fill=white, spacing=0):
    if spacing == 0:
        box = draw.textbbox((0, 0), text, font=fnt)
        draw.text(((w - (box[2] - box[0])) / 2, y), text, font=fnt, fill=fill)
        return
    widths = [draw.textlength(c, font=fnt) for c in text]
    total = sum(widths) + spacing * (len(text) - 1)
    x = (w - total) / 2
    for c, cw in zip(text, widths):
        draw.text((x, y), c, font=fnt, fill=fill)
        x += cw + spacing

# Use the artwork from the existing company logo as the mark. Its source has a
# white background, so the original dark strokes become the opacity mask.
logo = Image.open(ROOT / 'static/images/ivoryarvena-email-logo.png').convert('RGB')
mark = logo.crop((0, 0, 800, 393))
mark = mark.resize((155, 76), Image.Resampling.LANCZOS)
mask = ImageOps.invert(ImageOps.grayscale(mark)).point(lambda value: 0 if value < 30 else min(255, int(value * 1.35)))
white_mark = Image.new('RGBA', mark.size, (255, 250, 244, 0))
white_mark.putalpha(mask)
im.alpha_composite(white_mark, ((w - 155) // 2, 34))
draw = ImageDraw.Draw(im)

centered('IVORY ARVENA', 112, font(avenir, 29), spacing=4)
centered('INTERIOR & DESIGN', 149, font(avenir, 14), spacing=4)

centered('Designing Your', 213, font(fraunces, 43))
centered('Dream Space', 260, font(fraunces, 88))

centered('Thoughtfully designed spaces,', 381, font(fraunces, 29), fill=(255, 250, 244, 185))
centered('crafted to feel like home.', 416, font(fraunces, 29), fill=(255, 250, 244, 185))

# Contact details follow the two angled edges of the unrolled drawing.
draw.line((120, 1272, 1000, 1272), fill=(255, 250, 244, 110), width=1)
draw.text((145, 1286), 'EXPLORE OUR WORK', font=font(avenir, 15), fill=(255, 250, 244, 180))
draw.text((145, 1313), 'ivoryarvena.vercel.app', font=font(avenir, 25), fill=white)
draw.text((598, 1286), 'START A CONVERSATION', font=font(avenir, 15), fill=(255, 250, 244, 180))
draw.text((598, 1313), 'ivorydesign2083@gmail.com', font=font(avenir, 23), fill=white)

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
im = im.convert('RGB').resize((1080, 1350), Image.Resampling.LANCZOS)
im.save(OUTPUT, quality=95, optimize=True)
print(OUTPUT)
