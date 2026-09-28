// Fonte oficial: microbit/protocolo.ts + microbit/<papel>.ts.
// Uso: node tools/gerar_makecode.js [--check]
const fs = require('node:fs');
const path = require('node:path');
const root = path.join(__dirname, '..');
const roles = ['central', 'estacao', 'ponte'];

function composeRole(role, sources = {}) {
    if (!roles.includes(role)) throw new Error('Papel inválido: ' + role);
    const protocol = sources.protocol || fs.readFileSync(path.join(root, 'microbit/protocolo.ts'));
    const main = sources.main || fs.readFileSync(path.join(root, 'microbit', role + '.ts'));
    const header = '// ARQUIVO GERADO AUTOMATICAMENTE — NÃO MANTER CÓPIAS MANUAIS.\n' +
        '// Fontes oficiais: microbit/protocolo.ts + microbit/' + role + '.ts\n' +
        '// Regenerar: node tools/gerar_makecode.js\n' +
        '// MAKECODE: copie TODO este arquivo para JavaScript. O protocolo já está incluído.\n' +
        '// Comentários dos fontes sobre adicionar protocolo.ts não se aplicam a este arquivo completo.\n' +
        (role === 'estacao' ? '// NOVA ESTAÇÃO: procure CONFIGURAÇÃO DA ESTAÇÃO abaixo e altere ID_ESTACAO e NOME_ESTACAO.\n' : '');
    const banner = role === 'estacao'
        ? '\n// ==================== CONFIGURAÇÃO DA ESTAÇÃO ====================\n' +
          '// Altere ID_ESTACAO logo abaixo: ID único, 2–8 caracteres A-Z/0-9/_/-.\n' +
          '// Exemplo: ID_ESTACAO = "COZINHA"; NOME_ESTACAO = "Cozinha".\n' +
          '// Não é necessário alterar o protocolo acima.\n'
        : '\n// ==================== PAPEL: ' + role.toUpperCase() + ' ====================\n';
    // Buffer.concat preserva os bytes exatos de ambos os fontes, inclusive CRLF.
    const combined = Buffer.concat([Buffer.from(header), protocol, Buffer.from(banner), main]);
    return {protocol, main, combined};
}
function generateRole(role, check = false) {
    const {protocol, main, combined} = composeRole(role);
    const output = path.join(root, 'microbit/makecode', role + '.ts');
    if (check) {
        if (!fs.existsSync(output) || !fs.readFileSync(output).equals(combined)) {
            throw new Error(output + ' está ausente ou desatualizado. Execute o gerador.');
        }
    } else {
        fs.mkdirSync(path.dirname(output), {recursive: true});
        fs.writeFileSync(output, combined);
    }
    return {protocol, main, combined, output};
}

module.exports = {generateRole, composeRole};
if (require.main === module) {
    if (process.argv.slice(2).some(arg => arg !== '--check')) throw new Error('Uso: node tools/gerar_makecode.js [--check]');
    const check = process.argv.includes('--check');
    for (const role of roles) {
        generateRole(role, check);
        console.log((check ? 'OK: sincronizado ' : 'Gerado: ') + 'microbit/makecode/' + role + '.ts');
    }
}
