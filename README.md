# MicroSerial — Central Micro:bit Radio

Rede para **micro:bit V2**, com uma Central, várias Estações e Pontes genéricas.
O protocolo V1 usa grupo **42**, potência **7**, pacotes binários de até **19 bytes**,
deduplicação e até **12 Pontes consecutivas**.

O [relatório de auditoria](AUDITORIA.md) contém diagnóstico, inventário, formato de
pacotes, justificativas, limitações, testes e checklist de validação física.

## Site público independente do PC

### Windows: iniciar com dois cliques

Na primeira configuração:

1. Clone/baixe o projeto e instale Python **3.10+**, habilitando **Add Python to PATH**.
2. Copie `.env.example` para `.env` na raiz do projeto.
3. No `.env`, substitua `COLOQUE_SEU_TOKEN_AQUI` pelo token privado já configurado
   no Render. A URL do backend atual já vem preenchida no exemplo.
4. Conecte a Central micro:bit por USB e dê dois cliques em **`iniciar.bat`**.

O launcher cria `.venv` se necessário, instala dependências ausentes ou com versão
diferente das fixadas em `requirements.txt`, carrega a configuração e executa
`app_radio.py --gateway-only` com o Python da `.venv`. A primeira instalação
precisa de internet; nas seguintes, dependências corretas não são reinstaladas.
O pip fornecido pelo Python é suficiente, sem atualização forçada a cada execução.
Erros deixam a janela aberta com instruções. Para parar, use **Ctrl+C**.

Após iniciar as threads do gateway, `iniciar.bat` solicita uma única abertura do
frontend público no navegador padrão do Windows. Reconexões não abrem novas abas.
Isso confirma a inicialização do processo, não a conexão à Central/Render; a página
pode mostrar offline enquanto aguarda dados. Se o navegador falhar, o gateway
continua normalmente e a URL aparece para abertura manual. `iniciar-local.bat`
mantém seu comportamento, sem abrir navegador automaticamente.

Validação do launcher: 11 testes, incluindo execução real dos `.bat` no
Windows em pasta com espaços, além de instalação limpa isolada e segunda execução
sem reinstalar. `pip check` passou nesse ambiente. Os testes usam um app substituto
e configuração fictícia, sem conectar ao hardware/backend nem usar seu `.env`.

