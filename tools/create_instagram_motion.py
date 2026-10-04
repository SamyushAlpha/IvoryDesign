from pathlib import Path
import math
import wave

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "instagram"
BG_PATH = OUT / "ivory-motion-background.png"
LOGO_PATH = ROOT / "static" / "images" / "ivory-design-logo-transparent.png"
VIDEO_PATH = OUT / "ivory-design-motion-post-2x-silent.mp4"
COVER_PATH = OUT / "ivory-design-motion-cover-2x.jpg"
AUDIO_PATH = OUT / "ivory-design-ambient.wav"

W, H = 1080, 1350
OUTPUT_SCALE = 2
FPS, SECONDS = 30, 7


def font(size, serif=False):
    candidates = (
        ["/System/Library/Fonts/NewYork.ttf", "/System/Library/Fonts/Supplemental/Didot.ttc"]
        if serif else
        ["/System/Library/Fonts/SFNS.ttf", "/System/Library/Fonts/Helvetica.ttc"]
    )
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def ease(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def fade(t, start, duration=0.6):
    return ease((t - start) / duration)


def cover_crop(im, width, height, zoom=1.0, x_shift=0, y_shift=0):
    scale = max(width / im.width, height / im.height) * zoom
    resized = im.resize((round(im.width * scale), round(im.height * scale)), Image.Resampling.LANCZOS)
    left = (resized.width - width) // 2 + x_shift
    top = (resized.height - height) // 2 + y_shift
    return resized.crop((left, top, left + width, top + height))


def paste_alpha(base, layer, xy, opacity=1.0):
    layer = layer.copy()
    if opacity < 1:
        layer.putalpha(layer.getchannel("A").point(lambda p: int(p * opacity)))
    base.alpha_composite(layer, xy)


def frame_at(t, bg, logo):
    zoom = 1.035 + 0.025 * (t / SECONDS)
    frame = cover_crop(bg, W, H, zoom=zoom, x_shift=round(12 * t / SECONDS)).convert("RGBA")

    # Warm editorial grade and left-side typography field.
    grade = Image.new("RGBA", (W, H), (34, 27, 20, 24))
    frame = Image.alpha_composite(frame, grade)
    shade = Image.new("L", (W, H), 0)
    sd = ImageDraw.Draw(shade)
    for x in range(W):
        a = int(145 * max(0, 1 - x / 790) ** 1.45)
        sd.line((x, 0, x, H), fill=a)
    shade = shade.filter(ImageFilter.GaussianBlur(28))
    frame.alpha_composite(Image.new("RGBA", (W, H), (19, 17, 14, 0)))
    dark = Image.new("RGBA", (W, H), (18, 16, 13, 255))
    frame = Image.composite(dark, frame, shade)

    draw = ImageDraw.Draw(frame)
    ivory = (246, 241, 229)
    soft = (236, 225, 207)
    ink = (31, 28, 24)

    # Logo entrance.
    p_logo = fade(t, 0.15, 0.8)
    logo_w = 305
    logo_h = round(logo.height * logo_w / logo.width)
    lg = logo.resize((logo_w, logo_h), Image.Resampling.LANCZOS)
    # Turn the dark logo into a warm ivory mark for contrast.
    alpha = lg.getchannel("A")
    solid = Image.new("RGBA", lg.size, ivory + (255,))
    solid.putalpha(alpha)
    paste_alpha(frame, solid, (76, round(72 + 18 * (1 - p_logo))), p_logo)

    # Animated rule and micro label.
    p_rule = fade(t, 0.55, 0.9)
    draw.line((78, 250, 78 + 150 * p_rule, 250), fill=soft + (220,), width=3)
    micro = "INTERIOR  •  ARCHITECTURE  •  BUILD"
    draw.text((78, 272), micro, font=font(22), fill=soft + (round(235 * fade(t, 0.75, 0.65)),), spacing=8)

    # Main statement reveals line-by-line with a gentle rise.
    headline = [("SPACES", 1.15), ("THAT FEEL", 1.42), ("LIKE YOU.", 1.69)]
    y0 = 410
    for i, (line, start) in enumerate(headline):
        p = fade(t, start, 0.7)
        y = y0 + i * 112 + round(26 * (1 - p))
        draw.text((74, y), line, font=font(92, serif=True), fill=ivory + (round(255 * p),))

    # Brief project promise.
    p_body = fade(t, 2.45, 0.8)
    body_y = round(800 + 18 * (1 - p_body))
    draw.text((80, body_y), "Thoughtful interiors, designed around", font=font(30), fill=ivory + (round(240 * p_body),))
    draw.text((80, body_y + 43), "how you live.", font=font(30), fill=ivory + (round(240 * p_body),))

    # Border-only CTA remains transparent so the interior stays visible.
    p_cta = fade(t, 3.55, 0.8)
    card_x = round(78 - 32 * (1 - p_cta))
    card_y = 1058
    card_w, card_h = 520, 132
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rounded_rectangle((card_x, card_y, card_x + card_w, card_y + card_h), radius=3,
                         outline=ivory + (round(230 * p_cta),), width=2)
    frame = Image.alpha_composite(frame, overlay)
    draw = ImageDraw.Draw(frame)
    draw.text((card_x + 34, card_y + 27), "START YOUR PROJECT", font=font(25), fill=ivory + (round(255 * p_cta),))
    draw.text((card_x + 34, card_y + 70), "ivory-design.vercel.app  →", font=font(22), fill=soft + (round(255 * p_cta),))

    # Fine framing details create motion without clutter.
    p_border = fade(t, 0.2, 1.2)
    draw.line((38, 38, 38, 38 + 150 * p_border), fill=ivory + (130,), width=2)
    draw.line((38, 38, 38 + 150 * p_border, 38), fill=ivory + (130,), width=2)
    draw.text((80, 1260), "IVORY DESIGN STUDIO", font=font(18), fill=ivory + (175,))
    draw.text((870, 1260), "01 / 01", font=font(18), fill=ivory + (150,))
    return frame.convert("RGB")


def create_ambient_audio():
    """Create a subtle, original ambient bed with no third-party music rights."""
    sample_rate = 44100
    duration = SECONDS
    count = sample_rate * duration
    rng = np.random.default_rng(27)
    x = np.arange(count, dtype=np.float64) / sample_rate
    signal = np.zeros(count, dtype=np.float64)
    # Airy major-ninth pad: A2, E3, B3, C#4 with slow modulation.
    for freq, amp, phase in [(110.0, .22, 0.1), (164.81, .16, 1.2), (246.94, .10, 2.0), (277.18, .075, .6)]:
        signal += amp * np.sin(2 * np.pi * freq * x + phase) * (0.78 + 0.22 * np.sin(2 * np.pi * .11 * x + phase))
    noise = rng.normal(0, 1, count)
    noise = np.convolve(noise, np.ones(900) / 900, mode="same")
    signal += .07 * noise
    fade_len = int(sample_rate * 1.25)
    envelope = np.ones(count)
    envelope[:fade_len] = np.linspace(0, 1, fade_len) ** 1.7
    envelope[-fade_len:] = np.linspace(1, 0, fade_len) ** 1.7
    signal *= envelope
    signal /= max(1.0, np.max(np.abs(signal)) / .58)
    pcm = np.int16(signal * 32767)
    with wave.open(str(AUDIO_PATH), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm.tobytes())


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    bg = Image.open(BG_PATH).convert("RGB")
    logo = Image.open(LOGO_PATH).convert("RGBA")
    output_size = (W * OUTPUT_SCALE, H * OUTPUT_SCALE)
    writer = cv2.VideoWriter(str(VIDEO_PATH), cv2.VideoWriter_fourcc(*"mp4v"), FPS, output_size)
    if not writer.isOpened():
        raise RuntimeError("Could not initialize MP4 writer")
    total = FPS * SECONDS
    for n in range(total):
        frame = frame_at(n / FPS, bg, logo)
        if n == int(4.7 * FPS):
            frame.resize(output_size, Image.Resampling.LANCZOS).save(COVER_PATH, quality=98, subsampling=0)
        frame_2x = frame.resize(output_size, Image.Resampling.LANCZOS)
        writer.write(cv2.cvtColor(np.asarray(frame_2x), cv2.COLOR_RGB2BGR))
    writer.release()
    create_ambient_audio()
    print(VIDEO_PATH)
    print(COVER_PATH)
    print(AUDIO_PATH)


if __name__ == "__main__":
    main()
