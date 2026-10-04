from pathlib import Path
import math
import subprocess
import wave

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "video"
GEN = Path("/Users/samyushgautam/.codex/generated_images/01a0afe9-a02e-7b43-a604-931bcf3390ee")
SCENES = [
    GEN / "exec-db767ed6-f6b5-4899-9bf4-2dba680471eb.png",
    GEN / "exec-921f1ec3-2677-4078-8c3e-df2ff4b093d8.png",
    GEN / "exec-42c6a4f0-1133-4b05-9d8b-0eaac7d81228.png",
    GEN / "exec-9c161436-e012-4709-a235-5cc970702c3a.png",
    GEN / "exec-343d2a7c-63ef-4a5b-b417-71037c37d0b5.png",
    GEN / "exec-9a1a3518-2eb5-41d3-9897-812b640e5d5c.png",
]
W, H, FPS, SECONDS = 1080, 1920, 30, 30
VOICE_TEXT = (
    "A beautiful home begins with a thoughtful journey. "
    "Step inside a living space shaped by warmth, light, and quiet elegance. "
    "Discover a kitchen where beauty meets everyday function. "
    "Rise into bedrooms designed for rest, comfort, and calm. "
    "Then, open the doors to a view that changes everything. "
    "Ivory Arvena Interior and Design. Thoughtfully designed spaces, crafted to feel like home."
)
CAPTIONS = [
    (0.4, 4.3, "A beautiful home begins\nwith a thoughtful journey."),
    (4.3, 9.2, "Step inside a living space shaped by\nwarmth, light, and quiet elegance."),
    (9.2, 13.9, "A kitchen where beauty meets\neveryday function."),
    (13.9, 19.0, "Rise into bedrooms designed for\nrest, comfort, and calm."),
    (19.0, 24.8, "Open the doors to a view\nthat changes everything."),
    (24.8, 30.0, "Thoughtfully designed spaces,\ncrafted to feel like home."),
]


def font(size, serif=False):
    if serif:
        p = Path('/Users/samyushgautam/Library/Application Support/Claude/local-agent-mode-sessions/skills-plugin/6ffd7260-72be-4d71-ab00-b8845ed6edfd/c4c0b788-3685-4979-a803-058c90ba8168/skills/morning/assets/fonts/fraunces-latin-600-normal.woff2')
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.truetype('/System/Library/Fonts/Avenir Next.ttc', size)


