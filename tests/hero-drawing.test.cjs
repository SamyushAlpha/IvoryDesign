// Run with Node.js: node tests/hero-drawing.test.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
function element() {
    return { attrs: {}, style: {setProperty() {}}, setAttribute(k, v) {this.attrs[k] = v;}, textContent: '', nodes: [], appendChild(node) {this.nodes = this.nodes.filter(n => n !== node); this.nodes.push(node);} };
}
const scenes = [element(), element(), element()];
const pencils = [element(), element()];
const strokes = pencils.map((pencil, index) => Object.assign(element(), {
    getTotalLength: () => 100,
    getPointAtLength: x => ({x, y: 0}),
    closest: selector => selector === '[data-interior-scene]' && index === 0 ? scenes[0] : selector === '.signature-sketch' && index === 1 ? {} : null,
    ownerSVGElement: {querySelector: () => pencil},
}));
const secondSceneStroke = Object.assign(element(), {getTotalLength: () => 140, getPointAtLength: x => ({x,y:0}), closest: selector => selector === '[data-interior-scene]' ? scenes[1] : null, ownerSVGElement: {querySelector: () => pencils[0]}});
const thirdSceneStroke = Object.assign(element(), {...secondSceneStroke, attrs: {}, style: {setProperty() {}}, closest: selector => selector === '[data-interior-scene]' ? scenes[2] : null});
const painters = ['left', 'bottom', 'right'].map((direction, index) => {
    const children = Object.fromEntries(['figure', 'shin-left', 'shin-right', 'shadow', 'arm-left', 'bucket', 'head', 'head-front', 'head-profile', 'head-back', 'leg-left', 'leg-right', 'arm-right', 'roller'].map(name => ['.painter-' + name, element()]));
    children['.uniform-brand'] = element();
    return Object.assign(element(), {
        dataset: {entry: direction, targetX: String([187, 367, 650][index]), targetY: String([484, 558, 480][index])},
        children, querySelector: name => children[name],
    });
});
const vehicles = ['left', 'bottom', 'right'].map((entry, index) => {
    const children = Object.fromEntries(['.vehicle-body', '.vehicle-track', '.truck-front', '.truck-rear', '.cab-driver', '.cab-driver-front', '.cab-driver-back', '.vehicle-door', '.vehicle-brand'].map(name => [name, element()]));
    children['.vehicle-door'].dataset = {hingeX: '-35', hingeY: '-108'};
    return Object.assign(element(), {
        children,
        dataset: {entry, kind: ['loader', 'truck', 'excavator'][index]},
        querySelector: name => children[name],
        querySelectorAll: () => [element(), element()],
    });
});
const reveals = Array.from({length: 12}, element);
const finishing = element();
const sparkles = element();
const drawing = Object.assign(element(), {
    classList: {add() {}, remove() {}},
    querySelectorAll: selector => ({'[data-draw]': [...strokes, secondSceneStroke, thirdSceneStroke], '[data-interior-scene]': scenes, '.house-finishing': [finishing], '.drawing-pencil': pencils, '.paint-reveal': reveals, '.scene-painter': painters, '.scene-vehicle': vehicles}[selector]),
    querySelector: selector => ({'.signature-sketch': {getBoundingClientRect: () => ({left: 490, top: 720, right: 800, bottom: 810})}, '.house-sketch': {getScreenCTM: () => ({inverse: () => ({})})}, '.house-finishing': finishing, '.paint-sparkles': sparkles}[selector]),
    getBoundingClientRect: () => ({left: 0, right: 1280, top: 0, bottom: 900}),
});
let frame;
let preferenceChange;
const motion = {matches: false, addEventListener: (event, callback) => {preferenceChange = callback;}};
const context = {
    document: {createElementNS: () => element(), querySelector: () => drawing, hidden: false, addEventListener() {}},
    matchMedia: () => motion,
    requestAnimationFrame: callback => {frame = callback; return 1;}, cancelAnimationFrame() {},
    ResizeObserver: class {observe() {}}, IntersectionObserver: class {observe() {}},
    DOMPoint: class {constructor(x, y) {this.x = x; this.y = y;} matrixTransform() {return this;}},
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(__dirname, '../static/hero-drawing.js'), 'utf8'), context);
const at = time => frame(time);
const x = value => Number(value.match(/translate\(([-\d.]+)/)[1]);
const y = value => Number(value.match(/translate\([-\d.]+ ([-\d.]+)/)[1]);
const vehicleBounds = [
    {left: 30, right: 198, top: 508, bottom: 605},
    {left: 402, right: 478, top: 581, bottom: 663},
    {left: 617, right: 795, top: 489, bottom: 589},
];
function staysOutsideVehicles() {
    painters.forEach(painter => {
        const px = x(painter.attrs.transform), py = y(painter.attrs.transform);
        vehicleBounds.forEach(box => assert(
            px <= box.left || px >= box.right || py <= box.top || py >= box.bottom,
            `Walking route intersects a parked vehicle at ${px}, ${py}`,
        ));
    });
}
at(0);
assert(painters.every(p => p.attrs.opacity === '0'));
assert(vehicles.every(v => v.attrs.opacity === '0'));
assert(reveals.every(r => r.attrs.height === '0'));
at(24000);
assert(vehicles.every(v => v.attrs.opacity === '0'), 'Vehicles wait for the signature');
at(32000);
assert(vehicles.every(v => v.attrs.opacity === '0'), 'Medium drawing pace finishes before vehicles arrive');
assert(strokes.some(p => Number(p.style.strokeDashoffset) > 0));
at(45000);
assert(strokes.some(p => Number(p.style.strokeDashoffset) > 0), 'Drawing continues at the slower pace');
assert(vehicles.every(v => v.attrs.opacity === '0'));
at(56000);
assert(strokes.every(p => Number(p.style.strokeDashoffset) === 0));
assert(painters.every(p => p.attrs['data-activity'] === 'driving'));
assert(vehicles.every(v => v.attrs['data-activity'] === 'driving'));
assert(painters.every(p => p.children['.painter-bucket'].attrs.opacity === '0'));
assert.equal(new Set(vehicles.map(v => v.attrs.transform)).size, 3);
assert.equal(painters[1].children['.painter-head-back'].attrs.opacity, '1');
assert(painters.every(p => p.attrs.opacity === '0'), 'Standing figures hidden while riding');
assert(vehicles.every(v => v.children['.cab-driver'].attrs.opacity === '1'), 'Drivers seated in cabs');
assert(vehicles.every(v => v.children['.vehicle-door'].attrs['data-open'] === '0'));
assert.equal(vehicles[2].children['.vehicle-brand'].attrs.transform, 'scale(-1 1)');
at(62000);
assert(painters.every(p => p.attrs.opacity === '0'), 'Door opens before driver steps out');
assert(vehicles.every(v => Number(v.children['.vehicle-door'].attrs['data-open']) > .9));
assert(painters.every(p => p.attrs['data-activity'] === 'dismounting'));
assert(vehicles.every(v => v.attrs['data-activity'] === 'parked'));
const parkingTransforms = vehicles.map(v => v.attrs.transform);
const parkedHeadings = vehicles.map(v => v.children['.vehicle-body'].attrs.transform);
const parkedTracks = vehicles.map(v => Number(v.children['.vehicle-track'].attrs['stroke-dashoffset']));
const staysParked = () => assert.deepEqual(vehicles.map(v => v.attrs.transform), parkingTransforms);
for (let time = 64101; time < 68900; time += 60) {
    at(time);
    assert(painters.every(p => p.attrs['data-activity'] === 'walking'));
    staysOutsideVehicles();
    staysParked();
}
assert(vehicles.every(v => v.children['.cab-driver'].attrs.opacity === '0'), 'Parked cabs empty');
assert(vehicles.every(v => v.children['.vehicle-door'].attrs['data-open'] === '0'));
at(69500);
assert(painters.every(p => p.attrs['data-activity'] === 'waving'));
assert(painters.every(p => p.children['.painter-head-front'].attrs.opacity === '1'));
assert(painters.every(p => p.children['.painter-roller'].attrs.opacity === '0'));
staysParked();
at(74000);
assert(painters.every(p => p.attrs['data-activity'] === 'painting'));
assert(reveals.every(r => Number(r.attrs.height) > 0 && Number(r.attrs.height) < 640));
assert(painters.every(p => p.children['.painter-roller'].attrs.opacity === '1'));
assert.equal(painters[1].children['.painter-head-back'].attrs.opacity, '1');
staysParked();
at(79000);
assert(painters.every(p => p.attrs['data-activity'] === 'waving'));
assert(painters.every(p => p.children['.painter-head-front'].attrs.opacity === '1'));
assert(reveals.every(r => Number(r.attrs.height) === 640));
staysParked();
for (let time = 80501; time < 85300; time += 60) {
    at(time);
    assert(painters.every(p => p.attrs['data-activity'] === 'walking'));
    staysOutsideVehicles();
    staysParked();
}
at(86600);
assert(painters.every(p => p.attrs['data-activity'] === 'boarding'));
staysParked();
assert(vehicles.every(v => v.children['.vehicle-door'].attrs['data-open'] === '1'), 'Board through open doors');
at(88400);
assert(painters.every(p => p.attrs.opacity === '0'));
assert(vehicles.every(v => v.children['.cab-driver'].attrs.opacity === '1'));
assert(vehicles.every(v => v.children['.vehicle-door'].attrs['data-open'] === '0'), 'Close doors before departure');
assert(painters.every(p => p.attrs['data-activity'] === 'reversing'));
for (let time = 88500; time < 94400; time += 100) {
    at(time);
    assert(vehicles.every(v => v.attrs['data-activity'] === 'reversing'));
    assert.deepEqual(vehicles.map(v => v.children['.vehicle-body'].attrs.transform), parkedHeadings, 'Vehicles keep their heading while reversing');
    assert.equal(y(vehicles[0].attrs.transform), y(parkingTransforms[0]));
    assert.equal(y(vehicles[2].attrs.transform), y(parkingTransforms[2]));
    assert.equal(x(vehicles[1].attrs.transform), x(parkingTransforms[1]));
    assert.equal(vehicles[1].children['.truck-rear'].attrs.opacity, '1');
    assert.equal(vehicles[1].children['.truck-front'].attrs.opacity, '0');
    assert(vehicles.every((v, i) => Number(v.children['.vehicle-track'].attrs['stroke-dashoffset']) > parkedTracks[i]), 'Tracks run backward');
}
assert(x(vehicles[0].attrs.transform) < x(parkingTransforms[0]), 'Loader reverses left');
assert(y(vehicles[1].attrs.transform) > y(parkingTransforms[1]), 'Truck reverses downward');
assert(x(vehicles[2].attrs.transform) > x(parkingTransforms[2]), 'Excavator reverses right');
at(96000);
assert(painters.every(p => p.attrs.opacity === '0'));
assert(vehicles.every(v => v.attrs.opacity === '0'));
at(98899);
assert.equal(drawing.attrs['data-active-scene'], '0', 'First scene stays until its full sequence ends');
at(99500);
assert.equal(drawing.attrs['data-active-scene'], '1');
assert.equal(scenes[0].style.display, 'none');
assert.equal(scenes[1].style.display, '');
assert(reveals.every(r => r.attrs.height === '0'));
for (const [offset, activity] of [[56000,'driving'],[62000,'dismounting'],[69500,'waving'],[74000,'painting'],[79000,'waving'],[86600,'boarding'],[90000,'reversing']]) {
    at(98900 + offset);
    assert.equal(drawing.attrs['data-active-scene'], '1');
    assert(painters.every(p => p.attrs['data-activity'] === activity), `Second scene repeats ${activity}`);
}
at(98900 + 96000);
assert(vehicles.every(v => v.attrs.opacity === '0'));
at(197800);
assert.equal(drawing.attrs['data-active-scene'], '2', 'Third interior starts after the second crew leaves');
assert.equal(scenes[1].style.display, 'none');
assert.equal(scenes[2].style.display, '');
for (const [offset, activity] of [[56000,'driving'],[62000,'dismounting'],[69500,'waving'],[74000,'painting'],[79000,'waving'],[86600,'boarding'],[90000,'reversing']]) {
    at(197800 + offset);
    assert.equal(drawing.attrs['data-active-scene'], '2');
    assert(painters.every(p => p.attrs['data-activity'] === activity), `Third scene repeats ${activity}`);
}
at(197800 + 96000);
assert(vehicles.every(v => v.attrs.opacity === '0'));
at(296700);
assert.equal(drawing.attrs['data-active-scene'], '0', 'All three interiors loop back to the first');
motion.matches = true;
preferenceChange();
assert(reveals.every(r => Number(r.attrs.height) === 640));
assert(painters.every(p => p.attrs.opacity === '0'));
assert(vehicles.every(v => v.attrs.opacity === '0'));
console.log('Passed: matched vehicles → park → dismount → walk → wave → paint → wave → return → board → reverse home; reduced-motion scene.');
