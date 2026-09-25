# Auditoria integrada — MicroSerial

Atualização da distribuição: os fontes oficiais continuam em `microbit/`. O gerador
`tools/gerar_makecode.js` produz `microbit/makecode/central.ts`, `estacao.ts` e
`ponte.ts`, cada um autocontido. O build oficial foi novamente executado nos três
arquivos completos como único `main.ts` de cada projeto, gerando HEX universal e V2.
Os manifestos agora também registram `makecodeSha256`. A identidade byte a byte do
protocolo incorporado foi conferida; o protocolo e os fontes dos papéis não foram
alterados. Os 16 cenários de rede, 11 testes Python e teste do frontend passaram
novamente sem modificações nos testes existentes. As cópias `firmware/*.ts` são
mantidas automaticamente por compatibilidade; a distribuição principal de código
para colar no editor está em `makecode/`. Consulte as duas opções no README.

Auditoria iniciada com leitura dos componentes antes de editar. A pista de que a ligação direta funcionava foi tratada como evidência, não como diagnóstico. A validação final inclui compilação nativa pelo MakeCode oficial, além das simulações. Nenhum micro:bit físico foi gravado ou testado nesta execução.

## 1. Inventário e arquitetura encontrada

| Componente | Arquivo | Responsabilidade original |
|---|---|---|
| Estação V2 | `microbit/estacao.ts` | Microfone, identificação, nome, status, heartbeat e recepção de ACK |
| Ponte V2 | `microbit/ponte.ts` | Converter `RELAY` em `R`; repetir ACK e RETURN |
| Central V2 | `microbit/central.ts` | Receber rádio, responder heartbeat, escrever mensagens na serial |
| Descoberta/abertura serial | `serial_manager.py` | Escolher porta COM e abrir a 115200 baud |
| Processo principal | `app_radio.py` | Flask/Socket.IO, leitor serial, reconexão e emissão de estado |
| Processamento alternativo | `radio.py` | Segunda implementação de parser → estado, sem emissão Socket.IO |
| Parser | `parser.py`, `utilitarios.py` | Formatos textuais, normalização de ID/nome/som/status |
| Estado e histórico | `estacoes.py`, `estado.py` | Estações individuais, timestamps, intervalos, histórico limitado e lock |
| Timeout | `monitor.py` | Marcar estação offline e publicar alteração |
| HTTP/Socket.IO | `routes/web.py`, `sockets/events.py` | `/`, `/api/data`, estado inicial ao conectar |
| Interface | `templates/index.html` | Cards, som, status, contadores e evento `radio_data` |
| Configuração/documentação | `config.py`, `requirements.txt`, `README.md` | Variáveis de ambiente, dependências e instruções |

Os `__init__.py` apenas organizam os módulos. Não havia testes versionados nesta pasta. A pasta `radio` aparece como não rastreada no repositório pai; também existiam alterações fora dela, que não foram modificadas por esta tarefa. Por isso um `git diff` do repositório não representa sozinho as alterações desta auditoria.

Fluxo original de ida:

```text
Estação → sendString → [Ponte: RELAY → R] → Central
  → serial.writeLine → app_radio.ler_microbit → parser
  → estacoes/estado → Socket.IO radio_data → cards da interface
```

O ACK era gerado na Central, sem participação do PC. O caminho aplicativo/interface → serial → Central → Estação não estava implementado. Existiam apenas atualização e consulta de estado no frontend.

Confirmados no código original: grupo **42**, potência **7**, ID **QUARTO**, som a **500 ms**, heartbeat a **1000 ms**, espera de ACK **1500 ms**, timeout visual do firmware **3000 ms** e timeout de estação no PC **5 s**. Não havia limite explícito de **5 saltos**, identificador de pacote, cache de duplicados ou retransmissão correlacionada por ACK.

## 2. Defeitos originais e causas

