# Latência — otimização após v0.0.2

Checkpoint preservado: commit `536afe1` (v0.0.2). Sem commit, tag, push ou deploy
nesta etapa. O estado físico/internet funcional foi informado pelo usuário; não
foi medido com aparelhos nesta execução. Benchmarks registrados em 26/09/2026;
validação final e repetição HTTP em 27/09/2026.

## Diagnóstico e mapa do caminho

O relato de ~300 ms não era uma medição instrumentada. Não o trate como baseline
comprovado. O código acumulava uma leitura espaçada, filas de rádio, um tick remoto
de 1 s e animação da barra. SOM **já não usava ACK/retry**; removê-los não daria ganho.

| Trecho | Antes (configurado) | Depois (configurado) | O que sabemos / não sabemos |
|---|---|---|---|
| Microfone → `soundLevel()` | Consulta a cada 500–540 ms | Prazo de leitura 20 ms | A API lê `levelSPL->getValue()`; o filtro/ADC interno não foi medido |
| Loop da Estação | `pause(10)` + runtime | Igual | `core/codal.cpp` oficial adiciona `fiber_sleep(20)` ao `forever`: cerca de 30 ms/iteração sem outras cargas |
| Decisão de SOM | Sempre envia cada leitura | Mudança ≥3/255, prazo mínimo 200–220 ms, refresh 1000 ms | Se já liberado, próxima leitura pode enviar; sob mudanças contínuas, espera o limite. Oscilações menores só aparecem no refresh |
| Fila Estação → rádio | Jitter 5–25 ms; FIFO 24 | Igual | Loop de transmissão pausa 5–15 + 1 + 20 ms após TX; tempos reais também dependem de CODAL/GC |
| Cada Ponte | Mesmo jitter/FIFO, dedup/TTL | Igual | Em carga, espera de fila soma ao percurso. Não é só tempo de propagação RF |
| Central rádio → serial | Callback imediato, `showIcon(...,0)`, `writeLine` | Igual | Sem debounce de SOM nem espera por ACK. Escrita pode bloquear se UART saturar |
| Serial 115200 → Python | `readline`, timeout 500 ms | Igual | Linha completa termina no `\n`; 500 ms é timeout de leitura incompleta, não atraso obrigatório por linha |
| Parser/estado → aviso remoto | Emissão local, cópia de histórico | Aviso por `Event`; snapshot remoto copia só whitelist | Parser e estado preservados; lock não cobre operação HTTP. Histórico local continua limitado a 100, não vai à internet |
| Gateway → HTTP | POST, depois espera 1000 ms; conexão fechada por urllib | Evento desperta envio; ≥100 ms entre resposta e próximo POST; refresh ocioso 1 s | Uma requisição em voo, uma notificação pendente. RTT lento reduz taxa automaticamente |
| HTTPS/internet | TCP/TLS em cada POST | Conexão reutilizada se servidor permitir | RTT, DNS, TLS, cold start e rede pública não foram medidos |
| Backend → Socket.IO | `emit` dentro do POST | Igual; diagnóstico opcional | Timer de 1 s do monitor não retém atualizações: serve para expiração/presença |
| Socket.IO → DOM | Reconstrói cards imediatamente a cada evento | Último estado por `requestAnimationFrame` | Aproximadamente até um frame (16,7 ms a 60 Hz) mais DOM; abas em segundo plano podem suspender frames |
| Barra visual | CSS `width 0.25s ease` | Sem essa transição | Não atrasava o número textual; só a barra. Como o DOM era reconstruído, o efeito exato variava |

Outros timers preservados: heartbeat 1000–1100 ms; ACK 2500 ms e até três
tentativas; identificação/nome/status ~30 s, fragmentos separados por 100 ms;
presença local de estação 5 s com monitor 1 s; gateway remoto 10 s; assinatura da
Central a cada 1 s, desconexão serial após 5 s sem assinatura; reconexão serial 2 s.
Os timeouts de PING (9/11 s) não entram no caminho normal de SOM.

## Por que esta taxa de rádio

Formato V1, limite de 19 bytes, grupo 42, potência 7, TTL 12, cache de 192 IDs/12 s
e fila de 24 permanecem idênticos. H/A/P/Q mantêm as garantias atuais. I/T/N já eram
melhor esforço com reanúncio periódico — não foi acrescentado nem removido ACK.

