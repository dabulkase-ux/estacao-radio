// Mesmo HTML do Flask, com URL pública injetada no build. Nenhum segredo.
const fs = require('node:fs');
const path = require('node:path');
const root = path.join(__dirname, '..');
function build(url) {
    const parsed = new URL(url);
    if (parsed.origin !== url.replace(/\/$/, '') ||
        (parsed.protocol !== 'https:' && !(parsed.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(parsed.hostname)))) {
        throw new Error('RADIO_BACKEND_URL deve ser uma origem HTTPS (HTTP só no localhost)');
    }
    const html = fs.readFileSync(path.join(root, 'templates/index.html'), 'utf8');
    const marker = 'const backendUrl = ""; // PUBLIC_BACKEND_URL';
    if (!html.includes(marker) || !html.includes('const publicMode = false;')) throw new Error('Marcadores de build ausentes');
    return html.replace(marker, 'const backendUrl = ' + JSON.stringify(parsed.origin).replace(/</g, '\\u003c') + ';')
        .replace('const publicMode = false;', 'const publicMode = true;');
}
module.exports = {build};
if (require.main === module) {
    const html = build(process.env.RADIO_BACKEND_URL || '');
    fs.mkdirSync(path.join(root, 'dist'), {recursive: true});
    fs.writeFileSync(path.join(root, 'dist/index.html'), html);
    console.log('Frontend estático gerado em dist/index.html (somente configuração pública)');
}
