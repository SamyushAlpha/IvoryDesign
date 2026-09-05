(() => {
  document.querySelectorAll('[data-filter]').forEach(b=>b.addEventListener('click',()=>{document.querySelectorAll('[data-filter]').forEach(x=>x.classList.toggle('is-active',x===b));document.querySelectorAll('.project-row').forEach(row=>row.hidden=b.dataset.filter!=='all'&&row.dataset.category!==b.dataset.filter);}));
})();
