# Distribuição Windows — v0.0.4.1 (candidata a teste físico)

## Auditoria e decisão

O ponto de entrada de desenvolvimento é `python -m configurador`. A GUI importa
Tkinter e os módulos model/builder/compiler/devices; eles usam somente a biblioteca
padrão Python (JSON, pathlib, tempfile, subprocess, ctypes/Win32, threading/queue).
Não importam gateway, Flask, pyserial, dotenv, frontend ou credenciais.

O subprocesso é Node → `tools/compilar_configurado.js` → PXT oficial. O gerador
`tools/gerar_makecode.js` compõe os quatro fontes-base em `microbit/`. O TypeScript
é configurado por AST em diretório temporário; parâmetros não mudam a composição
C++ das extensões. O alvo npm contém `built/target.json` (pacotes nativos embutidos)
e `built/hexcache` (imagens nativas por hash). Em pxt-core 13.0.1, `getHexInfoAsync`
consulta `<target>/built/hexcache/<sha>.hex` antes de tentar cloud/local C++.
As quatro imagens do alvo somam aproximadamente 3 MB; não são HEXs de testes.

A distribuição inclui Python/Tcl/Tk via PyInstaller, Node 24.18.0 privado,
pxt-microbit 9.1.1, pxt-core 13.0.1 e dependências fixadas por package-lock,
scripts JS e quatro fontes-base. Não inclui `.makecode-check/projects`, cache
npm, `.pxt` do usuário ou ferramentas C++/Git/npm. Os pacotes oficiais já contêm
os recursos nativos necessários para os três papéis atuais. Novas extensões C++
exigirão nova auditoria/cache/build; falta de cache causa erro, nunca download.

| Formato | Avaliação |
|---|---|
| Onefile | Extrairia o runtime grande a cada abertura; mais demora, temporários e dificuldade de diagnóstico/antivírus. Não escolhido. |
| Onedir | Executável claro com arquivos privados estáveis, sem extração a cada abertura. Escolhido. Copiar a pasta inteira. |
| Instalador | Pode instalar a mesma pasta em Program Files, adicionar atalhos e atualizar versões. Etapa posterior; não é necessário para provar autonomia. |

