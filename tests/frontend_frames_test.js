const assert = require('node:assert/strict');
const vm = require('node:vm');
const {build} = require('../tools/build_frontend');
const html = build('https://backend.example');
const handlers = {}, elements = new Map(), frames = [];
let renders = 0;
const context = vm.createContext({console,
    io: () => ({on: (name, cb) => handlers[name] = cb, connected:true}),
    setInterval() {}, fetch: async () => ({ok:false}),
    requestAnimationFrame: cb => frames.push(cb),
    document: {addEventListener() {}, querySelectorAll: () => [], getElementById(id) {
        if (!elements.has(id)) {
            const element = {textContent:'', className:'', html:''};
            Object.defineProperty(element, 'innerHTML', {
                get() {return this.html}, set(value) {this.html=value; if (id==='stations') renders++;}
            });
            elements.set(id, element);
        }
        return elements.get(id);
    }}
});
vm.runInContext(html.match(/<script>([\s\S]*?)<\/script>/)[1], context);
const payload = value => ({connected:true, stations:{QUARTO:{id:'QUARTO', name:'Quarto', connected:true, sound:value}}});
for (let i=0;i<200;i++) handlers.radio_data(payload(i));
assert.equal(frames.length, 1);
assert.equal(renders, 0);
frames.shift()();
assert.equal(renders, 1);
assert.ok(elements.get('stations').innerHTML.includes('199 / 255'));
handlers.radio_data(payload(200));
handlers.disconnect();
frames.shift()();
assert.equal(elements.get('centralStatus').textContent, 'Central desconectada');
handlers.radio_data(payload(201));
frames.shift()();
assert.ok(elements.get('stations').innerHTML.includes('201 / 255'));
assert.ok(!html.includes('width 0.25s'));
console.log('OK frames: 200 eventos -> 1 render mais recente; offline invalida frame; reconexao');
