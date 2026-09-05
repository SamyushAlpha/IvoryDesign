(() => {
  const viewer=document.querySelector('.project-viewer'); if(!viewer)return;
  const image=document.getElementById('project-viewer-image'),title=document.getElementById('project-viewer-title'),count=document.getElementById('project-viewer-count'),caption=document.getElementById('project-viewer-caption'),thumbs=document.getElementById('project-viewer-thumbs');
  let assets=[],index=0,lastTrigger=null;
  function show(next){if(!assets.length)return;index=(next+assets.length)%assets.length;image.src=assets[index].src;image.alt=assets[index].caption;caption.textContent=assets[index].caption;count.textContent=`${String(index+1).padStart(2,'0')} / ${String(assets.length).padStart(2,'0')}`;thumbs.querySelectorAll('button').forEach((b,i)=>b.classList.toggle('is-active',i===index));}
  function open(button){lastTrigger=button;const source=button.closest('.project-row').querySelector('.project-assets');assets=[...source.querySelectorAll('img')].map(i=>({src:i.dataset.src,caption:i.dataset.caption||source.dataset.name}));title.textContent=source.dataset.name;thumbs.replaceChildren(...assets.map((item,i)=>{const b=document.createElement('button');b.type='button';b.innerHTML=`<img src="${item.src}" alt="">`;b.onclick=()=>show(i);return b;}));viewer.hidden=false;document.body.classList.add('viewer-open');show(0);viewer.querySelector('[data-viewer-close]').focus();}
  function close(){viewer.hidden=true;document.body.classList.remove('viewer-open');lastTrigger?.focus();}
  document.querySelectorAll('[data-project-open]').forEach(b=>b.addEventListener('click',()=>open(b)));
  document.querySelectorAll('[data-filter]').forEach(b=>b.addEventListener('click',()=>{document.querySelectorAll('[data-filter]').forEach(x=>x.classList.toggle('is-active',x===b));document.querySelectorAll('.project-row').forEach(row=>row.hidden=b.dataset.filter!=='all'&&row.dataset.category!==b.dataset.filter);}));
  viewer.querySelector('[data-viewer-close]').onclick=close;viewer.querySelector('[data-viewer-prev]').onclick=()=>show(index-1);viewer.querySelector('[data-viewer-next]').onclick=()=>show(index+1);
  addEventListener('keydown',e=>{if(viewer.hidden)return;if(e.key==='Escape')close();if(e.key==='ArrowLeft')show(index-1);if(e.key==='ArrowRight')show(index+1);});
})();