| Defeito | Causa e consequência |
|---|---|
| Estação não passa corretamente ao modo Ponte quando perde a Central | Novo heartbeat reinicia o relógio a cada 1000 ms antes de vencer a espera de 1500 ms. A Ponte também ignora o heartbeat direto. |
| Cadeia de Pontes não encaminha a ida | Uma Ponte recebe `RELAY`, transmite `R`; a seguinte só aceita `RELAY`. O encaminhamento para após a primeira Ponte. |
| Loops no retorno | ACK e RETURN são repetidos integralmente, sem ID de pacote, cache ou TTL decrescente. Pontes vizinhas podem realimentar a mesma mensagem. |
| Som desaparece em certos valores | `RELAY|0|S|QUARTO|255` ocupa **20 bytes ASCII**; o código só envia se tiver até 19. Com dois dígitos cabe; com três não. |
| Nome/status não chegam corretamente ao estado | O firmware emite `NOME|ID|nome` e `STATUS|ID|estado`, mas o parser tratava o segundo campo como o próprio nome/status, sem ID. |
| Status excede o pacote | `STATUS|QUARTO|ONLINE` ocupa **20 bytes**, enviado sem checagem. |
| Retorno textual não escala para saltos de dois dígitos | `RETURN|1|ACK|QUARTO` ocupa 19 bytes; com `10`, ocupa 20. A Central suprime o envio acima de 19. Isso não era um limite explícito de cinco saltos. |
| Processamento de rádio atrasado | `basic.showIcon()` sem intervalo explícito utiliza 600 ms; era chamado na recepção, inclusive antes de enviar o ACK. |
| ACK antigo pode confirmar heartbeat novo | ACK contém só o ID da estação, sem token/sequence nem tentativa. |
| Estação falsamente online | ACK/RETURN refletidos passam pela Central e pelo parser como se fossem sinal novo da estação. SOM com valor ausente/inválido também podia ser aceito apenas pelo ID. |
| Perda/atribuição incorreta de metadados | Identificação só no início, sem recuperação após reconexão do PC. O README dizia haver contexto da última estação, mas o atualizador exigia ID e não implementava esse comportamento. |
| Porta errada selecionada | Nome/VID/PID não distinguem Central de Ponte/Estação; havia fallback para o primeiro USB sem handshake. Abrir COM era tratado como Central conectada. |
| Serial parcial/corrompida interpretada | `readline()` pode devolver fragmentos ao vencer timeout; o código interpretava cada fragmento, e `errors="ignore"` podia remover bytes corrompidos. |
| Fluxo de retorno inexistente no PC | Não havia evento/comando de interface, escrita serial nem leitura de comando na Central. |
| Divergência entre processadores Python | `app_radio.py` e `radio.py` tinham processamento duplicado; agora a aplicação usa o processador comum e publica seu resultado. |
| Som exibido incorretamente | A página limitava o valor a **225**, embora a API do microfone retorne **0–255**. |
| Navegador podia continuar indicando conexão | Não havia tratamento de desconexão Socket.IO. |

As falhas são verificáveis no código. Sem medição dos aparelhos originais, não é possível atribuir a cada uma uma porcentagem dos sintomas observados no ambiente real.

## 3. Limitações do micro:bit e escolha do transporte

O projeto declara **micro:bit V2** e a Estação usa o microfone V2. A documentação oficial limita tanto `radio.sendString` quanto `radio.sendBuffer` a **19** caracteres/bytes, respectivamente. O pacote de rádio de baixo nível tem outros cabeçalhos: não se pode tratar os 32 bytes físicos como 32 bytes livres para a aplicação MakeCode.

Foi escolhido `sendBuffer`, mantendo o rádio MakeCode, grupo e potência. Assim um número de som ocupa um byte, o token ocupa quatro, e os textos `RELAY`, `RETURN` e `HEARTBEAT` não competem com os dados. O cabeçalho é compartilhado pelos três papéis em `microbit/protocolo.ts`. Não há seleção de rota direta versus Ponte: o mesmo pacote funciona nos dois casos.

O V2 tem **128 KiB de RAM total**, parte ocupada pelo runtime. O cache possui no máximo **192** chaves e timestamps; a fila tem no máximo **24** buffers de até 19 bytes. O texto das chaves e números/referências soma alguns KiB, e há overhead de strings, arrays, objetos e GC; não se afirma uma medição de heap livre. A fila carrega no máximo 456 bytes de conteúdo, além desse overhead. A compilação nativa validou código/flash; o consumo dinâmico e GC sob tráfego precisam de medição física.

Fontes primárias consultadas:

