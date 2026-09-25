// Requer: npm install --prefix .makecode-check --ignore-scripts pxt-microbit@9.1.1
// Compila o código real com PXT. O HEX universal inclui micro:bit V2 (mbcodal).
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const {generateRole} = require('../tools/gerar_makecode');
const root = path.join(__dirname, '..');
const role = process.argv[2];
if (!['central', 'estacao', 'ponte'].includes(role)) throw new Error('Informe central, estacao ou ponte');
const target = path.join(root, '.makecode-check/node_modules/pxt-microbit');
const project = path.join(root, '.makecode-check/projects', role);
fs.mkdirSync(project, {recursive: true});
const {protocol, main, combined, output} = generateRole(role);
// Compilar exatamente o arquivo autocontido que o usuário cola no MakeCode.
fs.copyFileSync(output, path.join(project, 'main.ts'));
fs.writeFileSync(path.join(project, 'pxt.json'), JSON.stringify({
    name: 'microserial-' + role,
    dependencies: {core: '*', radio: '*', microphone: '*'},
    files: ['main.ts'],
    preferredEditor: 'tsprj',
}, null, 2));
// Não confundir --hw (extensões de outras placas) com mbcodal. O alvo
// micro:bit compila suas duas variantes oficiais automaticamente.
for (const name of ['binary.hex', 'mbcodal-binary.hex']) {
    const output = path.join(project, 'built', name);
    if (fs.existsSync(output)) fs.unlinkSync(output);
}
process.chdir(project);
require(path.join(root, '.makecode-check/node_modules/pxt-core')).mainCli(target,
    ['build', '--install']).then(() => {
        for (const name of ['binary.hex', 'mbcodal-binary.hex']) {
            const output = path.join(project, 'built', name);
            if (!fs.existsSync(output) || fs.statSync(output).size < 10000) {
                throw new Error('Compilação não produziu ' + output);
            }
        }
        const outputDir = path.join(root, 'microbit/firmware');
        fs.mkdirSync(outputDir, {recursive: true});
        if (!fs.readFileSync(path.join(project, 'main.ts')).equals(combined)) {
            throw new Error('O fonte compilado difere do arquivo autocontido gerado');
        }
        const hex = fs.readFileSync(path.join(project, 'built/binary.hex'));
        const hash = data => crypto.createHash('sha256').update(data).digest('hex');
        fs.writeFileSync(path.join(outputDir, role + '.hex'), hex);
        // Compatibilidade com a distribuição anterior; a localização principal é makecode/.
        fs.writeFileSync(path.join(outputDir, role + '.ts'), combined);
        fs.writeFileSync(path.join(outputDir, role + '.json'), JSON.stringify({
            role, target: 'microbit', targetVersion: '9.1.1', pxtVersion: '13.0.1',
            includesV2: true, protocolSha256: hash(protocol), roleSha256: hash(main),
            makecodeSource: 'microbit/makecode/' + role + '.ts', makecodeSha256: hash(combined),
            hexSha256: hash(hex),
        }, null, 2) + '\n');
        console.log('OK: ' + role + ' — HEX universal e runtime V2 gerados');
    }).catch(error => {
        console.error(error); process.exitCode = 1;
    });
