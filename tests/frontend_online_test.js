const assert = require('node:assert/strict');
const vm = require('node:vm');
const {build} = require('../tools/build_frontend');
const html = build('https://backend.example');
assert.ok(html.includes('const publicMode = true;'));
assert.ok(!html.includes('GATEWAY_TOKEN'));
assert.throws(() => build('http://public.example'));
const js = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const elements = new Map(), handlers = {}, intervals = [];
let now = 1000, fetches = 0;
const sandbox = {
    console, Date: {now: () => now},
    setInterval: f => intervals.push(f),
    fetch: async url => { assert.equal(url, 'https://backend.example/api/data'); fetches++; throw Error('backend offline'); },
    io: url => {
        assert.equal(url, 'https://backend.example');
        return {connected: true, on: (name, f) => { handlers[name] = f; }};
    },
    document: {
        getElementById: id => {
            if (!elements.has(id)) elements.set(id, {textContent: '', className: '', innerHTML: ''});
            return elements.get(id);
        },
        addEventListener() {}, querySelectorAll: () => [],
    },
};
vm.runInContext(js, vm.createContext(sandbox));
handlers.connect_error();
assert.equal(elements.get('centralStatus').textContent, 'Central desconectada');
const payload = sound => ({connected: true, transport: 'serial', stations: {QUARTO: {id: 'QUARTO', name: 'Quarto', sound, connected: true}}});
handlers.radio_data(payload(42));
assert.ok(elements.get('stations').innerHTML.includes('42 / 255'));
assert.ok(elements.get('stations').innerHTML.includes('hidden'));
handlers.radio_data(payload(51));
assert.ok(elements.get('stations').innerHTML.includes('51 / 255'));
assert.equal(elements.get('centralTransport').textContent, 'Conexão: USB Serial');
now += 9000; intervals[0]();
assert.equal(elements.get('centralStatus').textContent, 'Central desconectada');
assert.equal(elements.get('onlineStations').textContent, 0);
handlers.radio_data(payload(52));
assert.equal(elements.get('onlineStations').textContent, 1);
handlers.disconnect();
assert.equal(elements.get('onlineStations').textContent, 0);
// CDN indisponível: HTML ainda carrega e o fallback HTTP pode recuperar.
delete sandbox.io;
sandbox.fetch = async () => ({ok: true, json: async () => ({connected: false, stations: {}})});
vm.runInContext(js, vm.createContext({...sandbox}));
assert.ok(fetches > 0);
console.log('OK frontend público: build, offline, atualização 42→51, timeout, reconexão e falta de CDN');

// Uma resposta HTTP lenta deve recuperar a página mesmo após vários ticks offline.
(async () => {
    const pending = [], ticks = [];
    const context = vm.createContext({...sandbox,
        AbortSignal: {}, // Navegador sem AbortSignal.timeout também deve consultar a API.
        setInterval: f => ticks.push(f),
        fetch: () => new Promise(resolve => pending.push(resolve)),
    });
    vm.runInContext(js, context);
    now += 9000;
    ticks[0]();
    now += 2000;
    ticks[0]();
    pending[1]({ok: true, json: async () => payload(53)});
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(elements.get('onlineStations').textContent, 1);
    assert.ok(elements.get('stations').innerHTML.includes('53 / 255'));
    console.log('OK recuperação HTTP lenta e navegador sem AbortSignal.timeout');
})().catch(error => { console.error(error); process.exitCode = 1; });
