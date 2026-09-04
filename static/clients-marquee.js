(() => {
    const marquee = document.querySelector('.clients-marquee');
    if (!marquee) return;
    const track = marquee.querySelector('.clients-track');
    const group = track.querySelector('.clients-group');
    const originals = Array.from(group.children).map(item => item.cloneNode(true));
    const fill = () => {
        group.replaceChildren(...originals.map(item => item.cloneNode(true)));
        // Each half must fill the viewport even when only one logo is published.
        while (group.scrollWidth < marquee.clientWidth && originals.length) {
            originals.forEach(item => {
                const copy = item.cloneNode(true);
                copy.setAttribute('aria-hidden', 'true');
                copy.querySelector('img').alt = '';
                group.append(copy);
            });
        }
        const duplicate = group.cloneNode(true);
        duplicate.setAttribute('aria-hidden', 'true');
        duplicate.querySelectorAll('img').forEach(img => { img.alt = ''; });
        track.lastElementChild.replaceWith(duplicate);
        track.style.animationDuration = `${Math.max(group.scrollWidth / 40, 12)}s`;
    };
    new ResizeObserver(fill).observe(marquee);
    fill();
})();