Referências: [PyInstaller: modos de operação](https://pyinstaller.org/en/stable/operating-mode.html)
e [compilação/linkedição MakeCode](https://forum.makecode.com/t/understanding-the-compilation-and-linking-process-in-pxt-microbit-makecode-from-blocks-to-hex-file/31682).
Não alteramos o compilador oficial nem remendamos binários HEX pré-compilados.

## Preparação de desenvolvimento (não é feita pelo usuário final)

Windows x64, Python 3.13.12 x64 com Tcl/Tk e Node 24.18.0 x64. No repositório:

```powershell
python -m venv .makecode-check/packaging-venv
.makecode-check/packaging-venv/Scripts/python.exe -m pip install -r packaging/requirements-build.txt
```

Para uma instalação npm limpa, copie os arquivos fixados para a pasta de ferramentas
antes de instalar (isto atualiza somente ferramentas ignoradas pelo Git):

```powershell
Copy-Item packaging/package.json .makecode-check/package.json
Copy-Item packaging/package-lock.json .makecode-check/package-lock.json
npm.cmd ci --prefix .makecode-check --ignore-scripts --no-audit --no-fund
```

Depois:

```powershell
python tools/build_windows.py
```

Cada build gera uma pasta nova em `dist/windows-AAAAMMDD-HHMMSS/`; não apaga builds
anteriores. O build valida versões do Python de empacotamento, pacotes e Node,
empacota Python/Tk em ambiente isolado e copia somente recursos autorizados.
O lock npm fixa dependências transitivas; o lock pip fixa ferramentas do build.
É um processo repetível, não uma promessa de EXEs idênticos bit a bit (timestamps
PE/build variam). HEXs padrão continuam comparados byte a byte.

A distribuição é a pasta **Dualkase MicroSerial Configurator**, contendo:

```text
Dualkase MicroSerial Configurator.exe
_internal/                 Python, Tcl/Tk, DLLs
  resources/
    runtime/node.exe
    .makecode-check/node_modules/   PXT/alvo/dependências e hexcache
    tools/                 scripts JS e bloqueio offline
    microbit/              somente quatro fontes .ts
    expected-firmware.json hashes de referência públicos
LICENSES/
LEIA-ME.txt
manifest.json              inventário SHA-256 e tamanhos
```

Npm não está embarcado como ferramenta executável; o código Node não depende dele.
Não copie só o `.exe`. Para entregar, compacte essa pasta inteira em ZIP ou copie-a.
O ícone é provisoriamente o padrão PyInstaller. Um `.ico` definitivo poderá ser
passado no comando de build por `--icon`, sem mudar GUI/protocolo.
Build sem assinatura Authenticode: SmartScreen/antivírus podem pedir avaliação da
procedência. Não desative proteções; assinatura e instalador ficam para etapa futura.

## Recursos, escrita e offline

`configurador/resources.py` usa `_MEIPASS/resources` no executável e a raiz do
repositório em desenvolvimento. Não depende do diretório atual nem de caminhos
pessoais. No modo empacotado, Node vem exclusivamente do runtime privado; se faltar,
falha sem procurar Node global. Projetos, perfil/cache transitório do PXT e HEXs
intermediários ficam em `TemporaryDirectory`, nunca na pasta de instalação.

O subprocesso recebe ambiente mínimo, sem `NODE_OPTIONS`, `NODE_PATH`, tokens ou
configurações PXT do usuário, com perfil vazio e PATH apontando ao Node privado.
`--no-global-search-paths` evita módulos globais. `tools/offline_guard.js` bloqueia
conexões TCP/TLS/HTTP, fetch, UDP e subprocessos externos no processo Node. Assim,
mesmo uma falta de cache falha explicitamente em vez de instalar/baixar algo.
Isto verifica a ausência de dependência de rede no fluxo; não é uma barreira contra
código malicioso arbitrário nem substitui um teste em máquina realmente desconectada.

Gerar HEX mantém o arquivo escolhido; Gerar e gravar continua temporário. DAPLink,
V2, múltiplas unidades, revalidação e observação de remontagem continuam iguais.
Cópia concluída nunca é prova de boot. Nenhum firmware/protocolo foi alterado.

## Validação automática e limites

O build executa esta validação automaticamente. Para repetir somente a validação,
passe a pasta exata já criada:

```powershell
python tools/test_windows_distribution.py "dist/windows-AAAAMMDD-HHMMSS/Dualkase MicroSerial Configurator"
```

O teste confere o inventário, copia a distribuição para um diretório temporário
fora do repositório com espaços/acentos, executa o EXE com PATH vazio e perfil
limpo e usa outro diretório atual. O diagnóstico `--self-test` abre Tk real em
janela oculta, testa seleção múltipla, gera Central/Estação/Ponte, configurações
alternativas e duas gravações temporárias com USB simulado. Compara hashes padrão,
recusa sobrescrita, confere limpeza e garante que a pasta da aplicação não mudou.
O relatório `standalone-validation.json` fica ao lado da pasta distribuível, não
é recurso necessário do usuário final. Não executa flash em aparelho real.

Este ensaio remove ferramentas globais da resolução e caches pessoais do fluxo,
mas ainda usa este Windows e suas bibliotecas do sistema. Não equivale a uma VM
limpa nem prova todos os drivers/antivírus/versões Windows. Program Files não foi
modificado durante o teste; a verificação de pasta de instalação inalterada testa
o requisito de não escrever nela. Caminhos extremamente longos ainda dependem da
política de caminhos longos do Windows; prefira uma pasta extraída de caminho curto.

## Artefato e inventário desta candidata

Pasta: `dist/windows-20260928-175502/Dualkase MicroSerial Configurator`.
Executável: `Dualkase MicroSerial Configurator.exe` dentro dessa pasta.

| Componente | Bytes | MB (decimal) |
|---|---:|---:|
| Python/Tk, aplicativo, scripts, fontes e licenças | 26.975.113 | 26,98 |
| Node privado | 92.534.088 | 92,53 |
| PXT/MakeCode e dependências | 463.457.820 | 463,46 |
| Inventário SHA-256 | 5.074.633 | 5,07 |
| **Total** | **588.041.654** | **588,04** |

São 28.826 arquivos inventariados, mais o próprio `manifest.json` (que não inclui
seu próprio hash). O total é cerca de 560,80 MiB; tamanho alocado em disco depende
do sistema de arquivos. Python/Tk/app inclui todos os recursos menores fora de
Node/npm, não apenas o runtime Python.

A limpeza conservadora retirou 22.313.299 bytes de exemplos/testes e categorias
auxiliares. Antes dela, quatro compilações reais com bloqueio de rede rastrearam
291 leituras/módulos, sem usar `test`, `tests`, `__tests__`, `example`, `examples`,
`.github` ou `coverage`. Imagens nativas, pacotes, licenças e recursos do alvo
foram preservados. O relatório `pruning-audit.json` está ao lado da distribuição.

A auditoria dos arquivos distribuídos não encontrou `.env`, `.git`, configuração
de token do gateway, blocos de chaves privadas ou caminhos pessoais examinados.
Nomes genéricos de variáveis de autenticação e marcadores de formatos presentes
em bibliotecas não são classificados automaticamente como credenciais reais.
O inventário registra SHA-256 de cada arquivo incluído; não é assinatura digital.

A regressão já concluída passou com 86 testes Python (82 anteriores e 4 de
empacotamento), três suítes frontend, 16 cenários de protocolo, 33 de peak-hold,
25 de carga, redes configuradas e sincronização dos fontes MakeCode. GUI,
detecção/gravação USB, fluxo temporário e fontes/firmwares versionados não foram
alterados. A tag v0.0.4 continua no commit `855e4a5`.

### Resultado final do teste isolado

Concluído com sucesso em 29/09/2026, sem reconstruir o executável.
Relatório: `dist/windows-20260928-175502/standalone-validation.json`.

- EXE executado em cópia temporária fora do repositório, com espaços/acentos,
  outro diretório atual, PATH vazio e perfil novo.
- GUI Tk real inicializada em janela oculta; seleção múltipla preservada.
- Compilação oficial real: Central/rede42, QUARTO/rede42, Ponte/rede42,
  SALA/rede42 e LAB01/rede43, usando Node/PXT privados com rede bloqueada.
- Os três HEXs padrão coincidiram byte a byte com os hashes de referência;
  todas as cinco configurações produziram HEXs distintos e válidos.
- Geração em arquivo e recusa de sobrescrita passaram. Duas gravações diretas
  com USB simulado passaram e removeram seus temporários.
- Na cópia isolada, retirar o hexcache fez a compilação falhar. O cache foi
  restaurado em `finally`; a distribuição original não foi alterada.
- A instalação permaneceu inalterada e não sobraram temporários de firmware.

Não é necessário repetir o inventário completo para executar novamente testes
funcionais direcionados. Esta validação não substitui o ensaio físico abaixo.

## Roteiro físico

No PC atual:

1. Feche terminal/VS Code e o gateway. Abra o EXE com duplo clique.
2. Gere QUARTO/rede42 em arquivo. Gere SALA/rede42 para confirmar personalização.
3. Conecte V2, atualize a lista, selecione-o e use Gerar e gravar. Não deve pedir
   local de salvamento. Aguarde a mensagem final; confirme LEDs/boot.
4. Repita para outro aparelho, depois Ponte/Central. Nenhum HEX permanente deve
   ser acumulado pelo fluxo direto. Com duas unidades, confirme seleção explícita.
5. Inicie o gateway existente separadamente, confira presença/SOM, palma curta
   (peak-hold) e PING pela interface local. O gateway não faz parte deste EXE.

Em outro Windows 10/11 x64 sem ferramentas de desenvolvimento:

1. Copie **toda** a pasta distribuível; não copie repositório, caches ou `.env`.
2. Extraia em Downloads ou Desktop; desconecte internet/Wi-Fi.
3. Abra somente o EXE, gere os três papéis e SALA/rede43.
4. Conecte V2 e grave. Repita a seleção com dois aparelhos e confirme boot/radio.
5. Teste também uma pasta com acentos/espaços. Se houver erro, registre a mensagem
   e versão do Windows/DAPLink. Não instale Python/Node para contornar: isso
   mascararia uma falha do standalone.
6. Só após esse ensaio decida versão/tag/release. Nada foi publicado automaticamente.
