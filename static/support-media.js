/* Private support attachments and voice notes; no transcription or external API. */
(() => {
    "use strict";
    function attachments(parent, files) {
        for (const file of files || []) {
            if (!/^\/chatbox\/support\/files\/[a-f0-9-]+\/$/.test(file.url)) continue;
            const block = document.createElement("div"); block.className = "support-file";
            if (file.type.startsWith("image/")) {
                const img = document.createElement("img"); img.src = file.url; img.alt = file.name; img.loading = "lazy"; block.append(img);
            } else if (file.type.startsWith("audio/")) {
                const audio = document.createElement("audio"); audio.src = file.url; audio.controls = true; audio.preload = "metadata"; block.append(audio);
            }
            const link = document.createElement("a"); link.href = file.url + "?download=1";
            link.textContent = `Download ${file.name} (${Math.ceil(file.size / 1024)} KB)`; block.append(link); parent.append(block);
        }
    }

    function composer(form, status) {
        const controls = document.createElement("div"); controls.className = "support-media-controls";
        const label = document.createElement("button"); label.type = "button";
        const picker = document.createElement("input"); picker.type = "file";
        picker.accept = ".png,.jpg,.jpeg,.pdf,.txt,.webm,.ogg,.mp3,.wav,.m4a"; picker.hidden = true;
        const icons = {attach: 'M21 11.5 12.5 20a6 6 0 0 1-8.5-8.5L13 2.5a4 4 0 0 1 5.7 5.7l-9 9a2 2 0 0 1-2.8-2.8L15 6.3', mic: 'M9 5a3 3 0 0 1 6 0v7a3 3 0 0 1-6 0ZM5 10v2a7 7 0 0 0 14 0v-2M12 19v3M8 22h8', stop: 'M6 6h12v12H6Z', cancel: 'm6 6 12 12M6 18 18 6'};
        function icon(button, name, title) {
            button.replaceChildren(); button.className = "support-media-icon";
            button.setAttribute("aria-label", title); button.title = title;
            const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
            svg.setAttribute("viewBox", "0 0 24 24"); svg.setAttribute("aria-hidden", "true");
            const path = document.createElementNS(svg.namespaceURI, "path"); path.setAttribute("d", icons[name]); svg.append(path); button.append(svg);
        }
        icon(label, "attach", "Attach a file"); label.addEventListener("click", () => picker.click());
        const record = document.createElement("button"); record.type = "button"; icon(record, "mic", "Record a voice note");
        const cancel = document.createElement("button"); cancel.type = "button"; icon(cancel, "cancel", "Remove attachment or cancel recording"); cancel.hidden = true;
        const preview = document.createElement("div"); preview.className = "support-media-preview";
        preview.hidden = true; preview.setAttribute("aria-live", "polite");
        controls.append(picker, label, record, cancel);
        let row = form.querySelector(".ivory-chat__compose");
        if (!row) {
            row = document.createElement("div"); row.className = "support-compose-row";
            const input = form.querySelector("textarea"), submit = form.querySelector('button[type="submit"]');
            input.before(row); row.append(input, submit);
        }
        row.prepend(controls); row.before(preview);
        let file = null, recorder = null, stream = null, timer = null, objectUrl = null, recording = false, discarded = false, busy = false;
        function release() { if (objectUrl) URL.revokeObjectURL(objectUrl); objectUrl = null; }
        function clear() { file = null; picker.value = ""; release(); preview.replaceChildren(); preview.hidden = true; cancel.hidden = true; }
        function select(value) {
            clear();
            if (!value || !value.size || value.size > 5 * 1024 * 1024) { status.textContent = "Choose a non-empty file up to 5 MB."; return; }
            file = value; cancel.hidden = false; preview.hidden = false;
            const name = document.createElement("p"); name.textContent = `${file.name} · ${Math.ceil(file.size / 1024)} KB`; preview.append(name);
            if (file.type.startsWith("audio/")) {
                objectUrl = URL.createObjectURL(file); const audio = document.createElement("audio"); audio.controls = true; audio.src = objectUrl; preview.append(audio);
            }
            status.textContent = "Attachment ready. Press Send to share it.";
        }
        function stop() { if (recorder?.state === "recording") recorder.stop(); clearTimeout(timer); stream?.getTracks().forEach(t => t.stop()); }
        picker.addEventListener("change", () => select(picker.files[0]));
        cancel.addEventListener("click", () => { discarded = true; stop(); clear(); status.textContent = "Attachment removed."; });
        const supported = window.isSecureContext && navigator.mediaDevices?.getUserMedia && window.MediaRecorder;
        if (!supported) { record.disabled = true; record.title = "Recording needs HTTPS/localhost and a supported browser. Attach an audio file instead."; }
        record.addEventListener("click", async () => {
            if (busy) return;
            if (recording) { stop(); return; }
            record.disabled = true; recording = true; label.disabled = true;
            try {
                stream = await navigator.mediaDevices.getUserMedia({audio:true});
                const mime = ["audio/webm;codecs=opus", "audio/mp4", "audio/ogg;codecs=opus"].find(t => MediaRecorder.isTypeSupported(t));
                if (!mime) throw new Error("unsupported");
                const chunks = []; discarded = false; recording = true; clear();
                recorder = new MediaRecorder(stream, {mimeType:mime});
                recorder.addEventListener("error", () => {
                    discarded = true; recording = false; stop(); clear();
                    icon(record, "mic", "Record a voice note"); label.disabled = busy;
                    status.textContent = "Recording failed. Please try again or attach an audio file.";
                });
                recorder.addEventListener("dataavailable", e => { if (e.data.size) chunks.push(e.data); });
                recorder.addEventListener("stop", () => {
                    recording = false; icon(record, "mic", "Record a voice note"); picker.disabled = busy; label.disabled = busy; stop();
                    if (!discarded) {
                        const type = mime.split(";")[0], ext = type === "audio/mp4" ? "m4a" : type.split("/")[1];
                        select(new File(chunks, `voice-note.${ext}`, {type}));
                    }
                });
                recorder.start(1000); picker.disabled = true; cancel.hidden = false; icon(record, "stop", "Stop recording and preview"); record.classList.add("is-recording");
                status.textContent = "Recording… stop to preview (maximum 2 minutes).";
                timer = setTimeout(stop, 120000);
            } catch { recording = false; stop(); status.textContent = "Microphone unavailable or permission denied. You can attach an audio file instead."; }
            finally { record.disabled = busy || !supported; label.disabled = busy || recording; }
        });
        window.addEventListener("pagehide", () => { discarded = true; stop(); release(); });
        return { get file() { return file; }, get recording() { return recording; }, clear,
            setBusy(value) { busy=value; picker.disabled=value || recording; label.disabled=value || recording; record.disabled=value || !supported; cancel.disabled=value; } };
    }

    function send(url, message, id, file, csrf, status) {
        return new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest(); xhr.open("POST", url); xhr.timeout = 45000;
            xhr.setRequestHeader("X-CSRFToken", csrf);
            xhr.upload.onprogress = e => { if (e.lengthComputable) status.textContent = `Sending… ${Math.round(e.loaded/e.total*100)}%`; };
            xhr.onload = () => {
                let data; try { data=JSON.parse(xhr.responseText); } catch { data={}; }
                if (xhr.status >= 200 && xhr.status < 300) resolve(data);
                else { const error=new Error(data.error || "Unable to send. Please refresh and try again."); error.status=xhr.status; reject(error); }
            };
            xhr.onerror = xhr.ontimeout = () => reject(new Error("Connection interrupted. Check history before retrying."));
            if (file) { const body=new FormData(); body.append("message",message); body.append("client_message_id",id); body.append("file",file); xhr.send(body); }
            else { xhr.setRequestHeader("Content-Type","application/json"); xhr.send(JSON.stringify({message,client_message_id:id})); }
        });
    }
    function bindEnterToSend(input, submit, blocked) {
        input.addEventListener("keydown", event => {
            if (event.key !== "Enter" || event.shiftKey || event.isComposing || event.keyCode === 229) return;
            event.preventDefault();
            if (!blocked()) submit();
        });
    }
    window.IvorySupportMedia = {attachments, composer, send, bindEnterToSend};
})();
