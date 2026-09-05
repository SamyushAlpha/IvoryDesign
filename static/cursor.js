(() => {
    if (!matchMedia("(pointer:fine)").matches) return;
    const cursor = document.querySelector(".ivory-cursor");
    if (!cursor) return;
    let x = -100, y = -100, tx = -100, ty = -100, angle = 0;
    const interactiveSelector = "a,button,input,textarea,select,[data-cursor]";
    const readingSelector = "h1,h2,h3,h4,p,li,label,blockquote,.section-eyebrow,.footer-eyebrow";
    addEventListener("mousemove", (event) => {
        const dx = event.clientX - tx;
        const dy = event.clientY - ty;
        tx = event.clientX;
        ty = event.clientY;
        if (Math.abs(dx) + Math.abs(dy) > 2) angle = Math.atan2(dy, dx) * 180 / Math.PI;
        cursor.style.setProperty("--cursor-angle", `${angle}deg`);
        cursor.classList.add("is-visible");
    });
    addEventListener("mouseout", (event) => { if (!event.relatedTarget) cursor.classList.remove("is-visible"); });
    document.addEventListener("mouseover", (event) => {
        const interactive = Boolean(event.target.closest(interactiveSelector));
        cursor.classList.toggle("is-active", interactive);
        cursor.classList.toggle("is-reading", !interactive && Boolean(event.target.closest(readingSelector)));
    });
    function draw() { x += (tx-x)*.22; y += (ty-y)*.22; cursor.style.transform = `translate3d(${x}px,${y}px,0)`; requestAnimationFrame(draw); }
    draw();
})();
