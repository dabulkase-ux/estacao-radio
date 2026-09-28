# Configurador de firmware — v0.0.4

A ferramenta gera programas MakeCode oficiais para micro:bit V2, sem editar os
fontes principais. Não é um atualizador do DAPLink/bootloader. O checkpoint
v0.0.3.1, sua telemetria e peak-hold permanecem intactos.

## Preparação (uma vez, no Windows)

1. Instale Python 3.10+ com **Tcl/Tk** (opção do instalador oficial) e Node.js
   **24+** com npm. Não precisa abrir VS Code ou MakeCode. Git só é necessário
   se você escolher clonar em vez de baixar o projeto; a ferramenta não executa Git.
2. Abra PowerShell na pasta do projeto. Prepare o compilador oficial:

   ```powershell
   npm.cmd install --prefix .makecode-check --cache .makecode-check/npm-cache --ignore-scripts --no-audit --no-fund --save-exact pxt-microbit@9.1.1 pxt-core@13.0.1
   ```

3. Abra o programa:

   ```powershell
   python -m configurador
   ```

   Se já usa o ambiente do gateway: `.\.venv\Scripts\python.exe -m configurador`.
   O configurador só usa a biblioteca padrão Python (incluindo Tkinter); não
   precisa de `.env`, token, Flask, login ou instalação adicional via pip.
   `requirements.txt` continua atendendo ao gateway, sem mudanças.

A instalação npm requer internet. A compilação usa os pacotes e caches MakeCode;
sem os recursos necessários em cache, o PXT pode baixar dependências/imagens
nativas pelos serviços oficiais. Não prometemos funcionamento offline em uma
instalação limpa. O programa não baixa executáveis nem instala dependências
silenciosamente: informa se Node/PXT estiverem ausentes ou com versão diferente.

Se aparecer erro de Tcl/Tk, repare a instalação do Python habilitando Tcl/Tk.
A execução em ambiente restrito/sandbox também pode impedir sua inicialização;
abra normalmente no Windows. Os testes da GUI passaram fora desse sandbox.

## Uso normal

1. Feche o gateway e conecte o micro:bit **V2** por cabo USB de dados, sem segurar
   Reset. Ele deve aparecer como unidade **MICROBIT**, não MAINTENANCE.
2. Abra `python -m configurador` e escolha **Central**, **Estação** ou **Ponte**.
3. Escolha **Rede**, de 0 a 255. Use **42** para a rede atual.
4. Somente em Estação: preencha **ID** e **Nome**.
   - ID único nessa rede: 2–8 caracteres ASCII, letras, números, `_` ou `-`.
     Letras minúsculas são convertidas para maiúsculas; espaços não são aceitos.
   - Nome: 1–24 unidades UTF-16; acentos permitidos, emoji normalmente ocupa duas
     unidades. Sem `|`, `:` ou controles abaixo de U+0020, como quebra de linha.
5. Para **somente gerar**, clique **Gerar firmware .HEX** e salve no computador.
   Sugestões: `estacao-SALA-rede42.hex`, `central-rede42.hex`, `ponte-rede42.hex`.
   Nenhum dispositivo é necessário. Arquivo existente é recusado, mesmo se o
   diálogo nativo oferecer substituí-lo; escolha outro nome.
6. Para gravar, clique **Atualizar micro:bits USB**, confira a unidade/identificação
   e selecione o dispositivo. Com vários conectados, nenhuma seleção é automática.
7. Clique **Gerar e gravar no micro:bit** e confirme o aparelho. Não há diálogo
   para salvar: o firmware é compilado/validado temporariamente e gravado direto.
   Aguarde compilar, copiar e observar o dispositivo por ~10 s. Não desconecte
   durante a escrita. Os artefatos da operação são removidos após sucesso ou falha.
   Para guardar/enviar um HEX, use explicitamente **Gerar firmware .HEX**.
8. Leia a mensagem: **cópia concluída não prova boot nem comunicação**. Verifique
   os LEDs, a Central e o gateway. Para Ponte, ✓ significa apenas inicialização.

