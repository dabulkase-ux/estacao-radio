const assert=require('node:assert/strict');
const {configure}=require('../tools/compilar_configurado');
const {composeRole}=require('../tools/gerar_makecode');
const {Network}=require('./rede_sim');
const net=new Network({protocolo:' ',foreverDelay:20});
function add(role,group,id='QUARTO') {
    const source=composeRole(role).combined.toString('utf8');
    net.sources[role]=configure(source,role,{group,station_id:id,name:id});
    return net.add(role,id,id);
}
const a=add('estacao',42,'QUARTO'), pa=add('ponte',42), ca=add('central',42);
const b=add('estacao',43,'LAB01'), pb=add('ponte',43), cb=add('central',43);
net.link(a,pa);net.link(pa,ca);net.link(b,pb);net.link(pb,cb);
// Arestas cruzadas só entregam quando o filtro de grupo do runtime permitir.
net.link(a,pb);net.link(b,pa);net.link(pa,pb);net.link(pa,cb);net.link(pb,ca);
net.drop=(sender,receiver)=>sender.group!==receiver.group;
net.run(5000);
assert.ok(ca.lines.some(x=>x.startsWith('SOM|QUARTO|')));
assert.ok(cb.lines.some(x=>x.startsWith('SOM|LAB01|')));
assert.ok(!ca.lines.some(x=>x.includes('LAB01')));
assert.ok(!cb.lines.some(x=>x.includes('QUARTO')));
assert.equal(a.icon,'YES');assert.equal(b.icon,'YES');
ca.input='PING|QUARTO|1\n';cb.input='PING|LAB01|2\n';net.run(3000);
assert.ok(ca.lines.includes('CMD|QUARTO|1|OK'));assert.ok(cb.lines.includes('CMD|LAB01|2|OK'));
const base=composeRole('estacao').combined.toString('utf8');
assert.equal(configure(base,'estacao',{group:42,station_id:'QUARTO',name:'Quarto'}),base);
assert.throws(()=>configure(base+'\nradio.setGroup(42)','estacao',{group:43,station_id:'SALA',name:'Sala'}),/ambígua/);
console.log('OK configurador: duas redes isoladas no modelo de grupo, ACK/PING, AST e padrão idêntico.');
