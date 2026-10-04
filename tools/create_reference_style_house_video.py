from pathlib import Path
import math
import wave

import cv2
import numpy as np
from PIL import Image, ImageFilter, ImageEnhance, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[1]
GEN = Path('/Users/samyushgautam/.codex/generated_images/01a0afe9-a02e-7b43-a604-931bcf3390ee')
OUT = ROOT / 'output/video'
SCENES = [
    GEN / 'exec-feb2e62d-ca2a-4b45-84b9-bc10ae313842.png',
    GEN / 'exec-0cf7b18e-4125-4ed1-aa24-50d28234a081.png',
    GEN / 'exec-f1b9052b-5f25-43b6-a3e9-7bdbd6f01d82.png',
    GEN / 'exec-39119fbe-aa16-4880-9490-d07fb70226fd.png',
    GEN / 'exec-f581d2cf-b032-4064-bcde-8c8d119be279.png',
]
W, H, FPS, SECONDS = 1080, 1920, 30, 30


def smooth(x):
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)


def crop_motion(im, progress, index):
    base = max(W / im.width, H / im.height)
    # A slow arc and changing scale emulate the reference's orbiting camera.
    z0 = [1.01, 1.09, 1.05, 1.03, 1.11][index]
    z1 = [1.12, 1.02, 1.13, 1.11, 1.01][index]
    zoom = z0 + (z1 - z0) * smooth(progress)
    scale = base * zoom
    rw, rh = int(im.width * scale), int(im.height * scale)
    rs = im.resize((rw, rh), Image.Resampling.LANCZOS)
    arc_x = [90, -100, 105, -80, 115][index]
    arc_y = [-40, 55, -55, 35, -35][index]
    cx = rw // 2 + int(arc_x * (progress - .5))
    cy = rh // 2 + int(arc_y * math.sin(math.pi * (progress - .5)))
    return rs.crop((cx-W//2, cy-H//2, cx+W//2, cy+H//2)).convert('RGB')


def directional_blur(im, amount):
    if amount <= .1:
        return im
    # Layered horizontal offsets create a subtle camera whip without smearing detail excessively.
    arr = np.asarray(im).astype(np.float32)
    acc = np.zeros_like(arr)
    offsets = [-14, -8, -3, 0, 3, 8, 14]
    for off in offsets:
        acc += np.roll(arr, int(off * amount), axis=1)
    return Image.fromarray(np.uint8(np.clip(acc / len(offsets), 0, 255)))


def brand_assets():
    logo = Image.open(ROOT/'static/images/ivoryarvena-email-logo.png').convert('RGB')
    mark = logo.crop((0, 0, 800, 393)).resize((230, 113), Image.Resampling.LANCZOS)
    mask = ImageOps.invert(ImageOps.grayscale(mark)).point(lambda p: 0 if p < 25 else min(255, int(p*1.35)))
    white = Image.new('RGBA', mark.size, (252, 248, 239, 0)); white.putalpha(mask)
    return white


def centered(draw, y, text, fnt, fill):
    box = draw.textbbox((0, 0), text, font=fnt)
    draw.text(((W-(box[2]-box[0]))/2, y), text, font=fnt, fill=fill)


def make_video():
    OUT.mkdir(parents=True, exist_ok=True)
    ims = [Image.open(p).convert('RGB') for p in SCENES]
    logo = brand_assets()
    avenir = '/System/Library/Fonts/Avenir Next.ttc'
    lengths = [5.2, 5.8, 5.7, 6.0, 7.3]
    starts = np.cumsum([0] + lengths[:-1]).tolist()
    transition = .95
    path = OUT / 'ivory-arvena-architectural-reveal-silent.mp4'
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'mp4v'), FPS, (W, H))
    if not writer.isOpened(): raise RuntimeError('Could not initialize video encoder')
    for n in range(FPS * SECONDS):
        t = n / FPS
        idx = max(i for i, s in enumerate(starts) if s <= t)
        local_sec = t - starts[idx]
        local = min(1, local_sec / lengths[idx])
        frame = crop_motion(ims[idx], local, idx)
        # Reference-inspired assembly transition: bright drafting flash, then dissolve.
        if idx < len(ims)-1 and local_sec > lengths[idx]-transition:
            p = smooth((local_sec-(lengths[idx]-transition))/transition)
            nxt = crop_motion(ims[idx+1], p*.14, idx+1)
            frame = Image.blend(frame, nxt, p)
            flash = math.sin(math.pi*p)**6
            if flash > .01:
                frame = Image.blend(frame, Image.new('RGB',(W,H),(246,244,239)), .20*flash)
            frame = directional_blur(frame, math.sin(math.pi*p))
        # Very light cinematic finish. Keep the first stages clean and final reveal rich.
        if idx >= 3:
            frame = ImageEnhance.Color(frame).enhance(1.04 + .10*local)
            frame = ImageEnhance.Contrast(frame).enhance(1.03)
        # Requested final brand lockup, placed only over the completed 3D house.
        if t >= 26.0:
            p = float(smooth((t-26.0)/1.0))
            rgba = frame.convert('RGBA')
            shade = Image.new('RGBA', (W, H), (0, 0, 0, int(88*p)))
            rgba = Image.alpha_composite(rgba, shade)
            panel = Image.new('RGBA', (W, 470), (14, 12, 10, int(150*p)))
            rgba.alpha_composite(panel, (0, H-470))
            lg = logo.copy(); lg.putalpha(lg.getchannel('A').point(lambda a: int(a*p)))
            rgba.alpha_composite(lg, ((W-lg.width)//2, H-435))
            d = ImageDraw.Draw(rgba)
            centered(d, H-305, 'IVORY ARVENA', ImageFont.truetype(avenir, 44), (252,248,239,int(255*p)))
            centered(d, H-248, 'INTERIOR & DESIGN', ImageFont.truetype(avenir, 22), (252,248,239,int(230*p)))
            d.line((220,H-196,860,H-196), fill=(252,248,239,int(100*p)), width=1)
            centered(d, H-162, 'ivoryarvena.vercel.app', ImageFont.truetype(avenir, 28), (252,248,239,int(250*p)))
            centered(d, H-116, 'ivorydesign2083@gmail.com', ImageFont.truetype(avenir, 27), (252,248,239,int(235*p)))
            frame = rgba.convert('RGB')
        if n == int(27.5*FPS):
            frame.save(OUT/'ivory-arvena-architectural-reveal-cover.jpg', quality=96)
        writer.write(cv2.cvtColor(np.asarray(frame), cv2.COLOR_RGB2BGR))
    writer.release()
    return path


def make_music():
    sr, total = 44100, 44100*SECONDS
    t = np.arange(total)/sr
    music = np.zeros(total)
    # Original cinematic score: restrained piano-like pulses over a warm harmonic bed.
    chord_sets = [
        [73.42, 110.00, 146.83, 220.00],
        [82.41, 123.47, 164.81, 246.94],
        [92.50, 138.59, 185.00, 277.18],
        [73.42, 110.00, 146.83, 220.00],
    ]
    segment = total//4
    for j, chord in enumerate(chord_sets):
        a, b = j*segment, total if j==3 else (j+1)*segment
        tx = t[a:b]
        fade = np.sin(np.linspace(0, math.pi, b-a))**.42
        for k, f in enumerate(chord):
            music[a:b] += (.075/(1+k*.22))*np.sin(2*np.pi*f*tx + k*.7)*fade
    # Soft rhythmic architectural pulse, rising toward the final reveal.
    for beat in np.arange(.6, 29.5, 1.0):
        start=int(beat*sr); dur=int(.48*sr); x=np.arange(dur)/sr
        tone=np.sin(2*np.pi*(220 if int(beat)%2 else 293.66)*x)*np.exp(-7*x)
        music[start:start+dur] += tone*.035
    rise = np.clip((t-17)/8,0,1)
    music += .025*rise*np.sin(2*np.pi*440*t)*(0.6+0.4*np.sin(2*np.pi*.1*t))
    rng=np.random.default_rng(119)
    air=np.convolve(rng.normal(0,1,total),np.ones(1500)/1500,mode='same')
    music += .035*air
    env=np.ones(total); f=int(1.3*sr)
    env[:f]=np.linspace(0,1,f); env[-f:]=np.linspace(1,0,f)
    music*=env
    music/=max(1,np.max(np.abs(music))/.88)
    path=OUT/'ivory-arvena-architectural-reveal-music.wav'
    with wave.open(str(path),'wb') as wf:
        wf.setnchannels(1);wf.setsampwidth(2);wf.setframerate(sr)
        wf.writeframes(np.int16(music*32767).tobytes())
    return path


if __name__ == '__main__':
    print(make_video())
    print(make_music())