A gravação substitui somente o programa do aparelho escolhido. A ferramenta não
formata unidades, não apaga arquivos e não modifica o firmware de interface USB.
Não salve o HEX diretamente em unidade removível pelo diálogo de geração: use o
fluxo de gravação verificada. Se a identificação for inconclusiva, só gere o HEX.

## Redes e parâmetros

| Papel | Campos | Padrões |
|---|---|---|
| Central | Rede | 42 |
| Estação | Rede, ID, Nome | 42, QUARTO, Quarto |
| Ponte | Rede | 42 |

A rede corresponde a `radio.setGroup()`. Central, Estações e Pontes da rede A
usam, por exemplo, 42; todos os aparelhos da rede B usam 43. O runtime filtra o
grupo antes de entregar os pacotes ao código. A Ponte continua genérica dentro
do próprio grupo. Há **uma Central por grupo**; não foi criado campo Central ID.
Grupos são separação lógica, não criptografia/autenticação nem canais de RF
independentes: redes próximas ainda podem interferir fisicamente.

O gateway/backend atual continua destinado a **uma Central/rede por instância**.
Esta versão não agrega várias Centrais em um mesmo backend; para redes online
independentes, use instâncias/configurações independentes. IDs iguais em redes
diferentes são válidos no rádio, mas não devem ser misturados no mesmo backend.

Não foram expostos potência (7), TTL (12), ACK (2500 ms), cache (192/12 s), fila
(24), bytes/códigos de pacote, baud (115200), leitura do microfone, taxa de SOM,
threshold, refresh ou heartbeat. Esses valores permanecem exatamente nos fontes.