- [MakeCode: sendString](https://makecode.microbit.org/reference/radio/send-string)
- [MakeCode: sendBuffer](https://makecode.microbit.org/reference/radio/send-buffer)
- [micro:bit: especificações de hardware V2](https://tech.microbit.org/hardware/)
- [MakeCode: showIcon e intervalo padrão](https://makecode.microbit.org/reference/basic/show-icon)
- [MakeCode: soundLevel, V2 e faixa 0–255](https://makecode.microbit.org/reference/input/sound-level)
- Pacotes oficiais instalados: `pxt-microbit@9.1.1` e sua dependência `pxt-core@13.0.1`; o runtime serial foi inspecionado e `serial.readString()` usa leitura assíncrona.

## 4. Formato final dos pacotes de rádio

| Posição | Conteúdo |
|---|---|
| 0 | Nibble alto: versão **1**. Nibble baixo: tipo **1–8** |
| 1 | Nibble alto: tentativa **0–2**. Nibble baixo: TTL restante **0–12** |
| 2–5 | Token **uint32 little-endian** |
| 6 | Comprimento do ID, **2–8** bytes |
| 7 em diante | ID ASCII, caracteres `A-Z`, `0-9`, `_`, `-` |
| Após o ID | Carga do tipo, respeitando máximo total de **19 bytes** |

| Tipo | Valor | Sentido | Carga |
|---|---:|---|---|
| H | 1 | Estação → Central | Vazia: heartbeat |
| S | 2 | Estação → Central | Um byte: som 0–255 |
| I | 3 | Estação → Central | Vazia: identificação |
| N | 4 | Estação → Central | Descritor de fragmento + bytes de nome |
| T | 5 | Estação → Central | Um byte: 0 offline, 1 online |
| A | 6 | Central → Estação | Vazia: ACK do H |
| P | 7 | Central → Estação | Vazia: PING solicitado pelo PC |
| Q | 8 | Estação → Central | Vazia: resposta do PING |

O ID é a origem nos dados de subida e o destinatário em A/P. Em Q ele identifica a estação que respondeu. Não há um ID configurável da Central: a rede pressupõe **uma Central**. Os tipos distinguem os domínios de token de pedidos e respostas.

Para `QUARTO`: H/ACK/PING ocupam **13 bytes**, SOM/STATUS **14 bytes**. Com ID de 8 caracteres, SOM ocupa **16 bytes**. O token não cresce em tamanho quando o contador aumenta.

O nome tem até **24 unidades UTF-16**, preservando acentos. Cada N carrega um byte cujo nibble alto é `total-1` e cujo nibble baixo é o índice; depois vêm até `11 - comprimento_do_ID` bytes UTF-16LE. Todos os fragmentos de uma edição usam o mesmo token, com no máximo 16 partes. Nomes não aceitam controles, `|` ou `:`, que conflitam com a serial textual. ID/nome inválidos produzem `ERRO_CONFIG_ESTACAO` e impedem a transmissão, em vez de truncar silenciosamente.

## 5. Identificação, deduplicação, reinício e TTL

A chave do cache é **tipo + ID + token + tentativa + descritor do fragmento**, sem TTL. Cada Ponte encaminha uma chave uma vez enquanto ela permanecer no cache. A Central também deduplica para impedir que cópias por rotas diferentes multipliquem leituras/histórico. Estações deduplicam PING.

Cada Estação inicia um contador uint32 em posição aleatória e o incrementa em novas mensagens. Um reinício normalmente inicia outra região do espaço de tokens. Em overflow o contador volta a zero de forma definida; os valores anteriores já terão saído do cache em condições normais. Os timers também tratam a volta de `millis()`.

Isso **não é uma garantia criptográfica nem persistente** de unicidade após reinício: um token específico pode coincidir com probabilidade ideal de 1/2³²; a chance de sobrepor uma janela depende da quantidade de tokens ainda retidos e da qualidade do gerador aleatório. IDs duplicados em placas distintas são erro de configuração. O PC usa tokens aleatórios de 32 bits para PING; A/Q repetem o token e a tentativa do pedido.

O cache expira em **12 s** ou elimina a entrada mais antiga ao atingir **192 entradas**. Sob tráfego elevado a retenção efetiva pode ser menor. Tentativas 1/2 entram como novos pacotes de transporte, permitindo recuperação sem esperar o cache expirar. Nomes repetidos em anúncio futuro recebem novo token.

O TTL inicia em **12**, e cada Ponte o reduz em **1**. Um destinatário final aceita TTL **0**, mas uma Ponte não o retransmite. Portanto são permitidas **12 Pontes consecutivas** (13 enlaces físicos); uma cadeia com 13 Pontes é bloqueada. ACK e PING começam com orçamento próprio de 12, independentemente do valor restante na ida.

O valor 12 atende ao exemplo de oito Pontes com margem de quatro. A proteção principal é o cache; o TTL limita tráfego mesmo com reinício de Ponte, descarte por capacidade ou expiração do cache. Não foi uma troca de constante 5 → 10: o encaminhamento foi unificado e passou a ter identidade e deduplicação.

O envio ocorre em fila limitada com espera aleatória de **5–25 ms**, seguida de espaçamento de **5–15 ms**. Isso reduz sincronização entre repetidores, mas não elimina colisões. Em caminho sem congestionamento, 24 retransmissões de ida/volta consomem aproximadamente até 960 ms desses intervalos; a espera de 2500 ms inclui margem de processamento. Não é um limite de latência garantido sob fila cheia ou interferência.

## 6. Heartbeat, ACK, dados e PING

- SOM continua aproximadamente a cada **500 ms**, com jitter de até 40 ms. É telemetria: não há ACK individual nem replay de amostras antigas.
- HEARTBEAT continua aproximadamente a cada **1000 ms**, com jitter de até 100 ms quando a rede responde. Há apenas um heartbeat pendente. Ele espera **2500 ms** e tenta novamente até duas vezes, com o mesmo token e tentativa incrementada. Um ACK só confirma ID, token e tentativa correntes.
- Sem confirmação a Estação continua tentando; o ícone fica offline após **8000 ms** sem ACK. No PC a regra existente permanece: qualquer dado válido de estação renova `last_seen`, e o padrão de timeout é **5 s**. Assim “online” no PC demonstra recepção da subida, enquanto ícone/resultado PING demonstram ida e volta.
- I/T/N são anunciados na inicialização e aproximadamente a cada **30 s**, recuperando nome após reconexão. Nomes incompletos são descartados após 10 s; até 32 montagens simultâneas ficam em memória no PC. Uma parte perdida pode adiar a atualização até o próximo anúncio.
- PING é idempotente e limitado a um comando pendente na Central/PC. São até três tentativas de 2500 ms; o PC espera até 9 s e o navegador até 11 s. Resultados: `OK`, `TIMEOUT`, `BUSY`, `DISCONNECTED` ou ID inválido. Sucesso só é mostrado depois de Q correlacionado.

Não foram criados comandos de atuação física sem especificação. PING fornece o caminho de retorno completo; futuros comandos deverão definir suas próprias regras de execução/repetição.

## 7. Integração final

```text
Estação → H/S/I/N/T → zero ou mais Pontes → Central
  → linhas seriais → app_radio → protocolo_serial/parser
  → radio.py → estacoes.py/estado.py → radio_data + /api/data → página

Botão Testar comunicação → Socket.IO radio_ping → serial_manager.enviar_ping
  → PING|ID|token\n → Central → P → Pontes → Estação
  → Q → Pontes → Central → CMD|ID|token|OK\n
  → leitor serial → pedido pendente → resposta Socket.IO → página
```

O ACK de heartbeat continua local à rede de rádio; não exige PC conectado. A Ponte não lê nem interpreta nomes/estações além de validar o pacote comum e obter sua chave.

A Central anuncia `CENTRAL_ONLINE|1` ao iniciar, ao receber `HELLO` e a cada segundo. A descoberta só sonda candidatos micro:bit ou `MICROSERIAL_PORT` explicitamente configurada, e exige essa assinatura; não abre USB genérico por fallback. Há nova verificação ao abrir a conexão operacional. Após 5 s sem anúncio da Central a conexão é refeita. Isso identifica o papel, não é autenticação contra um dispositivo que imite a assinatura.

A serial usa **115200 baud**, linhas terminadas por LF (CRLF também aceito). Formatos emitidos: `ID|ID`, `HEARTBEAT|ID`, `SOM|ID|0..255`, `STATUS|ID|ONLINE`, `NPART|ID|token|índice|total|hex`, `CMD|ID|token|resultado`. O PC remonta NPART em `NOME|ID|nome`. ACK/RETURN textuais não atualizam mais estações. Formatos legados completos e inequívocos continuam aceitos pelo parser; mensagens parciais sem ID não são atribuídas à última estação.

O novo rádio é **incompatível com os firmwares textuais antigos**. Atualize Central, Estações e todas as Pontes juntas. Aceitar os antigos ACK/RETURN nas Pontes reintroduziria os loops que motivaram a correção.

## 8. Arquivos alterados e adicionados

Alterados: `microbit/central.ts`, `microbit/estacao.ts`, `microbit/ponte.ts`, `app_radio.py`, `radio.py`, `parser.py`, `serial_manager.py`, `sockets/events.py`, `templates/index.html` e `README.md`.

Adicionados: `microbit/protocolo.ts`, `protocolo_serial.py`, `.gitignore`, `AUDITORIA.md`, `tests/rede_sim.js`, `tests/test_integracao.py`, `tests/frontend_test.js`, `tests/makecode_build.js` e os artefatos gerados em `microbit/firmware/` (`.hex`, fonte combinado `.ts` e manifesto `.json` para cada papel).

Preservados: configuração de grupo/potência, microfone/IDs/nome/status, estrutura Flask/Socket.IO, rotas existentes, estado por estação, histórico limitado, locks e monitor de timeout. `config.py`, `estado.py`, `estacoes.py`, `monitor.py`, `utilitarios.py`, `routes/web.py` e `requirements.txt` não precisaram de alteração. As dependências do compilador ficam isoladas e ignoradas em `.makecode-check/`.

## 9. Validação e resultados

**Compilação oficial:** os três papéis foram compilados por `pxt-microbit 9.1.1` / `pxt-core 13.0.1`, produzindo HEX universal e `mbcodal-binary.hex`. Não foi apenas transpilar TypeScript para JavaScript: foram gerados executáveis nativos para o runtime V2. Nenhuma incompatibilidade de API do firmware foi encontrada. O script de build usa o alvo micro:bit multivariante, sem o argumento `--hw mbcodal`, que designaria incorretamente uma extensão de placa.

Os manifestos em `microbit/firmware/` registram hashes SHA-256 do protocolo, papel e HEX. O protocolo copiado nos três projetos de compilação é idêntico ao fonte atual.

SHA-256 compartilhado de `protocolo.ts`: `b7e5f38e44374ca4f89228b7783a6a206296450556ca14edab30215795d753d6`.
Os hashes dos fontes e HEXs foram conferidos, assim como comprimento/checksum de todos os registros HEX não vazios. Linhas vazias presentes no HEX universal oficial foram ignoradas nessa checagem.

| Firmware V2 | Flash reportada pelo compilador | Espaço livre na área utilizável |
|---|---:|---:|
| Central | 307876 bytes (65,4%) | 163164 bytes |
| Estação | 305284 bytes (64,8%) | 165756 bytes |
| Ponte | 302300 bytes (64,2%) | 168740 bytes |

Esses números incluem runtime e programa e não medem o heap ocupado em execução.

**Simulação:** 16 cenários passaram executando o TypeScript real em VMs independentes com APIs de micro:bit simuladas. Há tempo virtual, filas, topologia, duplicatas e perda seletiva de mensagens, mas não há física de RF nem simulação fiel do escalonador CODAL/GC.

**Python/integração:** 11 testes passaram. Incluem linhas produzidas pelos firmwares TypeScript através de oito Pontes, leitura byte a byte, remontagem de nomes, parser, estado, HTTP e cliente de teste Socket.IO. Incluem PING correlacionado, timeout/busy, erros seriais, descoberta, desconexão e recuperação de estações.

**Frontend:** teste do JavaScript real da página passou, com DOM simulado: cards, eventos, som 250/255, escape HTML, clique PING e desconexão. Não substitui teste visual e Socket.IO real no navegador.

**Sintaxe Python:** compilação dos módulos por `compileall` aprovada.

| Cenário solicitado | Cobertura |
|---|---|
| 1–2: Estação/Central diretas, nos dois sentidos | VM: heartbeat/ACK, SOM e PING/Q |
| 3–4: uma Ponte, nos dois sentidos | VM: dados, ACK, PING/Q |
| 5–6: várias Pontes, nos dois sentidos | VM: 8 e 12 Pontes; 13 bloqueadas com timeout |
| 7: múltiplas Estações | VM: QUARTO/COZINHA simultâneas; Python: isolamento de estado |
| 8: duplicado na mesma Ponte | VM: 20 cópias, um encaminhamento |
| 9: ciclo entre Pontes | VM: triângulo com retorno pelas arestas, tráfego termina |
| 10: ACK em múltiplas Pontes | VM: 8/12 Pontes; perda inicial de ACK e nova tentativa |
| 11: heartbeat pela rede | VM: confirmação e expiração de espera sem sobrescrita |
| 12: Ponte reinicia | VM: reinício de uma Ponte no caminho e recuperação |
| 13: Estação reinicia | VM: novo token e recuperação; Python: offline/online |
| 14: inválidos/incompletos | VM e Python: tamanho, versão, tipo, TTL, ID, som, fragmentos e serial |
| 15: Central ↔ Python | Serial simulada; parser real; assinatura, linhas parciais, comandos, fechamento |
| 16: propagação ao frontend | HTTP e Socket.IO de teste + JavaScript real com DOM simulado |

Adicionais: resposta PING perdida, ACK antigo/refletido, cache expirado/cheio, fila cheia, overflow de token e `millis()`, nome máximo de 24 unidades e todos os pacotes com até 19 bytes.

## 10. Limitações e ensaios físicos obrigatórios

A rede usa inundação controlada, não roteamento. Cada pacote válido atravessa as Pontes alcançadas, inclusive ramos que não levam ao destino. O custo cresce com estações e repetidores; 192 entradas não garantem 12 s de retenção sob qualquer carga. Se o cache eliminar chaves cedo, o TTL continua limitando cada linhagem de encaminhamento, mas duplicações adicionais são possíveis. A primeira cópia recebida pode ter usado um caminho mais longo que o caminho mínimo. Não há garantia de entrega em malha arbitrária, interferência contínua ou filas saturadas.

SOM e metadados são melhor esforço; heartbeat/PING têm repetição limitada. O grupo de rádio não autentica nem cifra pacotes. Uma Central, IDs de Estação únicos e firmware compatível em toda a rede são pressupostos. O frontend ainda depende do carregamento da biblioteca Socket.IO do CDN existente. O timeout do monitor Python continua baseado no relógio de sistema e pode ser afetado por saltos nesse relógio.

Antes de considerar a implantação validada, executar nos aparelhos V2:

1. Gravar e testar Estação/Central diretamente, confirmando som, nome, status, ícone e PING.
2. Testar uma Ponte e então cadeias reais de 8 e 12; garantir que endpoints e Pontes não estejam se ouvindo por atalhos. Apenas colocá-los na mesma mesa não testa multissaltos.
3. Repetir com duas ou mais Estações e com caminhos redundantes/cíclicos; medir perda, latência de ACK/PING e tráfego, inclusive ao ligar todas juntas.
4. Remover/religar uma Ponte no meio; reiniciar Estação e Central; desligar e reconectar USB/PC. Confirmar timeout, redescoberta da Central correta e recuperação do nome em até um novo anúncio bem-sucedido.
5. Manter uma estação fora de alcance e confirmar PING TIMEOUT, sem sucesso causado por ACK refletido. Verificar também quando só um dos sentidos funciona.
6. Medir comportamento sob interferência de 2,4 GHz, distância, paredes, alimentação baixa e fila/cache sob carga. Ajustar intervalos/capacidade apenas com essas medições; não prometer escala ilimitada.
7. Fazer ensaio prolongado para RAM/GC, estabilidade CODAL e consumo; os números de RAM são orçamento, não medição em aparelho.
8. Validar no navegador real o botão, timeout, atualização e reconexão; confirmar dependência do CDN no ambiente de uso.

As instruções exatas de gravação e recompilação estão no [README](README.md). Compilação aprovada demonstra que os fontes podem gerar firmware MakeCode V2; não demonstra que a rede física cumpre as metas de alcance e confiabilidade.