O limite relevante não é só a taxa bruta do transceptor: o loop de TX tem cerca de
31 ms por transmissão em carga (5–15 + 1 + 20), aproximadamente 32 pacotes/s por
nó antes de custos extras. Quatro estações com ~4,5 SOM/s e H/A consomem perto de
26 encaminhamentos/s por Ponte, mais metadados/PING. Já 8–10 SOM/s por estação
ultrapassam essa margem. Isso foi confirmado no teste de estresse abaixo.

Por isso o padrão é **até 5 SOM/s**, na prática ~4,4–4,6/s no modelo com jitter e
escalonamento. Constante: ~1 SOM/s. Histerese absoluta de 3/255 reduz ruído pequeno,
e refresh evita que um valor estável desapareça. Não é adaptação automática por
congestionamento; número de nós/interferência ainda exigem ajuste físico.

Não há fila de leituras na Estação. Se o envio falha por fila cheia, a próxima
tentativa lê um valor novo. Pacotes já aceitos nas FIFOs dos relays **não são
substituídos**; podem envelhecer/reordenar sob carga. Preservamos esse mecanismo
para não alterar o protocolo estável. No PC/browser, intermediários são coalescidos.

O cache pode reter menos de 12 s em redes carregadas; o TTL continua protegendo,
mas não garante malhas ilimitadas. O limite de 64 estações no backend não é uma
capacidade prometida para rádio. A configuração padrão foi simulada com até 4.

