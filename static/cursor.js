(() => {
    if (!matchMedia("(pointer:fine)").matches) return;
    const cursor = document.querySelector(".ivory-cursor");
    if (!cursor) return;
    let x = -100, y = -100, tx = -100, ty = -100;
    addEventListener("mousemove", (event) => { tx = event.clientX; ty = event.clientY; cursor.classList.add("is-visible"); });
    addEventListener("mouseout", (event) => { if (!event.relatedTarget) cursor.classList.remove("is-visible"); });
    document.addEventListener("mouseover", (event) => cursor.classList.toggle("is-active", Boolean(event.target.closest("a,button,input,textarea,select,[data-cursor]"))));
    function draw() { x += (tx-x)*.22; y += (ty-y)*.22; cursor.style.transform = `translate3d(${x}px,${y}px,0)`; requestAnimationFrame(draw); }
    draw();
})();