A faixa de grupo foi conferida em `pxt_modules/radio/radio.cpp` do alvo oficial,
na declaração de `setGroup`, e na
[documentação micro:bit](https://support.microbit.org/support/solutions/articles/19000030849-how-to-use-radio-group-codes-with-the-makecode-editor).
A identificação usa os [IDs oficiais de placa V2](https://support.microbit.org/support/solutions/articles/19000035697-what-are-the-usb-vid-pid-numbers-for-micro-bit),
o [DETAILS.TXT](https://support.microbit.org/support/solutions/articles/19000129907-details-txt)
e os [sinais DAPLink de falha](https://tech.microbit.org/software/daplink-interface/).

## Arquitetura e auditoria

- `configurador/model.py`: configuração imutável e validações independentes da GUI.
- `configurador/gui.py` / `__main__.py`: Tkinter; compilação/gravação em worker,
  resultados por fila e atualizações Tk na thread principal. Não trava a tela.
- `configurador/builder.py`: contexto de firmware em `TemporaryDirectory` na pasta
  temporária do sistema operacional. Compartilhado pelos dois fluxos: publicação
  exclusiva do arquivo permanente ou uso direto pelo gravador, seguido de limpeza.
- `configurador/compiler.py`: invoca Node sem shell, verifica versões, timeout de
  cinco minutos, falhas de build e checksum/estrutura Intel HEX universal.
- `tools/compilar_configurado.js`: usa o parser TypeScript que já vem no PXT.
  Localiza o argumento literal de `radio.setGroup` e, na Estação, os inicializadores
  de ID/nome. Substitui apenas esses intervalos sintáticos, escapando strings.
  Estrutura ausente/duplicada/inesperada falha explicitamente. Não usa substituição
  global de texto nem reimprime/reformata o restante do programa.
- `tools/gerar_makecode.js`: a composição já existente foi extraída em função
  reutilizável. O gerador tradicional e `tests/makecode_build.js` seguem funcionando
  e preservam exatamente os bytes produzidos antes.
- `configurador/devices.py`: Win32 enumera unidades removíveis sem letra fixa;
  exige nome MICROBIT, DETAILS.TXT limitado a 8 KiB, DAPLink em Interface, versão
  da interface e Unique ID de V2 conhecido (9903/9904/9905/9906). Antes da cópia,
  revalida letra, serial do volume e Unique ID. Não aceita caminho manual como
  prova de dispositivo. V1, MAINTENANCE, unidade só renomeada e identidade trocada
  são recusados. Essas evidências evitam acidentes, não são autenticação contra
  um dispositivo malicioso que forje todas as informações.

Fluxo: fontes base → composição existente → configuração AST em cópia → projeto
MakeCode temporário → PXT oficial → HEX universal com V2 → validação. A partir daí:

- **Gerar firmware .HEX:** salva no destino escolhido; esse arquivo permanece.
- **Gerar e gravar:** passa o HEX temporário ao gravador, sem publicar uma cópia
  permanente. O contexto só termina após a gravação e a observação de remontagem.

Em ambos os casos, `TemporaryDirectory` remove somente a árvore criada para aquela
operação, inclusive quando compilação, validação ou gravação lança uma exceção.
Não limpa caches compartilhados, dependências, ferramentas, arquivos do projeto,
HEXs permanentes nem arquivos no micro:bit. A cópia de dependências usada pelo
projeto temporário é descartada junto dele; a original permanece intacta.
Encerramento forçado do processo, queda de energia ou bloqueio de arquivos pelo
sistema podem impedir a limpeza. Erros de limpeza não são ocultados; não há uma
varredura automática que apague arquivos de outras operações.

O builder reaproveita `pxt_modules` local quando disponível; também foi compilado
um projeto novo sem essa cópia. Os pacotes npm e cache global já estavam instalados
nesse ensaio: isso não equivale a uma instalação offline do zero. O HEX V2 nativo
é exigido além do universal. O fonte base permanece em `microbit/`, sem três cópias
manuais da configuração/protocolo e sem alterações de comportamento.

Na cópia, erro de E/S deixa resultado não confirmado e não dispara retry automático.
Após copiar, observa ausência/reaparecimento pelo Unique ID e FAIL.TXT/ASSERT.TXT.
Um FAIL preexistente também causa resultado conservador de falha; a ferramenta não
apaga esse arquivo. Desmontagem durante a cópia pode ser flash ou falha: não adivinha.
Sem erro observado, confirma apenas a transferência e presença. Boot correto exige
ensaio físico. Identificação futura desconhecida é recusada até revisão.

## Testes e reprodução

```powershell
python -m unittest discover -s tests -v
node tests/configurador_radio.js
node tests/frontend_test.js
node tests/frontend_online_test.js
node tests/frontend_frames_test.js
node tests/rede_sim.js
node tests/som_picos.js
node tests/radio_carga.js
node tools/gerar_makecode.js --check
```

A suíte nova compila realmente sete configurações e repete uma geração: Central
42/0, Ponte 42/255, QUARTO 42 e SALA 42/43. Compara os três padrões byte a byte com
os HEXs versionados da v0.0.3.1, verifica preservação de todos os arquivos em
`microbit/`, UTF-16, IDs inválidos, checksums, caminhos com espaços e falhas.
Os testes USB usam diretórios/adaptadores simulados e não gravam aparelhos.
A GUI usa Tk real com janela oculta nos testes. Sem PXT instalado, os testes de
compilação são marcados como ignorados explicitamente; nesta validação foram executados.
O ensaio de duas redes modela explicitamente o filtro de grupo do runtime; não
constitui uma medição física de isolamento/interferência.

## Roteiro físico da v0.0.4

1. Gere Central/rede42 e grave um V2. Gere QUARTO/rede42 e SALA/rede42 e grave
   dois outros V2, conferindo a unidade selecionada a cada vez.
2. Gere Ponte/rede42 e grave um quarto aparelho. Teste primeiro sem Ponte, depois
   posicione-a para testar retransmissão. Inicie o gateway normal (`iniciar.bat`).
3. Confira QUARTO/SALA, nomes, ONLINE, SOM/peak-hold e PING pela interface local.
4. Gere uma segunda rede (Central, Estação LAB01 e Ponte, todos rede43).
   Verifique em instâncias locais separadas que LAB01 só chega à Central 43 e
   QUARTO/SALA só à Central 42. Uma Ponte 43 não deve estender a rede 42.
5. Com dois micro:bits USB, confira que é necessário escolher um antes de gravar.
   Sem aparelho, confirme que somente gerar funciona. Se houver falha, preserve
   examine FAIL.TXT e tente novamente após reconectar; não provoque desconexão no
   meio do flash. O fluxo direto não guarda o HEX, inclusive se houver falha.
6. Reconfirme o comportamento de palmas curtas e o fluxo já validado até a Vercel.

Nenhum micro:bit foi gravado nesta execução. Resta validar a detecção em aparelhos
reais, a cópia/remontagem do DAPLink e o boot/radio multi-rede no seu hardware.

## Futuro executável standalone

Ainda não é `.exe` standalone. Será necessário distribuir Python/Tcl/Tk, Node,
alvo PXT e suas dependências/licenças, resolver caches/imagens nativas para operação
offline, testar em Windows limpo sem Git/npm, definir pasta gravável para builds e
cache (fora de Program Files), atualização/versionamento, assinatura do executável
e ensaios de USB em diferentes versões de DAPLink. Nenhum empacotamento foi feito.

Resultados desta execução: **72 testes Python distintos aprovados** (40 anteriores
+ 32 do configurador; suíte completa de 71 e o teste adicional de despacho da GUI
executado em seguida), três scripts frontend, 16 cenários de rádio, 33 cenários de
peak-hold e 25 de carga. Teste adicional de redes configuradas/AST aprovado.
Compilação oficial padrão pelos scripts tradicionais também passou nos três
papéis; `git diff -- microbit` permaneceu vazio. Sintaxe Python/Node, sincronização
dos fontes gerados e `git diff --check` passaram. A primeira tentativa dos testes
Tk no sandbox falhou ao localizar Tcl; todos passaram com Tk real fora dele,
sem alterar testes para esconder essa limitação ambiental.

## Gravação direta temporária — melhoria final da v0.0.4

A GUI não pede destino no fluxo direto. O mesmo contexto de compilação/validação
serve aos dois botões; apenas o botão de exportação publica um arquivo permanente.
O gravador USB existente permanece sem alterações. Testes novos cobrem cinco
configurações consecutivas, ausência de acúmulo, limpeza após compilação/validação/
gravação falhar, desconexão antes da cópia e não reaparecimento depois dela,
permanência do arquivo explicitamente salvo e GUI sem diálogo de destino.
Há compilação PXT real no diretório temporário do sistema com espaços no caminho.

Para o ensaio físico consecutivo:

1. Execute `python -m configurador` e feche o gateway antes de gravar.
2. Conecte o primeiro V2, atualize a lista USB, escolha Estação QUARTO/rede42 e
   clique Gerar e gravar. Confirme o aparelho: nenhum diálogo Salvar deve aparecer.
3. Espere a mensagem final antes de trocar o aparelho. Repita para SALA/rede42,
   Ponte/rede42 e Central/rede42, atualizando a lista após cada troca.
4. Confirme que nenhum HEX permanente surgiu nas suas pastas. Os diretórios
   `microserial firmware *` criados por essas operações em `%TEMP%` devem desaparecer
   quando cada operação terminar normalmente. Não apague caches compartilhados.
5. Use Gerar firmware .HEX uma vez, escolha um destino e confira que esse HEX
   permanece mesmo após outra gravação direta. Um destino já existente é recusado.
6. Reinicie o gateway com a Central e confira SOM, nomes, presença, peak-hold e
   PING local. A mensagem de cópia não substitui essa confirmação física.

Nenhuma gravação física foi realizada nesta etapa. As desconexões foram simuladas;
não retire o cabo durante uma gravação real para reproduzir esses testes.

Regressão após essa melhoria: **82 testes Python passaram em 116,913 s**, incluindo
os 72 anteriores sem alterações e 10 novos. Passaram também os três scripts
frontend, 16 cenários de rádio, 33 de peak-hold, 25 de carga e o teste adicional de
redes configuradas/AST. A suíte compilou oficialmente sete configurações, repetiu
uma geração e compilou QUARTO no fluxo direto temporário: os três padrões seguem
idênticos byte a byte à v0.0.3.1. Checksums, preservação dos fontes, sincronização
MakeCode, sintaxe Python e `git diff --check` passaram. Segurança USB preservada;
nenhum token/.env foi exposto. Sem commit, push, tag ou deploy.
