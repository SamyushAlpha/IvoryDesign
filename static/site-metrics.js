(() => {
    "use strict";
    const total = document.getElementById("ivory-total-visits");
    const online = document.getElementById("ivory-online-visitors");
    if (!total && !online) return;

    async function refreshMetrics() {
        if (document.hidden) return;
        try {
            const response = await fetch("/website-metrics/", {
                credentials: "same-origin",
                cache: "no-store",
                headers: {"X-Requested-With": "XMLHttpRequest"},
            });
            if (!response.ok) return;
            const data = await response.json();
            if (total) total.textContent = Number(data.total_visits || 0).toLocaleString();
            if (online) online.textContent = Number(data.online_now || 0).toLocaleString();
        } catch (_) {
            // Keep the last successfully displayed values during a connection gap.
        }
    }

    refreshMetrics();
    const timer = setInterval(refreshMetrics, 15000);
    document.addEventListener("visibilitychange", refreshMetrics);
    window.addEventListener("pagehide", () => clearInterval(timer), {once: true});
})();
