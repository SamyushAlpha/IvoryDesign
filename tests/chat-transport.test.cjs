const test = require("node:test");
const assert = require("node:assert/strict");
const { createTypewriter, readSSE } = require("../static/chat-transport.js");

function clock() {
    let id = 0;
    const timers = new Map();
    return {
        schedule(fn) { timers.set(++id, fn); return id; },
        unschedule(key) { timers.delete(key); },
        step() {
            const entry = timers.entries().next().value;
            if (entry) { timers.delete(entry[0]); entry[1](); }
        },
        flush() { for (let n = 0; timers.size && n < 10000; n++) this.step(); assert.equal(timers.size, 0); },
        get size() { return timers.size; },
    };
}

test("local replies arrive progressively and preserve Unicode, whitespace, and literal HTML", async () => {
    const timer = clock();
    const frames = [];
    const typer = createTypewriter(text => frames.push(text), timer);
    const text = "Warm light.\nनमस्ते 🙂 <img src=x onerror=alert(1)>";
    typer.append(text);
    assert.equal(frames.length, 0);
    timer.step();
    assert.ok(frames[0].length > 0 && frames[0].length < text.length);
    const finished = typer.finish();
    timer.flush();
    await finished;
    assert.equal(frames.at(-1), text);
    assert.ok(frames.length > 2);
});

test("stream deltas append without duplication and can be replaced on error", async () => {
    const timer = clock();
    let visible;
    const typer = createTypewriter(text => { visible = text; }, timer);
    typer.append("Warm "); timer.flush();
    assert.equal(visible, "Warm ");
    typer.append("light"); timer.flush();
    assert.equal(visible, "Warm light");
    typer.replace("AI is unavailable. Contact the studio.");
    assert.equal(visible, "");
    timer.step();
    assert.equal(visible, "AI ");
    timer.flush(); await typer.finish();
    assert.equal(visible, "AI is unavailable. Contact the studio.");
});

test("reduced motion and reveal control skip animation, including future deltas", async () => {
    for (const reducedMotion of [true, false]) {
        const timer = clock();
        let visible;
        const typer = createTypewriter(text => { visible = text; }, { ...timer, reducedMotion });
        typer.append("Studio FAQ answer");
        if (!reducedMotion) typer.skip();
        assert.equal(visible, "Studio FAQ answer");
        typer.append(" continued");
        assert.equal(visible, "Studio FAQ answer continued");
        assert.equal(timer.size, 0);
        await typer.finish();
    }
});

test("cancelling stops timers and settles pending animation", async () => {
    const timer = clock();
    const frames = [];
    const typer = createTypewriter(text => frames.push(text), timer);
    typer.append("A very long answer"); timer.step();
    const finishing = typer.finish();
    typer.cancel(); await finishing;
    timer.flush();
    assert.deepEqual(frames, ["A "]);
});

function sse(name, data) { return `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`; }
function chunksResponse(text, size = 1) {
    const bytes = new TextEncoder().encode(text);
    let cancelled = false;
    return {
        body: new ReadableStream({
            start(controller) {
                for (let index = 0; index < bytes.length; index += size) controller.enqueue(bytes.slice(index, index + size));
                // Leave open: receiving 'done' must cancel without waiting for EOF.
            },
            cancel() { cancelled = true; },
        }),
        get cancelled() { return cancelled; },
    };
}

test("SSE handles split UTF-8, CRLF, multiple frames and stops on done", async () => {
    const response = chunksResponse((sse("start", {source:"ai"}) + sse("delta", {text:"नमस्ते 🙂\n"}) + sse("delta", {text:"Warm light"}) + sse("done", {source:"ai"})).replace(/\n/g, "\r\n"));
    const events = [];
    await readSSE(response, (name, data) => events.push([name, data]));
    assert.deepEqual(events.map(([name]) => name), ["start", "delta", "delta", "done"]);
    assert.equal(events[1][1].text, "नमस्ते 🙂\n");
    assert.equal(response.cancelled, true);
});

test("buffered stream can feed the typewriter when incremental transport is unavailable", async () => {
    const timer = clock();
    let visible = "";
    const typer = createTypewriter(text => { visible = text; }, timer);
    await readSSE({ text: async () => sse("reply", {reply:"A useful FAQ answer",source:"faq"}) + sse("done", {source:"faq"}) }, (name, data) => {
        if (name === "reply") typer.replace(data.reply);
    });
    assert.equal(visible, "");
    timer.step(); assert.equal(visible, "A ");
    timer.flush(); await typer.finish();
    assert.equal(visible, "A useful FAQ answer");
});

test("SSE rejects truncated, malformed, oversized and disconnected streams", async () => {
    for (const text of [sse("delta", {text:"Partial"}), "event: delta\ndata: not-json\n\n", "x".repeat(17000)]) {
        await assert.rejects(readSSE({text:async () => text}, () => {}));
    }
    await assert.rejects(readSSE({body:new ReadableStream({start(controller) {controller.error(new Error("Disconnected"));}})}, () => {}));
});

test("SSE delivers deltas before upstream completion rather than buffering full reply", async () => {
    let controller;
    const events = [];
    let received;
    const firstDelta = new Promise(resolve => { received = resolve; });
    const response = {body:new ReadableStream({start(value) {controller = value;}})};
    const reading = readSSE(response, (name, data) => { events.push(name); if (name === "delta") received(data.text); });
    controller.enqueue(new TextEncoder().encode(sse("delta", {text:"First word"})));
    assert.equal(await firstDelta, "First word");
    assert.deepEqual(events, ["delta"]);
    controller.enqueue(new TextEncoder().encode(sse("done", {source:"ai"})));
    await reading;
    assert.deepEqual(events, ["delta", "done"]);
});
