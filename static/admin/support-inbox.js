(() => {
    "use strict";
    const root = document.querySelector(".support-inbox");
    if (!root) return;
    const canChange = root.dataset.canChange === "true";
    const list = document.getElementById("support-conversation-list");
    const messageList = document.getElementById("support-message-list");
    const empty = document.getElementById("support-empty");
    const activeDetail = document.getElementById("support-active-detail");
    const connection = document.getElementById("support-connection");
    const actionStatus = document.getElementById("support-action-status");
    const csrf = document.querySelector("[name=csrfmiddlewaretoken]")?.value || "";
    const replyForm = document.getElementById("support-reply-form");
    const media = replyForm ? window.IvorySupportMedia.composer(replyForm, actionStatus) : null;
    let pending = false;
    let filter = "active";
    let selectedId = "";
    let reconnectDelay = 1000;
    let socket;
    let listPoll;
    let historyPoll;

    function textNode(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        node.textContent = text;
        return node;
    }

    async function getJson(url, options = {}) {
        const response = await fetch(url, { credentials: "same-origin", ...options });
        if (response.redirected || response.status === 401 || response.status === 403) {
            throw new Error("Please sign in again with a staff account that has live support access.");
        }
        if (!response.headers.get("content-type")?.includes("application/json")) {
            throw new Error("The inbox could not load. Please retry; if this continues, restart the site after applying its database updates.");
        }
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || "Request failed.");
        return data;
    }

    function renderConversationList(conversations) {
        list.replaceChildren();
        if (!conversations.length) {
            list.append(textNode("p", "support-inbox__none", "No conversations in this view."));
            return;
        }
        conversations.forEach((conversation) => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "support-inbox__conversation";
            button.dataset.id = conversation.id;
            button.setAttribute("aria-current", String(conversation.id === selectedId));
            const heading = textNode("strong", "", conversation.visitor_name || "Anonymous visitor");
            const meta = textNode("span", "", conversation.status_label + (conversation.assigned_name ? ` · ${conversation.assigned_name}` : ""));
            const time = textNode("time", "", new Date(conversation.last_activity_at).toLocaleString());
            button.append(heading, meta, time);
            if (conversation.staff_unread_count) {
                button.append(textNode("span", "support-inbox__unread", String(conversation.staff_unread_count)));
            }
            button.addEventListener("click", () => selectConversation(conversation.id));
            list.append(button);
        });
    }

    async function loadList() {
        try {
            const data = await getJson(`/admin/support/api/conversations/?status=${encodeURIComponent(filter)}`);
            renderConversationList(data.conversations);
        } catch (error) {
            const notice = textNode("p", "support-inbox__error", error.message);
            notice.setAttribute("role", "alert");
            const retry = textNode("button", "support-inbox__retry", "Retry loading conversations");
            retry.type = "button";
            retry.addEventListener("click", () => {
                retry.disabled = true;
                loadList();
            });
            list.replaceChildren(notice, retry);
        }
    }

    function renderMessages(messages) {
        messageList.replaceChildren();
        messages.forEach((message) => {
            const item = document.createElement("article");
            item.className = `support-inbox__message support-inbox__message--${message.sender}`;
            item.append(textNode("strong", "", message.label));
            item.append(textNode("p", "", message.body));
            window.IvorySupportMedia.attachments(item, message.attachments);
            item.append(textNode("time", "", new Date(message.created_at).toLocaleString()));
            messageList.append(item);
        });
        messageList.scrollTop = messageList.scrollHeight;
    }

    async function selectConversation(id, quiet = false) {
        selectedId = id;
        if (!quiet) actionStatus.textContent = "Loading conversation…";
        try {
            const data = await getJson(`/admin/support/api/${id}/`);
            empty.hidden = true;
            activeDetail.hidden = false;
            document.getElementById("support-visitor-name").textContent = data.conversation.visitor_name || "Anonymous visitor";
            document.getElementById("support-conversation-status").textContent = data.conversation.status_label + (data.conversation.assigned_name ? ` · Assigned to ${data.conversation.assigned_name}` : "");
            document.getElementById("support-visitor-phone").textContent = data.conversation.visitor_phone ? `Phone: ${data.conversation.visitor_phone}` : "Phone not collected yet";
            renderMessages(data.messages);
            if (!quiet) actionStatus.textContent = "Conversation loaded.";
            await loadList();
        } catch (error) {
            if (!quiet) actionStatus.textContent = error.message;
        }
    }

    async function action(path, payload) {
        if (!selectedId || !canChange || pending || media?.recording) return;
        pending = true; media?.setBusy(true);
        root.querySelectorAll('.support-inbox__actions button, #support-reply-form button[type="submit"]').forEach(b => b.disabled = true);
        actionStatus.textContent = "Saving…";
        try {
            if (path === "reply") await window.IvorySupportMedia.send(`/admin/support/api/${selectedId}/reply/`, payload.message, payload.client_message_id, media.file, csrf, actionStatus);
            else await getJson(`/admin/support/api/${selectedId}/${path}/`, {
                method: "POST",
                headers: { "X-CSRFToken": csrf, ...(payload ? { "Content-Type": "application/json" } : {}) },
                body: payload ? JSON.stringify(payload) : undefined,
            });
            await selectConversation(selectedId);
            actionStatus.textContent = "Saved.";
            return true;
        } catch (error) {
            actionStatus.textContent = error.message;
            return false;
        } finally {
            pending = false; media?.setBusy(false);
            root.querySelectorAll('.support-inbox__actions button, #support-reply-form button[type="submit"]').forEach(b => b.disabled = false);
        }
    }

    document.querySelectorAll("[data-support-filter]").forEach((button) => {
        button.addEventListener("click", () => {
            filter = button.dataset.supportFilter;
            document.querySelectorAll("[data-support-filter]").forEach((item) => item.setAttribute("aria-pressed", String(item === button)));
            loadList();
        });
    });
    document.getElementById("support-claim")?.addEventListener("click", () => action("claim"));
    document.getElementById("support-assistant")?.addEventListener("click", () => action("assistant"));
    document.getElementById("support-resolve")?.addEventListener("click", () => action("resolve"));
    async function sendReply(event) {
        event?.preventDefault();
        const input = document.getElementById("support-reply");
        const message = input.value.trim();
        if ((!message && !media.file) || pending || media.recording) return;
        input.readOnly = true;
        try {
            const saved = await action("reply", { message, client_message_id: crypto.randomUUID() });
            if (saved) { input.value = ""; media.clear(); input.focus(); }
        } finally { input.readOnly = false; }
    }
    replyForm?.addEventListener("submit", sendReply);
    if (replyForm) window.IvorySupportMedia.bindEnterToSend(document.getElementById("support-reply"), sendReply, () => pending || media.recording);

    function connect() {
        const protocol = location.protocol === "https:" ? "wss:" : "ws:";
        socket = new WebSocket(`${protocol}//${location.host}/ws/support/staff/`);
        socket.addEventListener("open", () => {
            reconnectDelay = 1000;
            connection.textContent = "Live updates connected";
        });
        socket.addEventListener("message", (event) => {
            let data;
            try { data = JSON.parse(event.data); } catch { return; }
            if (data.kind !== "conversation") return;
            loadList();
            if (selectedId === data.conversation?.id) selectConversation(selectedId);
        });
        socket.addEventListener("close", () => {
            connection.textContent = "Reconnecting to live updates…";
            setTimeout(connect, reconnectDelay);
            reconnectDelay = Math.min(reconnectDelay * 2, 15000);
        });
        socket.addEventListener("error", () => socket.close());
    }

    loadList();
    connect();
    listPoll = setInterval(() => {
        if (!document.hidden && !pending) loadList();
    }, 3000);
    historyPoll = setInterval(() => {
        if (!document.hidden && selectedId && !pending) selectConversation(selectedId, true);
    }, 2500);
    document.addEventListener("visibilitychange", () => {
        if (!document.hidden) {
            loadList();
            if (selectedId) selectConversation(selectedId, true);
        }
    });
    window.addEventListener("pagehide", () => {
        clearInterval(listPoll);
        clearInterval(historyPoll);
        socket?.close();
    });
})();
