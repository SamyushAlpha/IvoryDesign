(() => {
    "use strict";
    if (!location.pathname.startsWith("/my-lo/")) return;

    let previousUnread = null;
    const link = [...document.querySelectorAll("a")].find((item) => item.href.includes("/my-lo/support/"));
    const notificationsSupported = "Notification" in window;

    if (notificationsSupported && Notification.permission !== "denied") {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "ivory-support-notify-toggle";
        button.textContent = Notification.permission === "granted" ? "Support alerts on" : "Enable support alerts";
        button.addEventListener("click", async () => {
            const permission = await Notification.requestPermission();
            button.textContent = permission === "granted" ? "Support alerts on" : "Browser alerts blocked";
        });
        document.body.append(button);
    }

    function setBadge(count) {
        document.querySelectorAll(".ivory-support-badge").forEach((item) => item.remove());
        if (!link || !count) return;
        const badge = document.createElement("span");
        badge.className = "ivory-support-badge";
        badge.textContent = count > 99 ? "99+" : String(count);
        link.append(badge);
    }

    async function check() {
        try {
            const response = await fetch("/my-lo/support/api/conversations/?status=active", {credentials: "same-origin"});
            if (!response.ok) return;
            const data = await response.json();
            const unread = data.conversations.reduce((sum, item) => sum + (item.staff_unread_count || 0), 0);
            setBadge(unread);
            document.title = unread ? `(${unread}) ${document.title.replace(/^\(\d+\) /, "")}` : document.title.replace(/^\(\d+\) /, "");
            if (previousUnread !== null && unread > previousUnread && notificationsSupported && Notification.permission === "granted") {
                const newest = data.conversations.find((item) => item.staff_unread_count);
                new Notification("New Ivory Arvena message", {
                    body: `${newest?.visitor_name || "A visitor"} sent a new support message.`,
                    icon: "/static/images/Ivoryarvena.svg",
                    tag: "ivory-live-support",
                }).onclick = () => { window.focus(); location.href = "/my-lo/support/"; };
            }
            previousUnread = unread;
        } catch { /* Retry on the next poll. */ }
    }

    check();
    setInterval(check, 5000);
    document.addEventListener("visibilitychange", check);
})();
