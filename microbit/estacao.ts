// MICRO:BIT V2 — ESTAÇÃO. Adicione também protocolo.ts ao MakeCode.
let ID_ESTACAO = "QUARTO" // Único; 2..8 ASCII A-Z/0-9/_/-.
let NOME_ESTACAO = "Quarto" // Até 24 unidades UTF-16, fragmentado sem truncar.
let INTERVALO_SOM = 200 // Limite: até 5 envios/s, mais jitter; não é taxa de heartbeat.
let REFRESH_SOM = 1000
let MUDANCA_SOM = 3 // Escala 0..255: suprime pequenas oscilações/repetições.
let ultimoSomEnviado = -1
let ultimoEnvioSom = 0
let proximaLeituraSom = 0
let INTERVALO_HEARTBEAT = 1000
let TIMEOUT_COMUNICACAO = 8000
let ultimaConfirmacao = 0
let comunicacaoAtiva = false
let aguardandoAck = false
let tokenHeartbeat = 0
let tentativaHeartbeat = 0
let prazoAck = 0
let proximoHeartbeat = control.millis() + randint(0, 1000)
let proximoSom = control.millis() + randint(0, INTERVALO_SOM)
let proximaIdentificacao = control.millis() + randint(0, 1000)
let parteNome = 0
let tokenNome = 0
let enviandoNome = false
let proximaParte = 0
let configuracaoValida = Rede.idValido(ID_ESTACAO) && NOME_ESTACAO.length > 0 && NOME_ESTACAO.length <= 24
for (let i = 0; i < NOME_ESTACAO.length; i++) {
    if (NOME_ESTACAO.charCodeAt(i) < 32 || "|:".indexOf(NOME_ESTACAO.charAt(i)) >= 0) configuracaoValida = false
}
Rede.iniciar()
basic.showIcon(IconNames.No, 0)
if (!configuracaoValida) serial.writeLine("ERRO_CONFIG_ESTACAO")

radio.onReceivedBuffer(function (p) {
    if (!configuracaoValida || !Rede.valido(p) || Rede.id(p) != ID_ESTACAO) return
    let tipo = Rede.tipo(p)
    if (tipo == Rede.A && aguardandoAck && Rede.token(p) == tokenHeartbeat && Rede.tentativa(p) == tentativaHeartbeat) {
        aguardandoAck = false
        ultimaConfirmacao = control.millis()
        comunicacaoAtiva = true
        basic.showIcon(IconNames.Yes, 0)
    } else if (tipo == Rede.P && Rede.aceitar(p)) {
        Rede.enviar(Rede.pacote(Rede.Q, ID_ESTACAO, Rede.token(p), pins.createBuffer(0), Rede.tentativa(p)))
    }
})
function enviarHeartbeat() {
    Rede.enviar(Rede.pacote(Rede.H, ID_ESTACAO, tokenHeartbeat, pins.createBuffer(0), tentativaHeartbeat))
    prazoAck = control.millis() + Rede.ESPERA_ACK
}
basic.forever(function () {
    let agora = control.millis()
    if (configuracaoValida) {
        if (Rede.venceu(proximaLeituraSom)) {
            let valor = input.soundLevel()
            proximaLeituraSom = agora + 20
            if (Rede.venceu(proximoSom) && (ultimoSomEnviado < 0 || Math.abs(valor - ultimoSomEnviado) >= MUDANCA_SOM || Rede.decorrido(ultimoEnvioSom) >= REFRESH_SOM)) {
                let som = pins.createBuffer(1)
                som[0] = valor
                if (Rede.enviar(Rede.pacote(Rede.S, ID_ESTACAO, Rede.novoToken(), som))) {
                    ultimoSomEnviado = valor
                    ultimoEnvioSom = agora
                }
                // Sem fila de amostras na Estação: a próxima tentativa lê o valor atual.
                proximoSom = agora + INTERVALO_SOM + randint(0, 20)
            }
        }
        if (aguardandoAck && Rede.venceu(prazoAck)) {
            if (tentativaHeartbeat < 2) {
                tentativaHeartbeat += 1
                enviarHeartbeat()
            } else {
                aguardandoAck = false
            }
        }
        if (!aguardandoAck && Rede.venceu(proximoHeartbeat)) {
            tokenHeartbeat = Rede.novoToken()
            tentativaHeartbeat = 0
            aguardandoAck = true
            proximoHeartbeat = agora + INTERVALO_HEARTBEAT + randint(0, 100)
            enviarHeartbeat()
        }
        // Reanuncia após perda/reconexão do PC/Central.
        if (Rede.venceu(proximaIdentificacao) && !enviandoNome) {
            Rede.enviar(Rede.pacote(Rede.I, ID_ESTACAO, Rede.novoToken(), pins.createBuffer(0)))
            let status = pins.createBuffer(1)
            status[0] = 1
            Rede.enviar(Rede.pacote(Rede.T, ID_ESTACAO, Rede.novoToken(), status))
            tokenNome = Rede.novoToken()
            parteNome = 0
            enviandoNome = true
            proximaParte = agora + 100
            proximaIdentificacao = agora + 30000 + randint(0, 1000)
        }
        if (enviandoNome && Rede.venceu(proximaParte)) {
            let capacidade = 11 - ID_ESTACAO.length
            let bytes = NOME_ESTACAO.length * 2
            let total = Math.ceil(bytes / capacidade)
            let inicio = parteNome * capacidade
            let tamanho = Math.min(capacidade, bytes - inicio)
            let c = pins.createBuffer(1 + tamanho)
            c[0] = (total - 1) * 16 + parteNome
            for (let i = 0; i < tamanho; i++) {
                let pos = inicio + i
                let codigo = NOME_ESTACAO.charCodeAt(Math.floor(pos / 2))
                c[i + 1] = pos % 2 == 0 ? codigo & 255 : codigo >> 8
            }
            if (Rede.enviar(Rede.pacote(Rede.N, ID_ESTACAO, tokenNome, c))) parteNome += 1
            if (parteNome >= total) enviandoNome = false
            proximaParte = agora + 100
        }
        if (comunicacaoAtiva && Rede.decorrido(ultimaConfirmacao) > TIMEOUT_COMUNICACAO) {
            comunicacaoAtiva = false
            basic.showIcon(IconNames.No, 0)
        }
    }
    basic.pause(10)
})
