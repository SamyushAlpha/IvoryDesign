from pathlib import Path
import math

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path('/Users/samyushgautam/Downloads/design/Instapost/insta video.mp4')
OUT=ROOT/'output/video'
AVENIR='/System/Library/Fonts/Avenir Next.ttc'

def rotated_text(text,size,color,angle,sub=None):
    f=ImageFont.truetype(AVENIR,size);sf=ImageFont.truetype(AVENIR,max(11,int(size*.42)))
    tmp=Image.new('RGBA',(900,220),(0,0,0,0));d=ImageDraw.Draw(tmp)
    b=d.textbbox((0,0),text,font=f);d.text(((900-(b[2]-b[0]))/2,52),text,font=f,fill=color)
    if sub:
        b=d.textbbox((0,0),sub,font=sf);d.text(((900-(b[2]-b[0]))/2,118),sub,font=sf,fill=color)
    return tmp.rotate(angle,Image.Resampling.BICUBIC,expand=True)

def paste_center(base,layer,cx,cy):
    base.alpha_composite(layer,(round(cx-layer.width/2),round(cy-layer.height/2)))

def box_mask(mask,cx,cy,w,h,angle):
    pts=cv2.boxPoints(((float(cx),float(cy)),(float(w),float(h)),float(angle))).astype(np.int32)
    cv2.fillConvexPoly(mask,pts,255)

def process():
    cap=cv2.VideoCapture(str(SOURCE));fps=cap.get(cv2.CAP_PROP_FPS);W=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH));H=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    path=OUT/'ivory-arvena-house-animation-pro-silent.mp4';writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'mp4v'),fps,(W,H));n=0
    while True:
        ok,frame=cap.read()
        if not ok:break
        t=n/fps
        if t<4.85:
            mask=np.zeros((H,W),np.uint8)
            # Track the stationary desk objects as the camera pushes into the drawing.
            if t<=3:
                mug_x,mug_y=335-8*t,438-13*t; coaster_x,coaster_y=332-8*t,665-18*t
            else:
                mug_x,mug_y=311-8*(t-3),399-190*(t-3);coaster_x,coaster_y=308-8*(t-3),611-168*(t-3)
            box_mask(mask,mug_x,mug_y,430,118,-18)
            box_mask(mask,coaster_x,coaster_y,315,118,-8)
            # Source drawing title block: remove only the old wordmark, following the paper curl.
            if .65<=t<=3.85:
                q=min(1,(t-.65)/1.35);x=3190-210*q+25*max(0,t-2);y=1735+155*q+18*max(0,t-2);ang=-10*(1-q)
                box_mask(mask,x,y,680,170,ang)
            # Fine-print source company name along the lower sheet edge.
            if t<.65:
                box_mask(mask,1910,2070,1420,48,0)
            elif t<=3.9:
                q=min(1,(t-.65)/1.35);y=2035+70*q+45*max(0,t-2);ang=-5*(1-q)
                box_mask(mask,1500,y,2500,54,ang)
            # Inpaint from adjacent mug/paper pixels for an integrated surface with no blocks.
            frame=cv2.inpaint(frame,mask,7,cv2.INPAINT_TELEA)
            im=Image.fromarray(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)).convert('RGBA')
            # Curved-object decals are small and follow the original angles.
            mug=rotated_text('IVORY ARVENA',30,(246,243,235,235),18)
            paste_center(im,mug,mug_x,mug_y)
            coaster=rotated_text('IVORY ARVENA',31,(246,243,235,245),8,'INTERIOR & DESIGN')
            paste_center(im,coaster,coaster_x,coaster_y)
            if .65<=t<=3.85:
                brand=rotated_text('IVORY ARVENA',41,(42,40,37,240),-ang,'INTERIOR & DESIGN')
                paste_center(im,brand,x,y)
            frame=cv2.cvtColor(np.asarray(im.convert('RGB')),cv2.COLOR_RGB2BGR)
        writer.write(frame);n+=1
    cap.release();writer.release();print(path)

if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True);process()