No uso diário: **conecte a Central → abra `iniciar.bat` → acesse
[o frontend público](https://estacao-radio-gules.vercel.app/)**.
Backend atual: `https://estacao-radio-backend.onrender.com`.

**`.env NÃO deve ser commitado. Nunca compartilhe seu token.** `.env` e `.venv/`
já estão ignorados pelo Git. Não coloque o token nos `.bat` nem no frontend.
Os launchers usam o `.env` da pasta do projeto, com prioridade sobre variáveis
homônimas do terminal. Espaços, comentários e valores entre aspas são aceitos;
use aspas simples ao redor de valores com caracteres especiais. Não há expansão
de `${VAR}` nem execução de comandos. Apenas variáveis `MICROSERIAL_*` são carregadas.

Opcional: **`iniciar-local.bat`** usa o mesmo setup e `.env`, mas executa o modo
normal, com interface em `http://127.0.0.1:5000` **e publicação remota**.
O comando direto `python app_radio.py` continua inalterado e não carrega `.env`
automaticamente; permanece disponível para uso manual exclusivamente local.
Se mover a pasta e a `.venv` deixar de funcionar, recrie apenas o ambiente virtual
(ambientes Python não são portáveis); preserve o `.env` privado.

O frontend pode ficar na **Vercel** e o backend mínimo no **Render**:

```text
micro:bits → Central → USB → Python no PC → HTTPS → Render (RAM)
                                                      ↓ Socket.IO
                                               site estático Vercel
```

O site abre sem o PC e mostra offline. O backend guarda somente o estado atual,
sem banco, login ou histórico; reiniciar o processo pode apagar as estações.
O gateway reutiliza a descoberta serial, parser e estado existentes. Não há
alterações no protocolo/firmware. `transport: "serial"` identifica a origem;
`bluetooth` está apenas reservado, sem implementação BLE.

**[Passo a passo de deploy, variáveis e limitações → DEPLOY.md](DEPLOY.md)**

No PC (PowerShell), depois de configurar o backend:

```powershell
$env:MICROSERIAL_BACKEND_URL = "https://SEU-BACKEND.onrender.com"
$env:MICROSERIAL_GATEWAY_TOKEN = "SEU-TOKEN-SECRETO"
python app_radio.py
```

Esse comando mantém a interface local e publica o estado remoto. Para atuar
somente como gateway, sem servidor local: `python app_radio.py --gateway-only`.
Sem essas duas variáveis, `python app_radio.py` continua exclusivamente local.
Não configure o token na Vercel: ela recebe apenas `RADIO_BACKEND_URL`, uma URL pública.

A página pública é somente leitura; o botão PING continua na interface **local**.
A Central fica offline após 10 s sem gateway; estações expiram após o timeout
existente (5 s por padrão sem sinal válido). O Render gratuito pode dormir;
isso não impede que o HTML na Vercel abra e mostre offline.

## Opção 1 — usuário comum: gravar o HEX pronto

Os arquivos abaixo foram compilados com o MakeCode oficial
`pxt-microbit 9.1.1` / `pxt-core 13.0.1`. São HEX universais que incluem a variante V2:

- [Central](microbit/firmware/central.hex)
- [Estação QUARTO / Quarto](microbit/firmware/estacao.hex)
- [Ponte](microbit/firmware/ponte.hex)

1. Feche o aplicativo Python durante a gravação.
2. Conecte o micro:bit V2 por USB com cabo de dados; ele deve aparecer como unidade
   `MICROBIT`.
3. Copie o HEX do papel desejado para essa unidade. Aguarde terminar a gravação e
   o reinício. Não desconecte durante a cópia.
4. Grave **uma** Central, **uma** Estação QUARTO e quantas Pontes precisar.
   Todas as Pontes usam exatamente o mesmo HEX, sem ID de Estação configurado.
5. Para Estações adicionais, gere firmware com **ID diferente** conforme abaixo.
   Não grave o HEX QUARTO em várias Estações da mesma rede.
6. Mantenha a Central conectada ao PC pela USB; Estações e Pontes podem usar
   alimentação independente. Estação/Central exibem ✓ quando há comunicação
   correspondente; a Ponte exibe ✓ como indicação de inicialização, não de entrega.
7. Atualize **todos os papéis juntos**. O rádio binário novo não conversa com o
   rádio textual antigo (`RELAY`, `R`, `RETURN`).

Nenhum aparelho foi gravado automaticamente. Faça primeiro o ensaio direto,
depois uma Ponte e então os multissaltos descritos no relatório.

## Opção 2 — MakeCode: copiar apenas um arquivo completo

Escolha o papel e copie **TODO o conteúdo de apenas um arquivo**:

- [makecode/central.ts](microbit/makecode/central.ts)
- [makecode/estacao.ts](microbit/makecode/estacao.ts)
- [makecode/ponte.ts](microbit/makecode/ponte.ts)

**Não copie `protocolo.ts` separadamente: ele já está incluído.** Os caminhos
`firmware/` e `makecode/` ficam dentro da pasta `microbit/` deste projeto.

1. Abra [MakeCode para micro:bit](https://makecode.microbit.org/) e crie um novo projeto.
2. Selecione **JavaScript**. Para evitar erros ao juntar arquivos, copie **todo**
   o conteúdo do arquivo escolhido acima, substituindo
   o conteúdo inicial do editor.
3. Se estiver criando uma Estação, procure **CONFIGURAÇÃO DA ESTAÇÃO** e altere
   o ID e o nome logo abaixo, por exemplo:
   `let ID_ESTACAO = "COZINHA"` e `let NOME_ESTACAO = "Cozinha"`.
4. O ID deve ser único, ter **2–8** caracteres entre `A-Z`, `0-9`, `_` e `-`.
   O nome aceita acentos e até **24 unidades UTF-16** (caracteres fora do BMP,
   como alguns emojis, usam duas). Não use `|`, `:` ou caracteres de controle.
5. Verifique que as extensões nativas **radio** e **microphone** estão disponíveis.
   Projetos micro:bit usuais as incluem; se o editor indicar namespace ausente,
   adicione a extensão nativa correspondente em **Extensões**.
6. Clique em **Baixar/Download**. Grave o HEX produzido em um **micro:bit V2**.
   Repita o processo para cada ID distinto.

Para Central e Ponte, mantenha o código como está e prossiga para Download.
Não junte dois papéis no mesmo projeto.

Os arquivos `microbit/makecode/*.ts` são **gerados automaticamente**. Os fontes
oficiais continuam sendo `microbit/protocolo.ts` e `microbit/central.ts`,
`microbit/estacao.ts`, `microbit/ponte.ts`. Para manutenção no repositório, edite
esses fontes e regenere; não mantenha alterações manuais nos arquivos gerados.
Personalizar ID/nome na cópia colada no editor é suficiente para gravar uma nova unidade.

## Executar a aplicação PC

Use Python 3.10+ no Windows, a partir desta pasta:

```powershell
git clone https://github.com/dabulkase-ux/estacao-radio.git
cd estacao-radio
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app_radio.py
```

Se já clonou o projeto, basta ativar o ambiente e executar os dois últimos comandos.
Se o PowerShell impedir a ativação, use `.\.venv\Scripts\python.exe` em vez de `python`.

Abra `http://127.0.0.1:5000`. O servidor permanece vinculado ao localhost.
A página recebe dados em tempo real e o botão **Testar comunicação** envia um
PING até a Estação; “Resposta confirmada” só aparece após a volta do pacote.

A seleção automática exige a assinatura `CENTRAL_ONLINE|1` do firmware novo.
Uma Ponte conectada por USB não será aceita como Central. Para selecionar uma
porta explicitamente, mantendo a verificação da assinatura:

```powershell
$env:MICROSERIAL_PORT = "COM5"
python app_radio.py
```

Dependências da aplicação: Flask 3.1.3, Flask-SocketIO 5.6.1, pyserial 3.5 e
simple-websocket 1.1.0. A interface ainda carrega Socket.IO do CDN indicado no HTML.

## Estado, intervalos e serial

- Som: aproximadamente 500 ms + jitter; heartbeat: 1000 ms + jitter quando confirmado.
- ACK: espera de 2500 ms, no máximo três tentativas por heartbeat.
- Ícone de comunicação da Estação: offline após 8 s sem ACK.
- PC: timeout padrão de Estação de 5 s sem dados válidos; esse estado comprova
  recepção da subida. Use PING para testar os dois sentidos.
- Identificação/status/nome: anúncio inicial e aproximadamente a cada 30 s.
- Serial: 115200 baud; LF ou CRLF; linhas parciais são remontadas antes do parser.

`/api/data` e `radio_data` preservam o estado da Central, porta, timestamps,
estações, som, intervalos e histórico limitado. Mensagens sem ID não herdam uma
“última estação”; entradas inválidas e ACKs refletidos não renovam o estado.

O rádio usa os tipos H/S/I/N/T/A/P/Q detalhados no relatório. A Central traduz a
subida em linhas legíveis para o PC, como:

```text
CENTRAL_ONLINE|1
ID|QUARTO
HEARTBEAT|QUARTO
SOM|QUARTO|250
STATUS|QUARTO|ONLINE
NPART|QUARTO|123|0|3|5100750061
```

NPART é remontado no PC como nome UTF-16LE. O retorno usa
`PING|QUARTO|token` e `CMD|QUARTO|token|OK` (ou TIMEOUT/BUSY).
São preservados no parser formatos completos legados como
`SOM|ID|valor`, `RADIO|ID|nome|ONLINE|SOM|valor` e
`ID=QUARTO|NOME=Quarto|SOM=57`; isso não torna o firmware compatível com o rádio antigo.

## Configuração do PC

Valores inválidos ou fora da faixa utilizam os padrões de `config.py`.

| Variável | Padrão | Observação |
|---|---:|---|
| `MICROSERIAL_PORT` | automático | COM explícita, ainda exige assinatura |
| `MICROSERIAL_BAUDRATE` | 115200 | Precisa coincidir com o firmware |
| `MICROSERIAL_RECONNECT_SECONDS` | 2 | Espera entre tentativas de conexão |
| `MICROSERIAL_STATION_TIMEOUT` | 5 | Segundos sem dados válidos |
| `MICROSERIAL_HISTORY_LIMIT` | 100 | Registros por Estação |
| `MICROSERIAL_SERIAL_TIMEOUT` | 0.5 | Timeout de uma leitura serial |
| `MICROSERIAL_PROBE_TIMEOUT` | 1.5 | Espera da assinatura; muito baixo pode impedir descoberta |
| `MICROSERIAL_MAX_MESSAGE_LENGTH` | 512 | Limite de linha serial, não do pacote de rádio |
| `MICROSERIAL_LOG_LEVEL` | INFO | DEBUG/INFO/WARNING/ERROR/CRITICAL |

## Reproduzir testes e compilação oficial

Para gerar os três arquivos autocontidos, sem instalar o compilador:

```powershell
node tools/gerar_makecode.js
node tools/gerar_makecode.js --check
```

O segundo comando verifica sem modificar arquivos e falha se algum estiver ausente
ou desatualizado. O build abaixo também gera automaticamente o arquivo do papel
selecionado e **compila esse arquivo completo como único `main.ts`**.

Os testes JavaScript usam Node **24+**; a simulação precisa de
`node:module.stripTypeScriptTypes`. Python e as dependências acima também são necessários.

```powershell
node --disable-warning=ExperimentalWarning tests/rede_sim.js
node tests/frontend_test.js
node tests/frontend_online_test.js
python -m unittest discover -s tests -v
python -m compileall -q app_radio.py parser.py protocolo_serial.py radio.py serial_manager.py gateway_remote.py backend_online.py online_wsgi.py
```

Para compilar os firmwares com o alvo oficial MakeCode, dentro desta pasta:

```powershell
npm.cmd install --prefix .makecode-check --cache .makecode-check/npm-cache --ignore-scripts --no-audit --no-fund pxt-microbit@9.1.1
node tests/makecode_build.js central
node tests/makecode_build.js estacao
node tests/makecode_build.js ponte
```

A compilação gera HEX universal e V2 em `.makecode-check/projects/<papel>/built/`.
O fonte autocontido é gerado em `microbit/makecode/<papel>.ts`. O script copia o HEX
universal e um manifesto SHA-256 para `microbit/firmware/<papel>.hex/.json`.
Por compatibilidade, `firmware/<papel>.ts` também recebe uma cópia gerada idêntica;
para MakeCode use a localização principal `makecode/`.
O manifesto registra os hashes do protocolo, do papel, do arquivo autocontido
efetivamente compilado e do HEX. Não use `--hw mbcodal`: o alvo
micro:bit já compila as variantes oficiais automaticamente.

Para gerar outra Estação pela CLI, edite `microbit/estacao.ts` e execute novamente
o build da Estação; guarde o HEX com o ID correspondente antes da próxima configuração.
Os HEXs entregues foram compilados, mas o alcance, as colisões, a carga máxima,
o consumo de RAM e a estabilidade prolongada ainda exigem ensaio nos aparelhos.
