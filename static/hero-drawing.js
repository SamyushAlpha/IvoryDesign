(() => {
    const drawing = document.querySelector('.hero-drawing');
    if (!drawing) return;
    const motion = matchMedia('(prefers-reduced-motion: reduce)');
    const scenes = Array.from(drawing.querySelectorAll('.residence-scene'));
    const reveals = Array.from(drawing.querySelectorAll('.reference-reveal'));
    const drawDuration = 18000;
    const holdDuration = 3200;
    const fadeDuration = 1500;
    let elapsed = 0;
    let previous = null;
    let frame = null;
    let visible = true;
    let activeIndex = 0;
    const clamp = value => Math.min(1, Math.max(0, value));

    function reset() {
        elapsed = 0;
        scenes.forEach((scene, index) => {
            scene.style.display = index === activeIndex ? '' : 'none';
            scene.setAttribute('opacity', '1');
        });
        reveals.forEach(reveal => reveal.setAttribute('width', '0'));
    }
    function render() {
        const drawProgress = clamp(elapsed / drawDuration);
        reveals[activeIndex].setAttribute('width', String(700 * drawProgress));
        if (drawProgress < 1) {
            scenes[activeIndex].setAttribute('opacity', '1');
            return;
        }
        const fadeProgress = clamp((elapsed - drawDuration - holdDuration) / fadeDuration);
        scenes[activeIndex].setAttribute('opacity', String(1 - fadeProgress));
        if (fadeProgress === 1) { activeIndex = (activeIndex + 1) % scenes.length; reset(); }
    }
    function tick(now) {
        if (previous !== null) elapsed += now - previous;
        previous = now;
        render();
        frame = requestAnimationFrame(tick);
    }
    function update() {
        if (frame !== null) cancelAnimationFrame(frame);
        frame = null;
        previous = null;
        if (motion.matches) {
            drawing.classList.remove('is-animating');
            scenes.forEach((scene, index) => { scene.style.display = index === 0 ? '' : 'none'; scene.setAttribute('opacity', '1'); });
            reveals.forEach(reveal => reveal.setAttribute('width', '700'));
        } else {
            drawing.classList.add('is-animating');
            render();
            if (visible && !document.hidden) frame = requestAnimationFrame(tick);
        }
    }
    new IntersectionObserver(entries => { visible = entries[0].isIntersecting; update(); }).observe(drawing);
    document.addEventListener('visibilitychange', update);
    motion.addEventListener('change', update);
    drawing.classList.add('is-ready');
    reset();
    update();
})();
