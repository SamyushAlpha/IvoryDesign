/* Durable live support: HTTP persists sends; WebSockets deliver live updates. */
(() => {
    "use strict";
    const panel = document.getElementById("ivory-chat");
    if (!panel) return;
    const launcher = document.getElementById("ivory-chat-launcher");
    const closeButton = document.getElementById("ivory-chat-close");
    const form = document.getElementById("ivory-chat-form");
    const input = document.getElementById("ivory-chat-input");
    const sendButton = document.getElementById("ivory-chat-send");
    const messages = document.getElementById("ivory-chat-messages");
    const status = document.getElementById("ivory-chat-status");
    const presence = document.getElementById("ivory-chat-presence");
    const announcement = document.getElementById("ivory-chat-announcement");
    const revealButton = document.getElementById("ivory-chat-reveal");
    const suggestions = [...panel.querySelectorAll("[data-ivory-question]")];
    const transport = window.IvoryChatTransport;
    const media = window.IvorySupportMedia.composer(form, status);
    const renderedIds = new Set();
    let conversationId = "";
    let pending = false;
    let socket = null;
    let reconnectTimer = null;
    let reconnectDelay = 1000;
    let activeTyper = null;
    let renderQueue = Promise.resolve();
    let historyPoll = null;

    function setOpen(open) {
        panel.hidden = !open;
        launcher.setAttribute("aria-expanded", String(open));
        launcher.setAttribute("aria-label", open ? "Close Ivory Design support" : "Open Ivory Design support");
        (open ? input : launcher).focus();
        if (open) startSupport();
    }
    launcher.hidden = false;
    launcher.addEventListener("click", () => setOpen(panel.hidden));
    closeButton.addEventListener("click", () => setOpen(false));
    panel.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            event.preventDefault();
            setOpen(false);
        }
    });
    revealButton.addEventListener("click", () => activeTyper?.skip());
    window.addEventListener("pagehide", () => {
        clearTimeout(reconnectTimer);
        clearInterval(historyPoll);
        socket?.close();
        activeTyper?.cancel();
    });

    function updatePresence(conversation) {
        input.placeholder = conversation?.lead_state === "awaiting_name" ? "Your name…" : "Ask about Ivory Design…";
        if (!conversation) presence.textContent = "Ready for a team member";
        else if (conversation.status === "waiting") presence.textContent = "Waiting for a team member";
        else if (conversation.status === "bot_handled") presence.textContent = "Automated assistant";
        else if (conversation.status === "human_active") presence.textContent = conversation.assigned_name ? `Talking with ${conversation.assigned_name}` : "Ivory Design team member";
        else presence.textContent = "Conversation resolved";
    }

    function messageElement(message) {
        const item = document.createElement("p");
        item.className = `ivory-chat__message ivory-chat__message--${message.sender}`;
        const label = document.createElement("strong");
        label.textContent = message.label;
        const body = document.createElement("span");
        body.textContent = "";
        item.append(label, body);
        messages.append(item);
        messages.scrollTop = messages.scrollHeight;
        return { body, item };
    }

    async function renderMessage(message, progressive = false) {
        if (!message || renderedIds.has(message.id)) return;
        renderedIds.add(message.id);
        const element = messageElement(message);
        if (!progressive || message.sender === "visitor" || !transport) {
            element.body.textContent = message.body;
        } else {
            const typer = transport.createTypewriter((text) => {
                element.body.textContent = text;
                messages.scrollTop = messages.scrollHeight;
            }, { reducedMotion: window.matchMedia("(prefers-reduced-motion: reduce)").matches });
            activeTyper = typer;
            revealButton.hidden = false;
            typer.replace(message.body);
            await typer.finish();
            activeTyper = null;
            revealButton.hidden = true;
            announcement.textContent = `${message.label}: ${message.body}`;
        }
        while (messages.children.length > 100) messages.firstElementChild.remove();
        window.IvorySupportMedia.attachments(element.item, message.attachments);
        messages.scrollTop = messages.scrollHeight;
    }

    function enqueue(messagesToRender, progressive = true) {
        renderQueue = renderQueue.then(async () => {
            for (const message of messagesToRender || []) await renderMessage(message, progressive);
        });
        return renderQueue;
    }

    function uuid() {
        if (crypto.randomUUID) return crypto.randomUUID();
        const bytes = crypto.getRandomValues(new Uint8Array(16));
        bytes[6] = (bytes[6] & 15) | 64;
        bytes[8] = (bytes[8] & 63) | 128;
        return [...bytes].map((value, index) => value.toString(16).padStart(2, "0") + ([3, 5, 7, 9].includes(index) ? "-" : "")).join("");
    }

    async function getJson(url, options = {}) {
        const response = await fetch(url, { credentials: "same-origin", ...options });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            const error = new Error(data.error || "Support is temporarily unavailable.");
            error.status = response.status;
            throw error;
        }
        return data;
    }

    async function syncHistory() {
        try {
            const data = await getJson(form.dataset.historyUrl);
            updatePresence(data.conversation);
            if (!data.conversation) return;
            conversationId = data.conversation.id;
            messages.replaceChildren();
            renderedIds.clear();
            await enqueue(data.messages, false);
            connectSocket();
        } catch {
            status.textContent = "Saved messages could not be loaded. You can still use the Contact form below.";
        }
    }

    async function pollHistory() {
        if (!conversationId || pending || document.hidden) return;
        try {
            const data = await getJson(form.dataset.historyUrl);
            updatePresence(data.conversation);
            await enqueue((data.messages || []).filter((message) => !renderedIds.has(message.id)), true);
            status.textContent = "Messages are up to date.";
        } catch {
            status.textContent = "Checking for new messages…";
        }
    }

    async function startSupport() {
        if (pending) return;
        try {
            const data = await getJson(form.dataset.startUrl, {method:"POST", headers:{"X-CSRFToken":form.elements.csrfmiddlewaretoken.value}});
            if (conversationId !== data.conversation.id) {
                socket?.close(); socket = null; await renderQueue; messages.replaceChildren(); renderedIds.clear();
            }
            conversationId = data.conversation.id;
            updatePresence(data.conversation);
            await enqueue(data.messages, false);
            connectSocket();
        } catch { status.textContent = "Unable to start support. Please refresh and try again."; }
    }

    function connectSocket() {
        if (!conversationId || socket?.readyState === WebSocket.OPEN || socket?.readyState === WebSocket.CONNECTING) return;
        clearTimeout(reconnectTimer);
        const protocol = location.protocol === "https:" ? "wss:" : "ws:";
        socket = new WebSocket(`${protocol}//${location.host}/ws/support/${conversationId}/`);
        socket.addEventListener("open", () => {
            reconnectDelay = 1000;
            status.textContent = "Live updates connected.";
        });
        socket.addEventListener("message", (event) => {
            let data;
            try { data = JSON.parse(event.data); } catch { return; }
            if (data.kind !== "conversation") return;
            updatePresence(data.conversation);
            enqueue(data.messages, true);
        });
        socket.addEventListener("close", () => {
            socket = null;
            status.textContent = "Reconnecting to live updates…";
            reconnectTimer = setTimeout(async () => {
                await syncHistory();
                connectSocket();
            }, reconnectDelay);
            reconnectDelay = Math.min(reconnectDelay * 2, 15000);
        });
        socket.addEventListener("error", () => socket?.close());
    }


    historyPoll = setInterval(pollHistory, 3000);
    document.addEventListener("visibilitychange", () => {
        if (!document.hidden) pollHistory();
    });

    async function submitQuestion() {
        if (pending || media.recording) return;
        const message = input.value.trim();
        if ((!message && !media.file) || message.length > 600) {
            status.textContent = "Please enter a message between 1 and 600 characters.";
            input.focus();
            return;
        }
        pending = true;
        media.setBusy(true);
        sendButton.disabled = true;
        suggestions.forEach((button) => { button.disabled = true; });
        input.readOnly = true;
        status.textContent = "Sending securely…";
        try {
            const data = await window.IvorySupportMedia.send(form.action, message, uuid(), media.file, form.elements.csrfmiddlewaretoken.value, status);
            input.value = "";
            media.clear();
            conversationId = data.conversation.id;
            updatePresence(data.conversation);
            await enqueue(data.messages, true);
            connectSocket();
            status.textContent = data.duplicate ? "Message already received." : "Message sent.";
        } catch (error) {
            status.textContent = error.status === 429
                ? "Please pause before sending another message."
                : error.message;
        } finally {
            pending = false;
            media.setBusy(false);
            sendButton.disabled = false;
            suggestions.forEach((button) => { button.disabled = false; });
            input.readOnly = false;
            if (!panel.hidden) input.focus();
        }
    }

    form.addEventListener("submit", (event) => {
        event.preventDefault();
        submitQuestion();
    });
    input.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
            event.preventDefault();
            submitQuestion();
        }
    });
    suggestions.forEach((button) => button.addEventListener("click", () => {
        input.value = button.dataset.ivoryQuestion;
        input.focus();
        submitQuestion();
    }));

    syncHistory();
})();
