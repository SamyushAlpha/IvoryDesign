"""Render an original 4:5 Ivory Arvena social motion post."""

from __future__ import annotations

import argparse
import math
import wave
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "instagram"
LOGO_PATH = ROOT / "static" / "images" / "ivoryarvena-email-logo.png"
VIDEO_PATH = OUT / "ivory-arvena-a-line-becomes-a-home-ivory-silent.mp4"
COVER_PATH = OUT / "ivory-arvena-a-line-becomes-a-home-ivory-cover.jpg"
MUSIC_PATH = OUT / "ivory-arvena-a-line-becomes-a-home-original-music.wav"
W, H = 1080, 1350
FPS, DURATION = 24, 8
IVORY = (242, 239, 231)
INK = (34, 48, 44)
SOFT = (94, 105, 99)
GOLD = (148, 117, 57)


def font(size: int, serif: bool = False) -> ImageFont.FreeTypeFont:
    path = "/System/Library/Fonts/NewYork.ttf" if serif else "/System/Library/Fonts/SFNS.ttf"
    return ImageFont.truetype(path, size)


def ease(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def fade(t: float, start: float, duration: float = 0.6) -> float:
    return ease((t - start) / duration)


def draw_text(draw: ImageDraw.ImageDraw, xy, value: str, *, size: int, color, alpha=255, serif=False, spacing=0):
    face = font(size, serif)
    if not spacing:
        draw.text(xy, value, font=face, fill=(*color, int(alpha)))
        return
    x, y = xy
    for letter in value:
        draw.text((x, y), letter, font=face, fill=(*color, int(alpha)))
        x += draw.textlength(letter, font=face) + spacing


def prepare_logo(width: int, color: tuple[int, int, int]) -> Image.Image:
    source = Image.open(LOGO_PATH).convert("RGB")
    height = round(source.height * width / source.width)
    source = source.resize((width, height), Image.Resampling.LANCZOS)
    alpha = ImageOps.invert(ImageOps.grayscale(source)).point(lambda value: min(255, int(value * 1.12)))
    mark = Image.new("RGBA", source.size, (*color, 255))
    mark.putalpha(alpha)
    return mark


def make_background() -> Image.Image:
    yy, xx = np.mgrid[0:H, 0:W]
    base = np.empty((H, W, 3), dtype=np.float32)
    base[:] = IVORY
    # Barely perceptible paper warmth: the drawing remains the focal point.
    beam = np.exp(-((xx - (1100 - 0.20 * yy)) / 470.0) ** 2)
    base += beam[:, :, None] * np.array([2.0, 1.2, -0.2], dtype=np.float32)
    vignette = np.clip(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2, 0, 2)
    base -= vignette[:, :, None] * 1.5
    rng = np.random.default_rng(2609)
    base += rng.normal(0, 0.48, (H, W, 1))
    return Image.fromarray(np.uint8(np.clip(base, 0, 255)), "RGB").convert("RGBA")


# Each measured line belongs to the same architectural drawing. The leading
# point travels through them in sequence, like a pencil making a floor plan.
ROOM_LINES = [
    ((180, 925), (180, 605)), ((180, 605), (312, 530)),
    ((312, 530), (770, 530)), ((770, 530), (908, 605)),
    ((908, 605), (908, 925)), ((908, 925), (770, 997)),
    ((770, 997), (312, 997)), ((312, 997), (180, 925)),
    ((312, 530), (312, 997)), ((770, 530), (770, 997)),
    ((180, 605), (312, 682)), ((908, 605), (770, 682)),
    ((312, 682), (770, 682)),
    ((401, 530), (401, 682)), ((401, 530), (401, 410)),
    ((401, 410), (681, 410)), ((681, 410), (681, 530)),
    ((681, 530), (681, 682)), ((541, 410), (541, 682)),
    ((342, 810), (388, 783)), ((388, 783), (694, 783)),
    ((694, 783), (740, 810)), ((740, 810), (740, 898)),
    ((740, 898), (342, 898)), ((342, 898), (342, 810)),
    ((388, 783), (388, 752)), ((388, 752), (694, 752)),
    ((694, 752), (694, 783)),
    ((355, 897), (323, 940)), ((323, 940), (757, 940)),
    ((757, 940), (725, 897)),
    ((541, 410), (541, 340)),
]
ROOM_LINES = [
    ((start[0], round(start[1] * 0.8 + 260)), (end[0], round(end[1] * 0.8 + 260)))
    for start, end in ROOM_LINES
]
ROOM_LENGTHS = [math.dist(a, b) for a, b in ROOM_LINES]
ROOM_TOTAL = sum(ROOM_LENGTHS)


def draw_room(draw: ImageDraw.ImageDraw, progress: float, opacity: float) -> tuple[float, float]:
    remaining = ROOM_TOTAL * max(0.0, min(1.0, progress))
    tip = ROOM_LINES[0][0]
    for (start, end), length in zip(ROOM_LINES, ROOM_LENGTHS):
        if remaining <= 0:
            break
        portion = min(1.0, remaining / length)
        point = (start[0] + (end[0] - start[0]) * portion,
                 start[1] + (end[1] - start[1]) * portion)
        draw.line((start, point), fill=(*INK, round(225 * opacity)), width=3, joint="curve")
        tip = point
        remaining -= length
    return tip


def paste_logo(frame: Image.Image, logo: Image.Image, xy: tuple[int, int], opacity: float):
    if opacity <= 0:
        return
    layer = logo.copy()
    layer.putalpha(layer.getchannel("A").point(lambda value: round(value * opacity)))
    frame.alpha_composite(layer, xy)


def frame_at(t: float, background: Image.Image, small_logo: Image.Image, large_logo: Image.Image) -> Image.Image:
    frame = background.copy()
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    intro = 1 - fade(t, 4.70, 0.75)
    end = fade(t, 4.85, 0.8)

    # The glint tracks the pen tip. No foreground fill may cover the linework.
    progress = fade(t, 0.46, 3.75)
    room_alpha = 0.9 * intro
    tip = draw_room(draw, progress, room_alpha)
    if 0.02 < progress < 0.99:
        radius = 7 + 2 * math.sin(t * 7)
        draw.ellipse((tip[0] - radius, tip[1] - radius, tip[0] + radius, tip[1] + radius),
                     fill=(*GOLD, round(240 * intro)))
    if progress > 0.5:
        p_light = fade(t, 2.5, 1.4) * room_alpha
        draw.line((402, 683, 681, 683), fill=(*GOLD, round(145 * p_light)), width=3)

    draw.line((68, 68, 68, 170), fill=(*INK, 100), width=2)
    draw.line((68, 68, 170, 68), fill=(*INK, 100), width=2)
    draw.line((1012, 1180, 1012, 1282), fill=(*INK, 85), width=2)
    draw.line((910, 1282, 1012, 1282), fill=(*INK, 85), width=2)

    small_alpha = fade(t, 0.18, 0.65) * intro
    draw_text(draw, (78, 274), "INTERIOR  /  DESIGN  /  ART", size=24,
              color=SOFT, alpha=190 * small_alpha, spacing=2.1)
    for line, start, y in (("A LINE", 0.98, 319), ("BECOMES", 1.53, 412), ("A HOME.", 2.08, 505)):
        amount = fade(t, start, 0.6) * intro
        draw_text(draw, (72, y + 17 * (1 - amount)), line,
                  size=93, color=INK, alpha=255 * amount, serif=True)

    rule_progress = fade(t, 3.70, 0.75) * intro
    draw.line((78, 1117, 78 + 150 * rule_progress, 1117), fill=(*GOLD, round(235 * intro)), width=3)
    draw_text(draw, (78, 1142), "SPACES MADE TO FEEL LIKE YOU.", size=29,
              color=INK, alpha=225 * rule_progress, spacing=0.8)

    # End card stays on screen long enough to pause and read before upload.
    if end > 0:
        draw.line((180, 775, 900, 775), fill=(*GOLD, round(145 * end)), width=2)
        draw_text(draw, (170, 815 + 16 * (1 - end)), "LET'S DESIGN", size=77,
                  color=INK, alpha=250 * end, serif=True)
        draw_text(draw, (248, 902 + 16 * (1 - end)), "YOURS.", size=77,
                  color=INK, alpha=250 * end, serif=True)
        draw_text(draw, (196, 1037), "INTERIOR & DESIGN  /  KATHMANDU", size=22,
                  color=SOFT, alpha=215 * end, spacing=2.0)
        draw.rounded_rectangle((250, 1120, 830, 1200), radius=40,
                               outline=(*INK, round(195 * end)), width=2)
        draw_text(draw, (310, 1140), "IVORYARVENA.VERCEL.APP", size=26,
                  color=INK, alpha=255 * end, spacing=0.8)

    draw_text(draw, (75, 1280), "IVORY ARVENA", size=20, color=SOFT, alpha=155, spacing=2.4)
    draw_text(draw, (880, 1280), "01 / 01", size=20, color=SOFT, alpha=155)
    frame = Image.alpha_composite(frame, overlay)
    paste_logo(frame, small_logo, (76, 78), small_alpha)
    paste_logo(frame, large_logo, ((W - large_logo.width) // 2, 230), end)
    return frame.convert("RGB")


def write_original_music():
    """A quiet, original ambient bed with soft chords and architectural ticks."""
    sample_rate = 44100
    time = np.arange(sample_rate * DURATION, dtype=np.float64) / sample_rate
    sound = np.zeros_like(time)
    # D major add-nine, gently drifting between two voicings.
    for frequency, amplitude, phase in ((146.83, .060, 0), (185.00, .045, .6),
                                        (220.00, .043, 1.3), (329.63, .026, 2.0)):
        sound += amplitude * np.sin(2 * np.pi * frequency * time + phase)
        sound += amplitude * .14 * np.sin(2 * np.pi * frequency * 2 * time + phase)
    sound *= .82 + .18 * np.sin(2 * np.pi * .14 * time)
    for beat, pitch in ((.56, 440.0), (1.58, 493.88), (2.61, 554.37),
                        (3.66, 659.25), (5.16, 554.37), (6.24, 440.0)):
        elapsed = time - beat
        envelope = np.where(elapsed >= 0, np.exp(-np.maximum(elapsed, 0) * 3.5), 0)
        sound += .036 * envelope * np.sin(2 * np.pi * pitch * elapsed)
    fade_in = np.clip(time / .65, 0, 1)
    fade_out = np.clip((DURATION - time) / 1.05, 0, 1)
    sound *= fade_in * fade_out
    # Gentle stereo width, not an aggressive soundtrack.
    left = sound + .003 * np.sin(2 * np.pi * 277.18 * time)
    right = sound + .003 * np.sin(2 * np.pi * 329.63 * time + .5)
    stereo = np.stack((left, right), axis=1)
    pcm = np.int16(np.clip(stereo, -1, 1) * 32767)
    with wave.open(str(MUSIC_PATH), "wb") as track:
        track.setnchannels(2)
        track.setsampwidth(2)
        track.setframerate(sample_rate)
        track.writeframes(pcm.tobytes())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", action="store_true", help="Render only storyboard stills")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    background = make_background()
    small_logo = prepare_logo(260, INK)
    large_logo = prepare_logo(560, INK)

    if args.preview:
        for second in (1.4, 3.4, 6.6):
            frame_at(second, background, small_logo, large_logo).save(
                OUT / f"ivory-arvena-motion-preview-{second:.1f}.png"
            )
        return

    writer = cv2.VideoWriter(str(VIDEO_PATH), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
    if not writer.isOpened():
        raise RuntimeError("Could not initialize MP4 writer")
    try:
        for index in range(FPS * DURATION):
            frame = frame_at(index / FPS, background, small_logo, large_logo)
            if index == FPS * 6:
                frame.save(COVER_PATH, quality=94, subsampling=0)
            writer.write(cv2.cvtColor(np.asarray(frame), cv2.COLOR_RGB2BGR))
    finally:
        writer.release()
    write_original_music()
    print(VIDEO_PATH)
    print(COVER_PATH)
    print(MUSIC_PATH)


if __name__ == "__main__":
    main()
