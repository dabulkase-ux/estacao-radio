// Tempo virtual com o custo de basic.forever do runtime oficial; sem física de RF.
const assert = require('node:assert/strict');
const vm = require('node:vm');
const {execFileSync} = require('node:child_process');
const {Network} = require('./rede_sim');
const antigo = execFileSync('git', ['show', 'aae05ec:microbit/estacao.ts'], {encoding:'utf8'});
function setup(source, relays=0) {
    const net = new Network({foreverDelay:20, ...(source ? {estacao:source} : {})});
    const s = net.add('estacao'), c = net.add('central');
    let last = s;
    for(let i=0;i<relays;i++){const r=net.add('ponte');net.link(last,r);last=r;}
    net.link(last,c);
    s.context.input.soundLevel=()=>20;
    net.run(1500);
    // Aguarda um envio de refresh para posicionar o pulso dentro da janela real.
    const previous=vm.runInContext('ultimoEnvioSom',s.context);
    while(vm.runInContext('ultimoEnvioSom',s.context)===previous) net.run(1);
    const start=net.now;
    s.accepted=[];
    const send=s.context.Rede.enviar;
    s.context.Rede.enviar=p=>{const ok=send(p);if(ok && s.context.Rede.tipo(p)===2)s.accepted.push(net.now);return ok;};
    return {net,s,c,start};
}
function pulse(duration, offset, source, relays=0) {
    const {net,s,c,start}=setup(source,relays);
    s.context.input.soundLevel=()=>net.now>=start+offset && net.now<start+offset+duration ? 200 : 20;
    net.run(1600);
    const heard=c.lines.includes('SOM|QUARTO|200');
    if(!source){
        assert.ok(heard, `pulso ${duration}ms offset ${offset} relays ${relays}`);
        const values=c.lines.filter(x=>x.startsWith('SOM|QUARTO|'));
        assert.equal(values.at(-1),'SOM|QUARTO|20','acumulador deve liberar a queda');
        const tx=s.accepted;
        for(let i=1;i<tx.length;i++) assert.ok(tx[i]-tx[i-1]>=200,'limite de tráfego');
    }
    return heard;
}
let count=0;
for(const duration of [30,60,100,150]) {
    assert.equal(pulse(duration,10,antigo),false,'baseline deve reproduzir perda');
    for(const offset of [1,10,20,30]) {pulse(duration,offset);count++;}
    for(const relays of [1,8,12]) {pulse(duration,10,null,relays);count++;}
}
{
    const {net,s,start}=setup();
    s.context.input.soundLevel=()=>20+Math.floor(net.now/30)%3;
    net.run(5000);
    const tx=net.tx.filter(t=>t.node===s.index && (t.bytes[0]&15)===2 && t.at>start+100);
    assert.ok(tx.length>=4 && tx.length<=5,'ruído 0..2 só gera refresh ~1s');count++;
}
{
    const {net,s,c,start}=setup();
    s.context.input.soundLevel=()=>net.now<start+100 ? 23 : 20;
    net.run(600);
    assert.ok(c.lines.includes('SOM|QUARTO|23'),'delta exatamente 3 não suprimido');count++;
}
{
    const {net,s,c,start}=setup();
    const send=s.context.Rede.enviar;
    let refused=0;
    s.context.Rede.enviar=p=>{if(s.context.Rede.tipo(p)===2 && refused++===0)return false;return send(p);};
    s.context.input.soundLevel=()=>net.now<start+100 ? 200 : 20;
    net.run(1000);
    assert.ok(c.lines.includes('SOM|QUARTO|200'),'fila cheia não apaga pico');
    assert.equal(c.lines.filter(x=>x.startsWith('SOM|')).at(-1),'SOM|QUARTO|20');count++;
}
{
    const {net,s,c,start}=setup();
    s.context.input.soundLevel=()=>net.now<start+100 || (net.now>=start+230 && net.now<start+330) ? 200 : 20;
    net.run(800);
    assert.equal(c.lines.filter(x=>x.startsWith('SOM|')).at(-1),'SOM|QUARTO|20','pico igual não prende queda até refresh');count++;
}
{
    const {net,s,c,start}=setup();
    s.context.input.soundLevel=()=>net.now<start+60 ? 100 : net.now<start+120 ? 230 : 20;
    net.run(800);
    const values=c.lines.filter(x=>x.startsWith('SOM|')).slice(-2);
    assert.deepEqual(values,['SOM|QUARTO|230','SOM|QUARTO|20'],'máximo da janela, seguido de acumulador limpo');count++;
}
console.log(`${count} cenários peak-hold aprovados; 4 perdas reproduzidas no firmware anterior.`);

