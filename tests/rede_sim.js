// Executa o TypeScript real em contextos independentes; rádio e tempo simulados.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const {stripTypeScriptTypes} = require('node:module');
const path = require('node:path');
const root = path.join(__dirname, '..');
const common = fs.readFileSync(path.join(root, 'microbit/protocolo.ts'), 'utf8');
const compiled = new Map();
function compile(s) {
    if (!compiled.has(s)) compiled.set(s, stripTypeScriptTypes(s, {mode: 'transform'}));
    return compiled.get(s);
}
class Bytes extends Uint8Array {
    getNumber(_, offset) { return new DataView(this.buffer, this.byteOffset).getUint32(offset, true); }
    setNumber(_, offset, n) { new DataView(this.buffer, this.byteOffset).setUint32(offset, n, true); }
    slice(start, end) { return new Bytes(super.slice(start, end)); }
    toHex() { return Buffer.from(this).toString('hex'); }
}
class Network {
    constructor(sources = {}) { this.sources = sources; this.now = 0; this.nodes = []; this.edges = []; this.events = []; this.tx = []; this.drop = () => false; this.seed = 1234567; }
    add(role, id = 'QUARTO', name = 'Quarto') {
        const n = {role, id, name, index: this.nodes.length, lines: [], loops: [], input: '', receiver: null, icon: null};
        this.nodes.push(n); this.boot(n); return n;
    }
    boot(n) {
        n.loops = []; n.receiver = null; n.input = ''; n.bootTime = this.now;
        let current = null;
        const net = this;
        const context = {
            Buffer: Bytes, NumberFormat: {UInt32LE: 0}, BaudRate: {BaudRate115200: 115200}, IconNames: {Yes: 'YES', No: 'NO'},
            randint(a, b) { net.seed = (Math.imul(net.seed, 1664525) + 1013904223) >>> 0; return a + net.seed % (b - a + 1); },
            pins: {createBuffer: size => new Bytes(size)}, input: {soundLevel: () => 250},
            control: {millis: () => (net.now - n.bootTime + (net.timeOffset || 0)) >>> 0},
            basic: {
                showIcon: icon => { n.icon = icon; },
                forever: f => n.loops.push({f, due: net.now}),
                pause: ms => { if (current) current.due += ms; },
            },
            radio: {
                setGroup: group => { n.group = group; }, setTransmitPower: power => { n.power = power; },
                onReceivedBuffer: f => { n.receiver = f; },
                sendBuffer(p) {
                    assert.ok(p.length <= 19);
                    net.tx.push({at: net.now, node: n.index, bytes: [...p]});
                    for (const [a, b] of net.edges) {
                        const other = a === n.index ? b : b === n.index ? a : -1;
                        if (other >= 0 && !net.drop(n, net.nodes[other], p)) {
                            net.events.push({at: net.now + 1, to: other, p: p.slice(0)});
                        }
                    }
                },
            },
            serial: {
                setBaudRate: b => { n.baud = b; },
                writeLine: s => n.lines.push(String(s)),
                readString: () => { const s = n.input; n.input = ''; return s; },
            },
        };
        n.context = vm.createContext(context);
        const role = (this.sources[n.role] || fs.readFileSync(path.join(root, 'microbit', n.role + '.ts'), 'utf8'))
            .replace('let ID_ESTACAO = "QUARTO"', 'let ID_ESTACAO = ' + JSON.stringify(n.id))
            .replace('let NOME_ESTACAO = "Quarto"', 'let NOME_ESTACAO = ' + JSON.stringify(n.name));
        vm.runInContext(compile((this.sources.protocolo || common) + '\n' + role), n.context);
        n.tick = () => {
            for (const loop of n.loops) if (loop.due <= net.now) {
                current = loop; loop.due = net.now; loop.f();
                loop.due += net.sources.foreverDelay || 0;
                loop.due = Math.max(loop.due, net.now + 1); current = null;
            }
        };
    }
    link(a, b) { this.edges.push([a.index, b.index]); }
    run(ms) {
        const end = this.now + ms;
        while (this.now < end) {
            const ready = this.events.filter(e => e.at <= this.now);
            this.events = this.events.filter(e => e.at > this.now);
            for (const e of ready) this.nodes[e.to].receiver?.(e.p);
            for (const n of this.nodes) n.tick();
            this.now++;
        }
    }
    packet(n, type, token = 42, payload = [], attempt = 0) {
        return n.context.Rede.pacote(type, n.id, token, new Bytes(payload), attempt);
    }
}
function chain(count) {
    const net = new Network(), station = net.add('estacao');
    let last = station; const relays = [];
    for (let i = 0; i < count; i++) { const r = net.add('ponte'); relays.push(r); net.link(last, r); last = r; }
    const central = net.add('central'); net.link(last, central);
    return {net, station, central, relays};
}
let passed = 0;
function test(name, f) { f(); passed++; if (!process.argv.includes('--fixture')) console.log('OK ' + name); }
for (const count of [0, 1, 8, 12]) test('ida, volta, ACK e heartbeat com ' + count + ' Pontes', () => {
    const {net, station, central} = chain(count);
    net.run(5000);
    assert.equal(station.icon, 'YES');
    assert.ok(central.lines.includes('SOM|QUARTO|250'));
    assert.ok(central.lines.includes('HEARTBEAT|QUARTO'));
    central.input = 'PING|QUARTO|123\n'; net.run(3000);
    assert.ok(central.lines.includes('CMD|QUARTO|123|OK'));
    assert.equal(station.group, 42); assert.equal(station.power, 7);
});
test('13 Pontes excedem o limite e retornam timeout', () => {
    const {net, station, central} = chain(13);
    central.input = 'PING|QUARTO|123\n'; net.run(9000);
    assert.equal(station.icon, 'NO');
    assert.ok(central.lines.includes('CMD|QUARTO|123|TIMEOUT'));
    assert.ok(!central.lines.some(s => s.startsWith('SOM|')));
});
test('duas estações, nomes longos e isolamento dos ACKs', () => {
    const {net, station, central, relays} = chain(8);
    const other = net.add('estacao', 'COZINHA', 'Cozinha'); net.link(other, relays[0]);
    net.run(5000);
    assert.equal(other.icon, 'YES'); assert.equal(station.icon, 'YES');
    assert.ok(central.lines.includes('SOM|COZINHA|250'));
    assert.ok(central.lines.includes('SOM|QUARTO|250'));
});
test('duplicados e ciclo entre Pontes terminam', () => {
    const net = new Network(), a = net.add('ponte'), b = net.add('ponte'), c = net.add('ponte');
    net.link(a,b); net.link(b,c); net.link(c,a);
    const p = net.packet(a, 1);
    for (let i = 0; i < 20; i++) a.receiver(p.slice(0));
    net.run(1000);
    assert.equal(net.tx.length, 3);
    net.run(2000); assert.equal(net.tx.length, 3);
});
test('ACK perdido: mesma operação com nova tentativa atravessa caches', () => {
    const {net, station, central} = chain(8);
    let dropped = 0;
    net.drop = (from, to, p) => { if (from === central && (p[0] & 15) === 6 && (p[1] >> 4) === 0) { dropped++; return true; } return false; };
    net.run(6500);
    assert.ok(dropped > 0); assert.equal(station.icon, 'YES');
    assert.ok(net.tx.some(x => (x.bytes[0] & 15) === 1 && (x.bytes[1] >> 4) === 1));
});
test('resposta PING perdida é recuperada na segunda tentativa', () => {
    const {net, station, central} = chain(8);
    net.drop = (from, to, p) => from === station && (p[0] & 15) === 8 && (p[1] >> 4) === 0;
    central.input = 'PING|QUARTO|400\n'; net.run(6500);
    assert.equal(central.lines.filter(s => s === 'CMD|QUARTO|400|OK').length, 1);
});
test('reinício de Ponte e Estação recupera heartbeat e usa novo token', () => {
    const {net, station, central, relays} = chain(8);
    net.run(4000);
    const old = net.tx.filter(x => x.node === station.index && (x.bytes[0] & 15) === 1).map(x => x.bytes.slice(2, 6).join(','));
    net.boot(relays[4]); net.boot(station); net.run(4000);
    assert.equal(station.icon, 'YES');
    const newest = net.tx.filter(x => x.node === station.index && (x.bytes[0] & 15) === 1).at(-1).bytes.slice(2, 6).join(',');
    assert.ok(!old.includes(newest)); assert.ok(central.lines.includes('HEARTBEAT|QUARTO'));
});
test('pacotes inválidos, incompletos e tipos inesperados são descartados', () => {
    const {net, station, central, relays} = chain(1);
    const p = net.packet(station, 1);
    const invalid = [new Bytes(0), p.slice(0, 8), new Bytes(20)];
    for (const [offset, value] of [[0, 0x21], [0, 0x1f], [1, 15], [1, 0x3c], [6, 9], [7, 33]]) {
        const q = p.slice(0); q[offset] = value; invalid.push(q);
    }
    for (const q of invalid) for (const n of net.nodes) n.receiver(q.slice(0));
    assert.equal(central.lines.length, 1); assert.equal(station.icon, 'NO');
    assert.equal(relays[0].context.Rede.aceitar(net.packet(station, 2)), false);
});
test('ACK antigo não confirma novo heartbeat; ACK refletido não vai ao PC', () => {
    const {net, station, central} = chain(0);
    net.edges = []; net.run(1000);
    station.receiver(net.packet(station, 6, 999));
    central.receiver(net.packet(station, 6, 999));
    assert.equal(station.icon, 'NO'); assert.ok(!central.lines.some(s => s.startsWith('ACK|')));
});
test('cache expira, fila é limitada e TTL continua protegendo', () => {
    const net = new Network(), r = net.add('ponte'); const api = r.context.Rede;
    const p = net.packet(r, 1);
    assert.equal(api.aceitar(p), true); assert.equal(api.aceitar(p), false);
    net.run(12001); assert.equal(api.aceitar(p), true);
    for (let i = 0; i < 24; i++) assert.equal(api.enviar(net.packet(r, 1, i)), true);
    assert.equal(api.enviar(p), false);
    for (let i = 0; i < 300; i++) api.aceitar(net.packet(r, 1, 1000+i));
    const expired = p.slice(0); expired[1] = 0; api.repetir(expired);
    net.run(2000); assert.equal(net.tx.length, 24);
});
test('overflow uint32 é definido e nomes máximos cabem em 19 bytes', () => {
    const context = vm.createContext({randint: () => 65535});
    vm.runInContext(compile(common), context);
    assert.equal(context.Rede.novoToken(), 0); assert.equal(context.Rede.novoToken(), 1);
    const net = new Network(), s = net.add('estacao', 'ESTACAO8', 'á'.repeat(24)), c = net.add('central'); net.link(s,c);
    net.run(4000);
    assert.equal(c.lines.filter(s => s.startsWith('NPART|')).length, 16);
});
test('serial parcial, comando inválido, ocupado e assinatura', () => {
    const {net, central} = chain(0);
    central.input = 'PING|QUARTO|'; net.run(100);
    assert.ok(!net.tx.some(t => (t.bytes[0] & 15) === 7));
    central.input = '55\nPING|QUARTO|56\nHELLO\n' + 'x'.repeat(60) + '\nPING|QUARTO|NaN\n';
    net.run(3000);
    assert.ok(central.lines.includes('CMD|QUARTO|55|OK'));
    assert.ok(central.lines.includes('CMD|QUARTO|56|BUSY'));
    assert.ok(central.lines.includes('CENTRAL_ONLINE|1'));
});

test('temporizadores continuam após overflow de millis', () => {
    const net = new Network(); net.timeOffset = 4294966000;
    const s = net.add('estacao'), r = net.add('ponte'), c = net.add('central');
    net.link(s,r); net.link(r,c); net.run(5000);
    assert.equal(s.icon, 'YES');
    c.input = 'PING|QUARTO|88\n'; net.run(3000);
    assert.ok(c.lines.includes('CMD|QUARTO|88|OK'));
});

if (process.argv.includes('--fixture')) {
    const {net, central} = chain(8); net.run(5000);
    central.input = 'PING|QUARTO|314\n'; net.run(3000);
    console.log(JSON.stringify(central.lines));
} else console.log(passed + ' cenários aprovados (sem modelo físico de RF).');

// Reuso do mesmo simulador nos benchmarks; nenhum cenário acima é substituído.
module.exports = {Network, Bytes};
