(() => {
    const section = document.querySelector("[data-horizontal-works]");
    if (!section) return;
    const track = section.querySelector(".works-grid");
    const viewport = section.querySelector(".works-viewport");
    const reduced = matchMedia("(prefers-reduced-motion: reduce)");
    const mobile = matchMedia("(max-width: 760px)");
    let distance = 0;

    function measure() {
        if (mobile.matches || reduced.matches) {
            section.style.removeProperty("height");
            track.style.removeProperty("transform");
            return;
        }
        distance = Math.max(0, track.scrollWidth - viewport.clientWidth);
        section.style.height = `${innerHeight + distance}px`;
        update();
    }

    function update() {
        if (mobile.matches || reduced.matches) return;
        const rect = section.getBoundingClientRect();
        const travelled = Math.min(distance, Math.max(0, -rect.top));
        track.style.transform = `translate3d(${-travelled}px,0,0)`;
    }

    addEventListener("scroll", update, {passive:true});
    addEventListener("resize", measure);
    addEventListener("load", measure, {once:true});
    document.fonts?.ready.then(measure);
    measure();
})();
