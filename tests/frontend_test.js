const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync(require('node:path').join(__dirname, '../templates/index.html'), 'utf8');
const js = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const elements = new Map(), handlers = {}, listeners = {};
const socket = {
    on: (name, f) => { handlers[name] = f; },
    timeout: () => socket,
    emit: (name, data, callback) => {
        assert.equal(name, 'radio_ping'); assert.equal(data.id, 'QUARTO');
        callback(null, {ok: true, status: 'OK'});
    },
};
const context = vm.createContext({
    io: () => socket, console,
    fetch: async () => ({ok: false}),
    document: {
        getElementById: id => {
            if (!elements.has(id)) elements.set(id, {textContent: '', innerHTML: '', className: ''});
            return elements.get(id);
        },
        addEventListener: (name, f) => { listeners[name] = f; },
        querySelectorAll: () => [],
    },
});
vm.runInContext(js, context);
handlers.radio_data({connected: true, stations: {
    QUARTO: {id: 'QUARTO', name: '<Quarto>', sound: 250, connected: true, interval: 0.5},
    COZINHA: {id: 'COZINHA', sound: 17, connected: false},
}});
assert.equal(elements.get('onlineStations').textContent, 1);
assert.equal(elements.get('offlineStations').textContent, 1);
assert.equal(elements.get('centralStatus').textContent, 'Central conectada');
assert.ok(elements.get('stations').innerHTML.includes('250 / 255'));
assert.ok(elements.get('stations').innerHTML.includes('&lt;Quarto&gt;'));
assert.ok(!elements.get('stations').innerHTML.includes('<Quarto>'));
listeners.click({target: {closest: () => ({dataset: {ping: 'QUARTO'}})}});
assert.equal(vm.runInContext('resultadosPing.get("QUARTO")', context), 'Resposta confirmada');
handlers.disconnect();
assert.equal(elements.get('centralStatus').textContent, 'Central desconectada');
assert.equal(elements.get('lastUpdate').textContent, 'Sem conexão com o servidor');
console.log('OK frontend: eventos, cards, escala 255, escape HTML, PING e desconexão');
