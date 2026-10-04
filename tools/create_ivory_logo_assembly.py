from pathlib import Path
import math
import random

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/video'
W,H,FPS,DURATION=1920,1080,30,3.7

def smooth(x):
    x=max(0,min(1,x)); return x*x*(3-2*x)

def prepare_logo():
    src=Image.open(ROOT/'static/images/ivoryarvena-email-logo.png').convert('RGB')
    ink=ImageOps.invert(ImageOps.grayscale(src))
    box=ink.point(lambda p:255 if p>20 else 0).getbbox()
    src=src.crop(box)
    # Keep the sofa mark and full Ivory Arvena wordmark crisp at the final lockup.
    max_w,max_h=1000,600
    scale=min(max_w/src.width,max_h/src.height)
    return src.resize((round(src.width*scale),round(src.height*scale)),Image.Resampling.LANCZOS)

def fragments(logo):
    # Uneven tiles create the reference's abstract pieces while retaining exact final alignment.
    xs=[0,.08,.18,.29,.42,.57,.71,.83,.92,1]
    ys=[0,.12,.29,.48,.65,.80,1]
    rng=random.Random(2083); items=[]
    for yi in range(len(ys)-1):
        for xi in range(len(xs)-1):
            x0=round(xs[xi]*logo.width);x1=round(xs[xi+1]*logo.width)
            y0=round(ys[yi]*logo.height);y1=round(ys[yi+1]*logo.height)
            tile=logo.crop((x0,y0,x1,y1)).convert('RGBA')
            alpha=ImageOps.invert(ImageOps.grayscale(tile.convert('RGB'))).point(lambda p:0 if p<12 else min(255,int(p*1.3)))
            if not alpha.getbbox(): continue
            black=Image.new('RGBA',tile.size,(14,13,12,0));black.putalpha(alpha)
            # Start positions stretch across the scene with exaggerated depth and rotation.
            items.append(dict(img=black,x=x0,y=y0,
                sx=rng.uniform(-1500,1500),sy=rng.uniform(-760,760),
                scale=rng.uniform(.35,3.2),angle=rng.uniform(-120,120),
                delay=rng.uniform(0,.34)))
    return items

def make_video():
    logo=prepare_logo();items=fragments(logo)
    final_x=(W-logo.width)//2;final_y=(H-logo.height)//2-92
    avenir='/System/Library/Fonts/Avenir Next.ttc'
    fraunces='/Users/samyushgautam/Library/Application Support/Claude/local-agent-mode-sessions/skills-plugin/6ffd7260-72be-4d71-ab00-b8845ed6edfd/c4c0b788-3685-4979-a803-058c90ba8168/skills/morning/assets/fonts/fraunces-latin-600-normal.woff2'
    path=OUT/'ivory-arvena-logo-assembly-silent.mp4'
    writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'mp4v'),FPS,(W,H))
    for n in range(round(FPS*DURATION)):
        t=n/FPS; progress=t/2.85
        frame=Image.new('RGBA',(W,H),(250,250,249,255))
        # Very subtle white studio gradient gives pieces a sense of depth.
        grad=np.zeros((H,W,4),dtype=np.uint8)
        for y in range(H):
            v=int(5*abs(y-H*.48)/(H*.52));grad[y,:,0:3]=max(242,250-v);grad[y,:,3]=255
        frame=Image.fromarray(grad,'RGBA')
        ordered=sorted(items,key=lambda q:q['scale'],reverse=True)
        for it in ordered:
            p=smooth((progress-it['delay'])/(1-it['delay']))
            if p<=0: continue
            # Cubic depth collapse toward the exact logo tile location.
            depth=(1-p)**2
            cx=final_x+it['x']+it['img'].width/2 + it['sx']*depth
            cy=final_y+it['y']+it['img'].height/2 + it['sy']*depth
            scale=1+(it['scale']-1)*depth
            tw=max(1,round(it['img'].width*scale));th=max(1,round(it['img'].height*scale))
            tile=it['img'].resize((tw,th),Image.Resampling.BICUBIC)
            angle=it['angle']*depth
            tile=tile.rotate(angle,Image.Resampling.BICUBIC,expand=True)
            if depth>.28: tile=tile.filter(ImageFilter.GaussianBlur(1.8*depth))
            frame.alpha_composite(tile,(round(cx-tile.width/2),round(cy-tile.height/2)))
        # At settle time, dissolve to the exact source logo so seams disappear.
        if t>=2.55:
            p=smooth((t-2.55)/.38)
            logo_mask=ImageOps.invert(ImageOps.grayscale(logo)).point(lambda a:0 if a<10 else min(255,int(a*1.25*p)))
            exact_logo=Image.new('RGBA',logo.size,(14,13,12,0));exact_logo.putalpha(logo_mask)
            exact=Image.new('RGBA',(W,H),(0,0,0,0)); exact.alpha_composite(exact_logo,(final_x,final_y))
            frame=Image.alpha_composite(frame,exact)
        if t>=2.72:
            p=smooth((t-2.72)/.42)
            d=ImageDraw.Draw(frame)
            def center(y,text,fnt,fill):
                b=d.textbbox((0,0),text,font=fnt);d.text(((W-(b[2]-b[0]))/2,y),text,font=fnt,fill=fill)
            base_y=final_y+logo.height+28
            center(base_y,'Thoughtfully designed spaces, crafted to feel like home.',ImageFont.truetype(fraunces,31),(38,35,31,int(225*p)))
            d.line((590,base_y+58,1330,base_y+58),fill=(40,37,33,int(75*p)),width=1)
            center(base_y+82,'ivoryarvena.vercel.app   •   ivorydesign2083@gmail.com',ImageFont.truetype(avenir,25),(35,33,30,int(235*p)))
        writer.write(cv2.cvtColor(np.asarray(frame.convert('RGB')),cv2.COLOR_RGB2BGR))
    writer.release();return path

if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True);print(make_video())
