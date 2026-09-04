/* Small, dependency-free streaming and animation helpers; also tested in Node. */
(function (root, factory) {
    if (typeof module === "object" && module.exports) module.exports = factory();
    else root.IvoryChatTransport = factory();
})(typeof window === "undefined" ? {} : window, function () {
    "use strict";

    function createTypewriter(render, options = {}) {
        const schedule = options.schedule || setTimeout;
        const unschedule = options.unschedule || clearTimeout;
        let target = "", visible = "", timer = null, instant = !!options.reducedMotion;
        let waiters = [];
        function settled() {
            if (visible === target) {
                waiters.splice(0).forEach(resolve => resolve());
            }
        }
        function tick() {
            timer = null;
            if (instant) visible = target;
            else {
                const remaining = target.slice(visible.length);
                visible += (remaining.match(/^\s*\S+\s*/) || [remaining])[0];
            }
            render(visible);
            if (visible !== target) timer = schedule(tick, options.delay || 35);
            settled();
        }
        function start() {
            if (instant) {
                if (timer !== null) unschedule(timer);
                timer = null;
                tick();
            } else if (timer === null && visible !== target) timer = schedule(tick, options.delay || 35);
        }
        return {
            append(text) { target += text; start(); },
            replace(text) {
                if (timer !== null) unschedule(timer);
                timer = null;
                target = text;
                visible = "";
                render(visible);
                start();
                settled();
            },
            finish() { return visible === target ? Promise.resolve() : new Promise(resolve => waiters.push(resolve)); },
            skip() { instant = true; start(); },
            cancel() {
                if (timer !== null) unschedule(timer);
                timer = null;
                target = visible;
                settled();
            },
            get text() { return target; },
        };
    }

    async function readSSE(response, onEvent) {
        let buffer = "", total = 0, done = false;
        function feed(text) {
            total += text.length;
            if (total > 262144) throw new Error("Stream too large");
            buffer += text;
            let separator;
            while (!done && (separator = /\r?\n\r?\n/.exec(buffer))) {
                const block = buffer.slice(0, separator.index);
                buffer = buffer.slice(separator.index + separator[0].length);
                let name = "message";
                const data = [];
                for (const line of block.split(/\r?\n/)) {
                    if (line.startsWith("event:")) name = line.slice(6).trim();
                    if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
                }
                if (!data.length) continue; // SSE comments / keepalives.
                if (!["start", "delta", "reply", "done"].includes(name)) continue;
                const payload = JSON.parse(data.join("\n"));
                if (!payload || typeof payload !== "object" || Array.isArray(payload)) throw new Error("Invalid stream event");
                onEvent(name, payload);
                done = name === "done";
            }
            if (!done && buffer.length > 16384) throw new Error("Stream event too large");
        }
        if (!response.body || typeof response.body.getReader !== "function") {
            // Buffered transports can still animate the received deltas locally.
            feed(await response.text());
        } else {
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            try {
                while (!done) {
                    const chunk = await reader.read();
                    if (chunk.done) { feed(decoder.decode()); break; }
                    feed(decoder.decode(chunk.value, { stream: true }));
                }
            } finally {
                try { await reader.cancel(); } catch { /* Disconnected already. */ }
                reader.releaseLock();
            }
        }
        if (!done) throw new Error("Stream interrupted");
    }
    return { createTypewriter, readSSE };
});