Referências: [MakeCode sendBuffer: máximo 19 bytes](https://makecode.microbit.org/reference/radio/send-buffer),
runtime do alvo compilado `pxt-microbit 9.1.1` (`core/codal.cpp`, `microphone.cpp`).
As simulações não substituem medição do canal compartilhado de 2,4 GHz.

## Serial: não é o gargalo demonstrado

`SOM|QUARTO|255\r\n` ocupa 16 bytes. Em 8N1, 115200 baud oferece aproximadamente
11520 bytes/s: essa linha ocupa 1,39 ms de fio. Quatro estações a 5 Hz consomem
320 bytes/s de SOM, ~2,8% da capacidade, mais heartbeat/metadados. Mesmo oito
estações ficam em ~5,6% para SOM. Não há evidência para aumentar baud. Latência
do driver USB e buffers do hardware ainda precisam ser medidas.

## Resultados HTTP medidos no Windows (loopback)

Compara o publicador real extraído de `536afe1` com o atual, servidor HTTP/1.1 real,
token fictício, sem `.env` e sem internet. Saída: `benchmarks/latencia-http.json`.

| Cenário | v0.0.2 | Atual |
|---|---:|---:|
| 6 mudanças isoladas, mediana alteração → recepção HTTP | 623,70 ms | 1,32 ms |
| Mesmo cenário, máximo | 956,71 ms | 57,00 ms |
| Conexões TCP para 7 publicações | 7 | 1 |
| 8 estações, 200 mudanças a 100 Hz: publicações | 4 | 21 |
| Nesse teste, máximo de idade da amostra entregue | 838,14 ms | 28,76 ms |
| Resposta atrasada 250 ms, 200 mudanças: publicações | 3 | 8 |
| Mesmo teste lento, máximo de idade da amostra entregue | 345,52 ms | 361,21 ms |

Todos terminaram exibindo a amostra 200. O teste lento não melhora todos os máximos:
uma requisição em voo não pode ser cancelada retroativamente; a próxima lê o
estado atual. O limite evita paralelismo/fila crescente, não apaga o RTT.

No teste rápido de carga, memória Python de pico rastreada pelo `tracemalloc` foi
52 KiB antes / 48 KiB depois; CPU do processo 0,031 s / 0,016 s. São medidas curtas,
incluem o servidor/instrumentação e têm resolução insuficiente para prometer
consumo em produção. Casos com CPU 0,000 significam abaixo da resolução, não custo
zero. Não medimos heap/CPU física dos micro:bits.

As mudanças isoladas foram inseridas em fases diferentes do intervalo anterior.
Na carga, a idade mede só amostras realmente entregues: não confundir pequena
idade das selecionadas com entrega de todas as 200. Descartar intermediários é
intencional; comandos continuam no caminho próprio, sem essa coalescência.

`urllib.request` usa `Connection: close`; o cliente atual usa `http.client`,
mantendo validação TLS padrão, destino fixo e rejeição de redirects. Não adiciona
dependências nem canal WebSocket de escrita. Não implementa proxy corporativo
HTTP via variáveis de ambiente. [urllib oficial](https://docs.python.org/3/library/urllib.request.html),
[http.client oficial](https://docs.python.org/3/library/http.client.html).

## Resultados de rádio simulados

Executa TypeScript real do checkpoint/atual com o mesmo protocolo. Modelo inclui
o custo conhecido de 20 ms do `forever`, tempo virtual em passos de 1 ms e 1 ms
por entrega de rádio. Não modela colisões reais, filas internas do driver, áudio,
GC ou escalonador completo. Os 16 testes anteriores mantêm seu modelo original.

Degraus de 20 unidades a cada 1 s, após aquecimento, p95 mudança → serial da Central:

| Pontes | 1 Estação antes/depois | 4 Estações antes/depois |
|---:|---:|---:|
| 0 | 560 / 51 ms | 546 / 57 ms |
| 1 | 569 / 104 ms | 563 / 167 ms |
| 8 | 737 / 306 ms | 818 / 431 ms |
| 12 | 815 / 427 ms | 973 / 544 ms |

São poucas amostras e uma semente determinística, não percentis de campo.
Não somar medianas/p95 desta tabela às do HTTP como se fossem medição ponta a ponta.
Dados completos: `benchmarks/latencia-radio.txt`.

- Valor constante, 4 estações/8 Pontes/10 s: SOM enviado cai de **76 para 40**.
- Mudanças a cada 40 ms, 4 estações, padrão 200 ms: **177–180 SOM enviados/10 s**;
  máximo observado de fila **13/24**; todos os cinco PINGs concluíram nos cenários
  com 0/1/8/12 Pontes. Valores intermediários não são todos enviados.
- Experimento com intervalo **100 ms**, 4 estações/8 Pontes: fila **24/24**, p95
  **1567 ms**, apenas **2/5 PINGs** concluíram na janela. **Não é o padrão entregue.**
- Perda seletiva de aproximadamente 1 em 10 entregas de SOM por aresta, 8 Pontes:
  40 enviados, 11 recebidos, 5/5 PINGs (perda aplicada só a SOM). Mostra o efeito
  acumulado de perda multissaltos; não garante comandos sob perda generalizada.
- Cópias duplicadas e caminho redundante: deduplicação/TTL preservados; 5/5 PINGs,
  fila máxima 13. Os testes antigos também cobrem ciclos, perda de ACK, reboot,
  overflow e fila cheia.

Diferenças entre enviados/recebidos no fim da janela também incluem pacotes em
trânsito; não atribuímos toda diferença a perda. Na malha redundante há caminho
mais curto: seu p95 não é comparável ao de uma cadeia estrita.

## Instrumentação e teste físico curto

1. Atualize o PC com estes arquivos e regrave as Estações. Preserve IDs únicos.
   Sem publicar o frontend novo, a otimização de frames/CSS ainda não estará na Vercel.
2. Opcionalmente acrescente **somente** `MICROSERIAL_LATENCY_DEBUG=1` ao seu `.env`
   local e inicie normalmente. Nenhum token é registrado. Remova a opção depois.
   Há medidas de linha serial completa → parser/notificação/emit local e RTT POST.
3. No Render, a mesma variável opcional habilita POST recebido → emit. A medição
   não inclui recebimento completo do corpo antes da entrada da rota nem transporte
   até o cliente. Esse ajuste/deploy é manual, não foi executado aqui.
4. No browser, acrescente `?diagnostico=1` à URL. Console mostra evento → DOM e
   transporte efetivo (`websocket`, `polling` ou fallback HTTP). Use aba visível.
5. Filme a 120/240 fps uma fonte sonora intermitente com indicador visual e a tela
   do navegador. Use um segundo aparelho como fonte, longe do microfone do PC.
   Conte frames do estímulo até a mudança numérica. Faça ≥30 repetições espaçadas
   por ~2 s; registre mediana/p95, rede, navegador e quantidade de relays.
6. Repita: direto, 1 Ponte, 8 Pontes (sem atalhos RF), 1/4 estações, som constante,
   mudanças rápidas. Compare interface local e pública para isolar internet.
   Execute PING local durante a carga e desligue/religue gateway/Estação/Ponte.
7. Observe expiração 5 s de estação / 10 s de gateway, reconexão e ausência de
   replay crescente. Após estabilizar a fonte, o valor mais recente deve prevalecer.

Relógios PC/Render/browser/micro:bit não são sincronizados: não subtraímos seus
timestamps para alegar latência unidirecional. RTT HTTP inclui ida, processamento
e volta; PING local mede ida/volta do rádio com serial. Rádio → serial absoluto
exige instrumentação física adicional (pinos/analisador ou vídeo); não aumentamos
os pacotes permanentemente para isso. Logs de diagnóstico são opt-in e podem
alterar o desempenho; para o ensaio visual final, repita com eles desligados.

## Compatibilidade, compilação e limites

- Central e Pontes: **não precisam ser regravadas**. Fontes, protocolo e HEXs
  resultantes são idênticos ao checkpoint após recompilação.
- Estações: regrave `microbit/firmware/estacao.hex` (ID padrão QUARTO). Para outras
  unidades, ajuste ID/nome no fonte oficial e gere/compile conforme README, ou use
  `microbit/makecode/estacao.ts` completo no MakeCode V2. Não duplique IDs.
- Compilados todos os três papéis com `pxt-microbit 9.1.1` / `pxt-core 13.0.1`,
  HEX universal + V2. Protocolo SHA-256 compartilhado permanece
  `b7e5f38e44374ca4f89228b7783a6a206296450556ca14edab30215795d753d6`.
- `makecode/estacao.ts`, `firmware/estacao.ts`, HEX e manifesto foram regenerados.
  Misturar Estação anterior/nova preserva formato V1; a antiga apenas continua lenta.
- Mudanças grandes após silêncio, direto e internet rápida, podem ficar muito
  responsivas; **<50 ms ponta a ponta não é garantido**. Em carga contínua há limite
  de ~5 Hz; em 8/12 Pontes o próprio percurso já alcança centenas de ms no modelo.
- Render frio/reiniciando, Wi-Fi, TLS, browser em segundo plano e filas Socket.IO
  de espectadores lentos continuam fora do controle desse limite de publicação.
  Não foi acrescentado controle individual de backpressure para milhares de viewers.
- Durante HTTP lento, o `age` representa a idade na captura no PC, não inclui o
  trânsito desconhecido; presença pode atrasar pelo tempo em trânsito. Timeouts
  existentes continuam iguais. Use apenas um gateway ativo por backend.

## Reprodução e revisão

```powershell
python -m unittest discover -s tests -v
node tests/frontend_test.js
node tests/frontend_online_test.js
node tests/frontend_frames_test.js
node --disable-warning=ExperimentalWarning tests/rede_sim.js
node --disable-warning=ExperimentalWarning tests/radio_carga.js
python tools/benchmark_latencia.py
node tools/gerar_makecode.js --check
node tests/makecode_build.js central
node tests/makecode_build.js estacao
node tests/makecode_build.js ponte
```

40 testes Python (33 existentes + 7), 3 scripts frontend e 16 cenários de regressão
RF passaram. Foram executados 25 cenários adicionais de carga/comparação, incluindo
o experimento de 100 ms que demonstra saturação e justifica não usar essa taxa.
O teste final adicional interrompe uma conexão TCP real e recria o publicador;
as próximas publicações contêm o valor atual (1 → 99 → 100), sem replay intermediário.
Hashes dos manifestos e checksums/comprimento dos registros Intel HEX foram
conferidos; build estático, sintaxe Python e `git diff --check` passaram.
A repetição HTTP está em `benchmarks/latencia-http-confirmacao.json`; a tabela
numérica acima permanece vinculada à primeira execução, sem selecionar o melhor resultado.
Apenas o suporte do
simulador foi estendido para injetar o fonte antigo e custo do runtime/exportar
classes; as expectativas dos 16 cenários antigos não foram alteradas.
O frontend de carga prova 200 eventos → um render do mais recente e invalidação
de frame pendente na desconexão, com DOM simulado, não benchmark visual real.

Nenhum `.env` foi lido/exposto, nenhum token real aparece nos benchmarks; só tokens
fictícios de teste. Launcher, `.bat`, configuração privada e dependências funcionais
foram preservados. Sem banco, histórico online, BLE ou login. Sem ensaio físico,
deploy ou validação de internet pública nesta etapa.

## Correção de picos curtos — 27/09/2026

Confirmada **perda de pico já capturado entre oportunidades de transmissão** na
Estação da v0.0.3 (fonte `aae05ec`). A leitura ocorria aproximadamente a cada 30 ms
no modelo do runtime, mas somente o valor lido na oportunidade de envio era usado.
Um pulso de 30/60/100/150 ms inteiramente dentro da espera de 200 ms podia ser lido
e depois substituído pelo silêncio. Os quatro casos foram reproduzidos no fonte
anterior pelo novo `node --disable-warning=ExperimentalWarning tests/som_picos.js`.

Agora um único acumulador mantém o máximo das leituras. Na oportunidade de envio,
a comparação >= 3/255 e o refresh >= 1000 ms usam esse máximo. Depois de enfileirar
com sucesso, o acumulador é limpo: a próxima janela pode informar a queda. Se a
fila recusar, conserva-se o pico para a próxima tentativa, ainda limitada a
200 ms + jitter 0..20 ms. Não há fila de amostras nem aumento da taxa configurada.
Se o máximo já estiver representado pelo último envio (delta < 3) e o refresh
não venceu, descarta-se esse máximo sem transmitir. Isso evita prender um pico
igual até o refresh e permite que a leitura seguinte informe a queda. Oscilações
menores que 3 continuam intencionalmente suprimidas; o refresh periódico permanece.
O espaçamento é controlado na entrada da fila: jitter/espera do transmissor podem
variar o intervalo observado no ar, como já ocorria antes desta correção.

Validação desta correção:

- **Simulação:** 33 cenários novos: quatro durações em quatro fases, percursos com
  1/8/12 pontes, ruído pequeno, delta exatamente 3, fila recusando envio, pico
  repetido sem prender a queda e máximo entre várias leituras. Todos passaram.
  Há também quatro reproduções da perda no firmware anterior. Os testes conferem
  envio do pico à Central, retorno ao nível baixo e limite de enfileiramento.
- **Regressão:** 40 testes Python (incluindo integração HTTP/Socket.IO loopback,
  servidor lento e reconexão), três scripts frontend e 16 cenários de rádio
  passaram, sem alterar expectativas antigas.
- **Carga simulada:** 25 cenários existentes passaram. Com quatro estações e oito
  pontes, variação a cada 40 ms e limite de envio de 200 ms: 180 pacotes SOM
  transmitidos, 174 recebidos até o fim dos 10 s, fila máxima 13/24 e 5/5 PINGs.
  O experimento não adotado de 100 ms continua saturando: fila 24/24 e 2/5 PINGs.
  Portanto permanece o limite de 5 envios/s. Essas contagens não modelam colisões
  físicas; pacotes ainda em trânsito ao encerrar também entram na diferença.
- **Compilação real:** Central, Estação e Ponte passaram no compilador oficial
  pxt-microbit 9.1.1 / pxt-core 13.0.1, produzindo HEX universal e runtime V2.
  Fontes autocontidos foram conferidos com `node tools/gerar_makecode.js --check`.
  Somente os artefatos da Estação mudaram; protocolo/Central/Pontes preservados.

Regrave apenas as Estações com `microbit/firmware/estacao.hex` (QUARTO padrão),
ou personalize ID/nome em `microbit/makecode/estacao.ts` e compile no MakeCode V2.
Central e Pontes não precisam ser regravadas.

**Limites:** isto corrige a perda local de um pico observado, não garante entrega
fim a fim. Pulsos entre leituras podem não ser amostrados; rádio SOM continua sem
ACK/retry, e internet lenta pode fazer o gateway coalescer um pico já recebido.
Nenhuma latência física nem melhoria visual na internet pública foi medida nesta
etapa. Para validar: use IDs únicos, compare palmas/pulsos curtos nos registros
SOM da Central e na interface, primeiro direto e depois com pontes/várias estações;
confira pico seguido de queda, PING e presença estáveis. Repita em várias fases
em relação aos envios. Um vídeo com estímulo e tela ajuda a medir a experiência.
Não foram alterados heartbeat, ACK, retries, TTL, deduplicação, parser, gateway,
backend ou frontend. Nenhum segredo foi lido/exposto; sem commit/push/tag/deploy.
