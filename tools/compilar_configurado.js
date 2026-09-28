// Configuração somente em cópias. Usa o parser TypeScript já incluído no PXT.
const fs = require('node:fs');
const path = require('node:path');
const root = path.join(__dirname, '..');
const pxt = require(path.join(root, '.makecode-check/node_modules/pxt-core'));
const ts = global.ts;
const {composeRole} = require('./gerar_makecode');

function configure(source, role, config) {
    const tree = ts.createSourceFile('main.ts', source, ts.ScriptTarget.Latest, true);
    if (tree.parseDiagnostics.length) throw new Error('Fonte base inválido.');
    const edits = [], found = {group:0, id:0, name:0};
    function edit(node, value, key) {
        found[key]++;
        edits.push({start:node.getStart(tree), end:node.end, value});
    }
    function visit(node) {
        if (node.kind === ts.SyntaxKind.CallExpression && node.expression.getText(tree) === 'radio.setGroup') {
            if (node.arguments.length !== 1 || node.arguments[0].kind !== ts.SyntaxKind.NumericLiteral)
                throw new Error('Estrutura radio.setGroup mudou; revisão necessária.');
            edit(node.arguments[0], String(config.group), 'group');
        }
        if (role === 'estacao' && node.kind === ts.SyntaxKind.VariableDeclaration) {
            const name = node.name.getText(tree);
            if (name === 'ID_ESTACAO' || name === 'NOME_ESTACAO') {
                if (!node.initializer || node.initializer.kind !== ts.SyntaxKind.StringLiteral)
                    throw new Error('Estrutura de configuração mudou; revisão necessária.');
                const value = name === 'ID_ESTACAO' ? config.station_id : config.name;
                // JSON protege aspas, barras e controles. Escape separadores JS Unicode.
                edit(node.initializer, JSON.stringify(value).replace(/\u2028/g,'\\u2028').replace(/\u2029/g,'\\u2029'), name === 'ID_ESTACAO' ? 'id' : 'name');
            }
        }
        ts.forEachChild(node, visit);
    }
    visit(tree);
    if (found.group !== 1 || (role === 'estacao' && (found.id !== 1 || found.name !== 1)))
        throw new Error('Configuração ausente/ambígua no fonte. Não foi gerado firmware.');
    for (const e of edits.sort((a,b)=>b.start-a.start)) source=source.slice(0,e.start)+e.value+source.slice(e.end);
    return source;
}
async function main() {
    const project = path.resolve(process.argv[2]);
    const config = JSON.parse(fs.readFileSync(path.join(project,'config.json'),'utf8'));
    if (!['central','estacao','ponte'].includes(config.role) || !Number.isInteger(config.group) || config.group<0 || config.group>255)
        throw new Error('Papel/rede inválido.');
    if(config.role==='estacao' && (!/^[A-Z0-9_-]{2,8}$/.test(config.station_id) || typeof config.name!=='string' || config.name.length<1 || config.name.length>24 || /[\x00-\x1f|:]/.test(config.name)))
        throw new Error('ID/nome inválido.');
    const {combined} = composeRole(config.role);
    const source = configure(combined.toString('utf8'), config.role, config);
    fs.writeFileSync(path.join(project,'main.ts'), source);
    if(process.argv.includes('--source-only')) return;
    fs.writeFileSync(path.join(project,'pxt.json'),JSON.stringify({name:'microserial-'+config.role, dependencies:{core:'*',radio:'*',microphone:'*'},files:['main.ts'],preferredEditor:'tsprj'},null,2));
    // Reuso opcional de pacotes locais; instalação limpa também funciona pelo PXT.
    const cache=path.join(root,'.makecode-check/projects',config.role,'pxt_modules');
    if(fs.existsSync(cache)) fs.cpSync(cache,path.join(project,'pxt_modules'),{recursive:true});
    process.chdir(project);
    await pxt.mainCli(path.join(root,'.makecode-check/node_modules/pxt-microbit'),['build','--install']);
    for(const name of ['binary.hex','mbcodal-binary.hex']) {
        const output=path.join(project,'built',name);
        if(!fs.existsSync(output) || fs.statSync(output).size<10000) throw new Error('PXT não produziu '+name);
    }
}
module.exports={configure};
if(require.main===module) main().catch(e=>{console.error(e.message);process.exitCode=1;});