def ease(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def fit_scene(im, progress, scene_index):
    base = max(W / im.width, H / im.height)
    # Forward drift creates the FPV motion. The terrace pulls back slightly to reveal the view.
    zoom0, zoom1 = ((1.14, 1.02) if scene_index == 5 else (1.02, 1.115))
    zoom = zoom0 + (zoom1 - zoom0) * ease(progress)
    scale = base * zoom
    rw, rh = round(im.width * scale), round(im.height * scale)
    rs = im.resize((rw, rh), Image.Resampling.LANCZOS)
    drift = [70, 30, 25, -65, 25, -30][scene_index]
    cx = rw // 2 + round(drift * (progress - .5))
    cy = rh // 2 + round((55 if scene_index in (0, 3) else 20) * (progress - .5))
    return rs.crop((cx - W // 2, cy - H // 2, cx + W // 2, cy + H // 2)).convert('RGBA')


def text_center(draw, xy, text, fnt, fill, spacing=4):
    box = draw.multiline_textbbox((0, 0), text, font=fnt, spacing=spacing, align='center')
    draw.multiline_text((xy[0] - (box[2] - box[0]) / 2, xy[1]), text, font=fnt, fill=fill,
                        spacing=spacing, align='center', stroke_width=1, stroke_fill=(0, 0, 0, 55))


def logo_layer():
    src = Image.open(ROOT / 'static/images/ivoryarvena-email-logo.png').convert('RGB')
    art = src.crop((0, 0, 800, 393)).resize((180, 88), Image.Resampling.LANCZOS)
    mask = ImageOps.invert(ImageOps.grayscale(art)).point(lambda p: 0 if p < 30 else min(255, int(p * 1.4)))
    layer = Image.new('RGBA', art.size, (250, 245, 234, 0))
    layer.putalpha(mask)
    return layer


def make_video():
    images = [Image.open(p).convert('RGB') for p in SCENES]
    logo = logo_layer()
    video = OUT / 'ivory-arvena-house-tour-silent.mp4'
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*'mp4v'), FPS, (W, H))
    if not writer.isOpened():
        raise RuntimeError('Could not initialize video encoder')
    scene_len = SECONDS / len(images)
    transition = .85
    for n in range(FPS * SECONDS):
        t = n / FPS
        idx = min(len(images) - 1, int(t / scene_len))
        local = (t - idx * scene_len) / scene_len
        frame = fit_scene(images[idx], local, idx)
        # Directional blur cross dissolve between rooms.
        if idx < len(images) - 1 and local > 1 - transition / scene_len:
            blend = ease((local - (1 - transition / scene_len)) / (transition / scene_len))
            nxt = fit_scene(images[idx + 1], blend * .12, idx + 1)
            frame = Image.blend(frame, nxt, float(blend))
            if .12 < blend < .88:
                frame = frame.filter(ImageFilter.GaussianBlur(2.2 * math.sin(math.pi * blend)))
        # Cinematic grade and vignette.
        frame = Image.alpha_composite(frame, Image.new('RGBA', (W, H), (43, 28, 14, 18)))
        vignette = Image.new('L', (W, H), 0)
        vd = ImageDraw.Draw(vignette)
        vd.ellipse((-260, -260, W + 260, H + 260), fill=225)
        vignette = ImageOps.invert(vignette.filter(ImageFilter.GaussianBlur(180)))
        black = Image.new('RGBA', (W, H), (0, 0, 0, 150))
        black.putalpha(vignette.point(lambda p: int(p * .62)))
        frame = Image.alpha_composite(frame, black)
        d = ImageDraw.Draw(frame)
        # Scene marker at top.
        label = ['ARRIVAL', 'LIVING', 'KITCHEN', 'ASCEND', 'REST', 'THE VIEW'][idx]
        d.text((70, 76), f'0{idx + 1}  /  06', font=font(20), fill=(250, 245, 234, 175))
        d.text((70, 108), label, font=font(20), fill=(250, 245, 234, 220))
        d.line((70, 143, 70 + 170 * min(1, local * 1.8), 143), fill=(250, 245, 234, 180), width=2)
        # Burned-in narration captions.
        for start, end, cap in CAPTIONS:
            if start <= t < end:
                edge = min(1.0, (t - start) / .35, (end - t) / .35)
                alpha = int(255 * ease(edge))
                caption_layer = Image.new('RGBA', (W, 220), (12, 10, 8, 0))
                cd = ImageDraw.Draw(caption_layer)
                cd.rounded_rectangle((70, 18, W - 70, 194), radius=9, fill=(14, 12, 10, int(112 * edge)),
                                     outline=(250, 245, 234, int(70 * edge)), width=1)
                text_center(cd, (W / 2, 52), cap, font(38, serif=True), (250, 245, 234, alpha), spacing=7)
                frame.alpha_composite(caption_layer, (0, 1588))
                break
        # Final brand lockup.
        if t >= 25.0:
            p = ease((t - 25.0) / 1.0)
            shade = Image.new('RGBA', (W, 440), (12, 10, 8, int(145 * p)))
            frame.alpha_composite(shade, (0, 0))
            lg = logo.copy(); lg.putalpha(lg.getchannel('A').point(lambda x: int(x * p)))
            frame.alpha_composite(lg, ((W - lg.width)//2, 38))
            d = ImageDraw.Draw(frame)
            text_center(d, (W/2, 135), 'IVORY ARVENA', font(38), (250,245,234,int(255*p)))
            text_center(d, (W/2, 182), 'INTERIOR & DESIGN', font(19), (250,245,234,int(230*p)))
            text_center(d, (W/2, 255), 'ivoryarvena.vercel.app', font(25), (250,245,234,int(245*p)))
            text_center(d, (W/2, 296), 'ivorydesign2083@gmail.com', font(24), (250,245,234,int(235*p)))
        writer.write(cv2.cvtColor(np.asarray(frame.convert('RGB')), cv2.COLOR_RGB2BGR))
        if n == 27 * FPS:
            frame.convert('RGB').save(OUT / 'ivory-arvena-house-tour-cover.jpg', quality=96)
    writer.release()
    return video


def make_audio():
    voice_aiff = OUT / 'ivory-arvena-voice.aiff'
    voice_wav = OUT / 'ivory-arvena-voice.wav'
    if not voice_aiff.exists() or voice_aiff.stat().st_size < 10000:
        subprocess.run(['/usr/bin/say', '-v', 'Samantha', '-r', '154', '-o', str(voice_aiff), VOICE_TEXT], check=True)
    voice_wav.unlink(missing_ok=True)
    subprocess.run(['/usr/bin/afconvert', '-f', 'WAVE', '-d', 'LEI16@44100', str(voice_aiff), str(voice_wav)], check=True)
    with wave.open(str(voice_wav), 'rb') as af:
        rate, channels, width, frames = af.getframerate(), af.getnchannels(), af.getsampwidth(), af.getnframes()
        raw = af.readframes(frames)
    voice = np.frombuffer(raw, dtype='<i2' if width == 2 else '<i4').astype(np.float64)
    if channels > 1: voice = voice.reshape(-1, channels).mean(axis=1)
    target_rate = 44100
    x = np.arange(int(len(voice) * target_rate / rate)) * rate / target_rate
    voice = np.interp(x, np.arange(len(voice)), voice)
    voice /= max(1, np.max(np.abs(voice)))
    total = target_rate * SECONDS
    if len(voice) > total - int(.35 * target_rate): voice = voice[:total - int(.35 * target_rate)]
    voice_track = np.zeros(total)
    offset = int(.35 * target_rate)
    voice_track[offset:offset + len(voice)] = voice
    # Original ambient cinematic pad: D major add9 with soft pulse and airy texture.
    t = np.arange(total) / target_rate
    music = np.zeros(total)
    for freq, amp, phase in [(73.42,.12,.1),(110.0,.08,1.1),(146.83,.065,2.0),(220.0,.045,.4),(329.63,.025,2.5)]:
        music += amp*np.sin(2*np.pi*freq*t+phase)*(0.72+0.28*np.sin(2*np.pi*.055*t+phase))
    pulse = .6 + .4*(.5+.5*np.sin(2*np.pi*.5*t))**4
    music *= pulse
    rng = np.random.default_rng(83)
    air = np.convolve(rng.normal(0, 1, total), np.ones(1200)/1200, mode='same')
    music += .05 * air
    env = np.ones(total); fade = int(1.5*target_rate)
    env[:fade] = np.linspace(0,1,fade); env[-fade:] = np.linspace(1,0,fade)
    music *= env
    # Duck music beneath the voice and mix for clear narration.
    mix = .82*voice_track + .22*music
    mix /= max(1.0, np.max(np.abs(mix))/.92)
    wav = OUT / 'ivory-arvena-house-tour-audio.wav'
    with wave.open(str(wav), 'wb') as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(target_rate)
        wf.writeframes(np.int16(mix*32767).tobytes())
    return wav


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    video = make_video()
    audio = make_audio()
    print(video)
    print(audio)


if __name__ == '__main__':
    main()
