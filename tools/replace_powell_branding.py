from pathlib import Path
import math

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path('/Users/samyushgautam/Downloads/design/Instapost/insta video.mp4')
OUT=ROOT/'output/video'

def logo_mark(width=430):
    src=Image.open(ROOT/'static/images/ivoryarvena-email-logo.png').convert('RGB')
    ink=ImageOps.invert(ImageOps.grayscale(src));box=ink.point(lambda p:255 if p>18 else 0).getbbox();src=src.crop(box)
    h=round(src.height*width/src.width);src=src.resize((width,h),Image.Resampling.LANCZOS)
    alpha=ImageOps.invert(ImageOps.grayscale(src)).point(lambda p:0 if p<12 else min(255,int(p*1.25)))
    out=Image.new('RGBA',src.size,(21,20,18,0));out.putalpha(alpha);return out

def center(draw,box,text,font,fill):
    b=draw.textbbox((0,0),text,font=font);x=(box[0]+box[2]-(b[2]-b[0]))/2;y=(box[1]+box[3]-(b[3]-b[1]))/2
    draw.text((x,y),text,font=font,fill=fill)

def process():
    cap=cv2.VideoCapture(str(SOURCE));fps=cap.get(cv2.CAP_PROP_FPS);w=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH));h=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    outpath=OUT/'ivory-arvena-house-animation-silent.mp4';writer=cv2.VideoWriter(str(outpath),cv2.VideoWriter_fourcc(*'mp4v'),fps,(w,h))
    avenir='/System/Library/Fonts/Avenir Next.ttc';bold=ImageFont.truetype(avenir,44);small=ImageFont.truetype(avenir,25);tiny=ImageFont.truetype(avenir,20)
    mark=logo_mark(360);n=0
    while True:
        ok,fr=cap.read()
        if not ok:break
        t=n/fps
        if t<5.0:
            im=Image.fromarray(cv2.cvtColor(fr,cv2.COLOR_BGR2RGB)).convert('RGBA');d=ImageDraw.Draw(im,'RGBA')
            # Replace the branded coaster with a clean navy Ivory Arvena coaster.
            cy=700-18*t if t<=3 else 646-168*(t-3);cx=338-9*t
            rx,ry=177,147
            d.ellipse((cx-rx,cy-ry,cx+rx,cy+ry),fill=(21,27,63,255),outline=(47,53,88,255),width=3)
            center(d,(cx-rx,cy-50,cx+rx,cy+20),'IVORY ARVENA',ImageFont.truetype(avenir,32),(247,244,236,255))
            center(d,(cx-rx,cy+18,cx+rx,cy+72),'INTERIOR & DESIGN',ImageFont.truetype(avenir,15),(247,244,236,220))
            # Cover the curved mug wordmark and add the Ivory name in its place.
            my=475-13*t if t<=3 else 436-195*(t-3);mx=372-8*t
            patch=Image.new('RGBA',(510,210),(0,0,0,0));pd=ImageDraw.Draw(patch)
            pd.rounded_rectangle((0,8,510,202),radius=62,fill=(28,32,68,255))
            center(pd,(0,0,510,210),'IVORY ARVENA',ImageFont.truetype(avenir,35),(247,244,236,250))
            patch=patch.rotate(-18,Image.Resampling.BICUBIC,expand=True)
            im.alpha_composite(patch,(round(mx-patch.width/2),round(my-patch.height/2)))
            # Remove the source firm's legal line from the rolled/unrolled plan.
            if t<.8:
                d.rounded_rectangle((1320,2040,2550,2110),radius=28,fill=(245,245,243,245))
            else:
                legal_y=2070+max(0,t-2.5)*90
                d.rectangle((285,legal_y,2820,legal_y+90),fill=(246,247,246,255))
            # Replace the architectural title block while it is visible.
            if .8<=t<=3.85:
                y=1760+max(0,t-3.0)*255
                x=2670-20*(t-2.5)
                card=(x,y,x+1020,y+300)
                d.rounded_rectangle(card,radius=6,fill=(247,248,247,250),outline=(176,178,176,150),width=2)
                lg=mark.resize((245,round(mark.height*245/mark.width)),Image.Resampling.LANCZOS)
                im.alpha_composite(lg,(round(x+95),round(y+54)))
                d.text((x+390,y+71),'IVORY ARVENA',font=bold,fill=(28,27,25,255))
                d.text((x+393,y+127),'INTERIOR & DESIGN',font=small,fill=(55,52,47,235))
                d.text((x+393,y+183),'ivoryarvena.vercel.app',font=tiny,fill=(65,61,55,220))
                d.text((x+393,y+217),'ivorydesign2083@gmail.com',font=tiny,fill=(65,61,55,220))
            fr=cv2.cvtColor(np.asarray(im.convert('RGB')),cv2.COLOR_RGB2BGR)
        writer.write(fr);n+=1
    cap.release();writer.release();print(outpath)

if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True);process()
