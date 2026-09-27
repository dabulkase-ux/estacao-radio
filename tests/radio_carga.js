// Tempo virtual; não modela interferência, airtime, GC nem escalonador CODAL.
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const {execFileSync} = require('node:child_process');
const {Network} = require('./rede_sim');
const baseline = execFileSync('git', ['show', '536afe1:microbit/estacao.ts'], {encoding:'utf8'});
const protocolo = fs.readFileSync(path.join(__dirname, '../microbit/protocolo.ts'), 'utf8')
    .replace('export const H = 1', 'export function filaDebug(): number { return fila.length }\n    export const H = 1');
function cenario(relays, count, intervalo, constante = false, perda = false, antigo = false, periodo = 1000, duplicatas = false) {
    // core/codal.cpp do alvo oficial acrescenta fiber_sleep(20) em basic.forever.
    const net = new Network({protocolo, foreverDelay:20, ...(antigo ? {estacao:baseline} : {})}), stations = [];
    const amplitude = periodo === 1000 ? 20 : 1;
    for (let i = 0; i < count; i++) stations.push(net.add('estacao', 'EST' + i));
    let first = null, last = null;
    for (let i = 0; i < relays; i++) {
        const r = net.add('ponte');
        if (last) net.link(last, r); else first = r;
        last = r;
    }
    const c = net.add('central');
    if (last) net.link(last, c);
    if (duplicatas && first) net.link(first, c); // Ciclo/caminho redundante.
    for (const s of stations) {
        net.link(s, first || c);
        if (duplicatas) net.link(s, first || c); // Entrega duas cópias por aresta.
        vm.runInContext('INTERVALO_SOM = ' + intervalo, s.context);
        s.context.input.soundLevel = () => constante ? 42 : Math.floor(net.now / periodo) * amplitude;
    }
    let dropped = 0;
    if (perda) net.drop = (a,b,p) => {
        if ((p[0] & 15) === 2 && (++dropped % 10 === 0)) return true;
        return false;
    };
    const ages = [], vistos = new Set(), rx = c.receiver;
    c.receiver = p => {
        if (c.context.Rede.tipo(p) === 2 && net.now > 2000 && !constante) {
            const value = c.context.Rede.carga(p)[0];
            const key = c.context.Rede.id(p) + ':' + value;
            const origem = value / amplitude * periodo;
            if (!vistos.has(key) && origem >= 2000) ages.push(net.now - origem);
            vistos.add(key);
        }
        rx(p);
    };
    let filaMax = 0;
    for (let i = 0; i < 5; i++) {
        c.input = 'PING|EST0|' + (100 + i) + '\n';
        for (let j = 0; j < 2000; j++) {
            net.run(1);
            filaMax = Math.max(filaMax, ...net.nodes.map(n => n.context.Rede.filaDebug()));
        }
    }
    const ping = c.lines.filter(x => x.endsWith('|OK')).length;
    if (intervalo >= 200) {
        assert.equal(ping, 5, 'PING não deve sofrer starvation nesta carga');
        assert.ok(stations.every(s => s.icon === 'YES'));
    }
    const sent = net.tx.filter(t => stations.some(s => s.index === t.node) && (t.bytes[0] & 15) === 2).length;
    const received = c.lines.filter(x => x.startsWith('SOM|')).length;
    ages.sort((a,b) => a-b);
    assert.ok(filaMax <= 24);
    return {version:antigo ? 'v0.0.2' : 'atual', relays, stations:count, intervalo, periodo, duplicatas, constante, perda, sent, received, filaMax,
            p95_sensor_ms: ages[Math.floor(ages.length * .95)] || 0,
            tx_total:net.tx.length, ping};
}
for (const r of [0,1,8,12]) for (const n of [1,4]) {
    console.log(JSON.stringify(cenario(r,n,500,false,false,true)));
    console.log(JSON.stringify(cenario(r,n,200)));
}
console.log(JSON.stringify(cenario(8,4,500,true,false,true)));
console.log(JSON.stringify(cenario(8,4,200,true)));
console.log(JSON.stringify(cenario(8,4,200,false,true)));
for (const r of [0,1,8,12]) console.log(JSON.stringify(cenario(r,4,200,false,false,false,40)));
console.log(JSON.stringify(cenario(8,4,100,false,false,false,40)));
console.log(JSON.stringify(cenario(8,4,200,false,false,false,40,true)));
