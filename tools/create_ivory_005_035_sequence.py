from pathlib import Path
import math
import wave

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

ROOT=Path(__file__).resolve().parents[1]
GEN=Path('/Users/samyushgautam/.codex/generated_images/01a0afe9-a02e-7b43-a604-931bcf3390ee')
OUT=ROOT/'output/video'
SCENES=[
 GEN/'exec-0cf7b18e-4125-4ed1-aa24-50d28234a081.png', # completed cutaway, reference 0:05
 GEN/'exec-9fd81dc6-4d2d-424c-8a54-683f375d5d91.png', # flat drawing, reference 0:10
 GEN/'exec-2030459e-dfc0-49df-8a5c-28501456b087.png', # slab/walls, reference 0:15
 GEN/'exec-feb2e62d-ca2a-4b45-84b9-bc10ae313842.png', # rooms/furniture, reference 0:20
 GEN/'exec-43b3373a-1063-4321-b441-bd4ea3c5a145.png', # upper floor/roof, reference 0:30
 GEN/'exec-0cf7b18e-4125-4ed1-aa24-50d28234a081.png', # completed return, reference 0:35
]
W,H,FPS,DURATION=1080,1920,30,30

def ease(x):
 x=np.clip(x,0,1);return x*x*(3-2*x)

def frame_crop(im,p,i):
 base=max(W/im.width,H/im.height)
 # Consistent clockwise aerial orbit and breathing zoom like the reference sequence.
 zoom=(1.035+0.035*math.sin(math.pi*p)) if i not in (1,) else (1.01+0.025*p)
 s=base*zoom; rw,rh=round(im.width*s),round(im.height*s)
 rs=im.resize((rw,rh),Image.Resampling.LANCZOS)
 direction=[1,-1,1,-1,1,-1][i]
 cx=rw//2+round(direction*95*(p-.5));cy=rh//2+round(38*math.sin(2*math.pi*p))
 return rs.crop((cx-W//2,cy-H//2,cx+W//2,cy+H//2)).convert('RGB')

def brand_logo():
 src=Image.open(ROOT/'static/images/ivoryarvena-email-logo.png').convert('RGB')
 art=src.crop((0,0,800,393)).resize((230,113),Image.Resampling.LANCZOS)
 mask=ImageOps.invert(ImageOps.grayscale(art)).point(lambda p:0 if p<25 else min(255,int(p*1.35)))
 out=Image.new('RGBA',art.size,(252,248,239,0));out.putalpha(mask);return out

def centered(d,y,text,fnt,fill):
 b=d.textbbox((0,0),text,font=fnt);d.text(((W-(b[2]-b[0]))/2,y),text,font=fnt,fill=fill)

def build_video():
 ims=[Image.open(p).convert('RGB') for p in SCENES]; logo=brand_logo(); avenir='/System/Library/Fonts/Avenir Next.ttc'
 path=OUT/'ivory-arvena-005-035-silent.mp4';writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'mp4v'),FPS,(W,H))
 transition=.72
 for n in range(FPS*DURATION):
  t=n/FPS;i=min(5,int(t/5));local=(t-i*5)/5
  frame=frame_crop(ims[i],local,i)
  if i<5 and local>(1-transition/5):
   p=ease((local-(1-transition/5))/(transition/5));nxt=frame_crop(ims[i+1],p*.1,i+1)
   # A soft paper-white sweep echoes the reference's continuous model assembly.
   mask=Image.new('L',(W,H),0);md=ImageDraw.Draw(mask);edge=int((W+360)*p)-180
   if edge>0: md.rectangle((0,0,edge,H),fill=255)
   mask=mask.filter(ImageFilter.GaussianBlur(70))
   frame=Image.composite(nxt,frame,mask)
  frame=ImageEnhance.Contrast(frame).enhance(1.02)
  # Branding appears only in the last 2.8 seconds over the restored completed model.
  if t>=27.2:
   p=float(ease((t-27.2)/.65));rgba=frame.convert('RGBA')
   rgba=Image.alpha_composite(rgba,Image.new('RGBA',(W,H),(10,9,8,int(72*p))))
   panel=Image.new('RGBA',(W,450),(12,10,8,int(166*p)));rgba.alpha_composite(panel,(0,H-450))
   lg=logo.copy();lg.putalpha(lg.getchannel('A').point(lambda a:int(a*p)));rgba.alpha_composite(lg,((W-lg.width)//2,H-420))
   d=ImageDraw.Draw(rgba);centered(d,H-290,'IVORY ARVENA',ImageFont.truetype(avenir,44),(252,248,239,int(255*p)))
   centered(d,H-235,'INTERIOR & DESIGN',ImageFont.truetype(avenir,21),(252,248,239,int(225*p)))
   d.line((220,H-184,860,H-184),fill=(252,248,239,int(95*p)),width=1)
   centered(d,H-150,'ivoryarvena.vercel.app',ImageFont.truetype(avenir,27),(252,248,239,int(250*p)))
   centered(d,H-106,'ivorydesign2083@gmail.com',ImageFont.truetype(avenir,26),(252,248,239,int(235*p)))
   frame=rgba.convert('RGB')
  writer.write(cv2.cvtColor(np.asarray(frame),cv2.COLOR_RGB2BGR))
 writer.release();return path

def build_music():
 sr=44100;count=sr*DURATION;t=np.arange(count)/sr;sig=np.zeros(count)
 # Original restrained architectural score, music only.
 for f,a,ph in [(73.42,.105,.2),(110,.075,1.1),(146.83,.06,2.2),(220,.035,.7),(293.66,.022,1.8)]:
  sig+=a*np.sin(2*np.pi*f*t+ph)*(.72+.28*np.sin(2*np.pi*.06*t+ph))
 for beat in np.arange(.5,29.5,1.25):
  s=int(beat*sr);ln=int(.5*sr);x=np.arange(ln)/sr;sig[s:s+ln]+=.04*np.sin(2*np.pi*220*x)*np.exp(-8*x)
 rng=np.random.default_rng(205);sig+=.035*np.convolve(rng.normal(0,1,count),np.ones(1400)/1400,mode='same')
 env=np.ones(count);f=int(1.2*sr);env[:f]=np.linspace(0,1,f);env[-f:]=np.linspace(1,0,f);sig*=env
 sig/=max(1,np.max(np.abs(sig))/.88);path=OUT/'ivory-arvena-005-035-music.wav'
 with wave.open(str(path),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(sr);w.writeframes(np.int16(sig*32767).tobytes())
 return path

if __name__=='__main__':
 OUT.mkdir(parents=True,exist_ok=True);print(build_video());print(build_music())
