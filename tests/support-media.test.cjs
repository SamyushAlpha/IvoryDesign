const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const context = {window: {}};
vm.runInNewContext(fs.readFileSync('static/support-media.js', 'utf8'), context);
test('Enter sends once; Shift+Enter, IME and pending sends are protected', () => {
    let handler, sends = 0, blocked = false, prevented = 0;
    context.window.IvorySupportMedia.bindEnterToSend({addEventListener: (_, fn) => handler = fn},
        () => sends++, () => blocked);
    const key = options => handler({key:'Enter', preventDefault:() => prevented++, ...options});
    key({}); assert.equal(sends, 1); assert.equal(prevented, 1);
    key({shiftKey:true}); key({isComposing:true}); key({keyCode:229});
    assert.equal(sends, 1); assert.equal(prevented, 1);
    blocked = true; key({}); assert.equal(sends, 1); assert.equal(prevented, 2);
});
test('Attachment renderer creates image, audio and document controls safely', () => {
    const node = tag => ({tag, children:[], append(...children) {this.children.push(...children);}});
    context.document = {createElement:node};
    const parent = node('article');
    context.window.IvorySupportMedia.attachments(parent, [
        {url:'/chatbox/support/files/abc-123/', type:'image/png', name:'room.png', size:100},
        {url:'/chatbox/support/files/abc-456/', type:'audio/webm', name:'voice.webm', size:100},
        {url:'/chatbox/support/files/abc-789/', type:'text/plain', name:'notes.txt', size:100},
        {url:'javascript:alert(1)', type:'image/png', name:'invalid', size:100},
    ]);
    assert.equal(parent.children.length, 3);
    assert.equal(parent.children[0].children[0].tag, 'img');
    assert.equal(parent.children[1].children[0].tag, 'audio');
    assert.equal(parent.children[1].children[0].controls, true);
    assert.match(parent.children[2].children[0].textContent, /notes.txt/);
});
