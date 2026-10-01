// Fail-closed: o compilador do produto não abre rede nem executa ferramentas externas.
const deny = () => { throw new Error('Compilação offline: acesso à rede/processo externo recusado.'); };
require('node:net').Socket.prototype.connect = deny;
for (const name of ['node:http', 'node:https']) {
    const mod = require(name); mod.request = deny; mod.get = deny;
}
require('node:tls').connect = deny;
require('node:dgram').createSocket = deny;
global.fetch = deny;
const cp = require('node:child_process');
for (const name of ['spawn','spawnSync','exec','execSync','execFile','execFileSync','fork']) cp[name] = deny;
