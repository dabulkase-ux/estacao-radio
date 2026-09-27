// ARQUIVO GERADO AUTOMATICAMENTE — NÃO MANTER CÓPIAS MANUAIS.
// Fontes oficiais: microbit/protocolo.ts + microbit/estacao.ts
// Regenerar: node tools/gerar_makecode.js
// MAKECODE: copie TODO este arquivo para JavaScript. O protocolo já está incluído.
// Comentários dos fontes sobre adicionar protocolo.ts não se aplicam a este arquivo completo.
// NOVA ESTAÇÃO: procure CONFIGURAÇÃO DA ESTAÇÃO abaixo e altere ID_ESTACAO e NOME_ESTACAO.
// Adicione a CADA projeto MakeCode junto de UM papel (central/estacao/ponte).
// V1: <=19 bytes; versão/tipo, tentativa/TTL, token uint32 LE, tamanho ID, ID, carga.
namespace Rede {
    export const H = 1
    export const S = 2
    export const I = 3
    export const N = 4
    export const T = 5
    export const A = 6
    export const P = 7
    export const Q = 8
    export const TTL = 12
    export const ESPERA_ACK = 2500
    export const CACHE_MS = 12000
    const CACHE_MAX = 192
    const FILA_MAX = 24
    let contador = randint(0, 65535) * 65536 + randint(0, 65535)
    let vistos: string[] = []
    let tempos: number[] = []
    let fila: Buffer[] = []
    let prazos: number[] = []

    export function decorrido(antes: number): number {
        return (control.millis() - antes + 4294967296) % 4294967296
    }
    export function venceu(prazo: number): boolean {
        return (control.millis() - prazo + 4294967296) % 4294967296 < 2147483648
    }

    export function idValido(id: string): boolean {
        if (id.length < 2 || id.length > 8) return false
        for (let i = 0; i < id.length; i++) {
            if ("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-".indexOf(id.charAt(i)) < 0) return false
        }
        return true
    }
    export function novoToken(): number {
        contador = (contador + 1) % 4294967296
        return contador
    }
    export function tipo(p: Buffer): number { return p[0] & 15 }
    export function ttl(p: Buffer): number { return p[1] & 15 }
    export function tentativa(p: Buffer): number { return p[1] >> 4 }
    export function token(p: Buffer): number { return p.getNumber(NumberFormat.UInt32LE, 2) }
    export function id(p: Buffer): string {
        let s = ""
        for (let i = 0; i < p[6]; i++) s += String.fromCharCode(p[7 + i])
        return s
    }
    export function carga(p: Buffer): Buffer { return p.slice(7 + p[6]) }
    export function valido(p: Buffer): boolean {
        if (p.length < 9 || p.length > 19 || (p[0] >> 4) != 1) return false
        if (ttl(p) > TTL || tentativa(p) > 2 || p[6] < 2 || p[6] > 8 || 7 + p[6] > p.length) return false
        if (!idValido(id(p))) return false
        let t = tipo(p)
        let c = carga(p)
        if (t == S) return c.length == 1
        if (t == T) return c.length == 1 && c[0] <= 1
        if (t == N) return c.length >= 2 && (c[0] & 15) <= (c[0] >> 4)
        return (t == H || t == I || t == A || t == P || t == Q) && c.length == 0
    }
    export function pacote(t: number, id: string, tok: number, c: Buffer, vez: number = 0): Buffer {
        let p = pins.createBuffer(7 + id.length + c.length)
        p[0] = 16 + t
        p[1] = vez * 16 + TTL
        p.setNumber(NumberFormat.UInt32LE, 2, tok)
        p[6] = id.length
        for (let i = 0; i < id.length; i++) p[7 + i] = id.charCodeAt(i)
        for (let i = 0; i < c.length; i++) p[7 + id.length + i] = c[i]
        return p
    }
    // TTL não identifica o pacote. Tipo separa pedido/resposta; tentativa
    // permite nova inundação; fragmento separa as partes do nome.
    function chave(p: Buffer): string {
        return "" + tipo(p) + ":" + id(p) + ":" + token(p) + ":" + tentativa(p) + ":" + (tipo(p) == N ? carga(p)[0] : 0)
    }
    export function aceitar(p: Buffer): boolean {
        if (!valido(p)) return false
        let agora = control.millis()
        while (tempos.length > 0 && decorrido(tempos[0]) >= CACHE_MS) {
            tempos.shift()
            vistos.shift()
        }
        let k = chave(p)
        if (vistos.indexOf(k) >= 0) return false
        if (vistos.length >= CACHE_MAX) {
            vistos.shift()
            tempos.shift()
        }
        vistos.push(k)
        tempos.push(agora)
        return true
    }
    export function enviar(p: Buffer): boolean {
        if (!valido(p) || fila.length >= FILA_MAX) return false
        fila.push(p)
        prazos.push(control.millis() + randint(5, 25))
        return true
    }
    export function repetir(p: Buffer) {
        if (!valido(p) || ttl(p) == 0 || fila.length >= FILA_MAX) return
        if (!aceitar(p)) return
        let copia = p.slice(0)
        copia[1] -= 1
        enviar(copia)
    }
    export function iniciar() {
        radio.setGroup(42)
        radio.setTransmitPower(7)
        basic.forever(function () {
            if (fila.length > 0 && venceu(prazos[0])) {
                let p = fila.shift()
                prazos.shift()
                radio.sendBuffer(p)
                basic.pause(randint(5, 15))
            }
            basic.pause(1)
        })
    }
}

// ==================== CONFIGURAÇÃO DA ESTAÇÃO ====================
// Altere ID_ESTACAO logo abaixo: ID único, 2–8 caracteres A-Z/0-9/_/-.
// Exemplo: ID_ESTACAO = "COZINHA"; NOME_ESTACAO = "Cozinha".
// Não é necessário alterar o protocolo acima.
// MICRO:BIT V2 — ESTAÇÃO. Adicione também protocolo.ts ao MakeCode.
let ID_ESTACAO = "QUARTO" // Único; 2..8 ASCII A-Z/0-9/_/-.
let NOME_ESTACAO = "Quarto" // Até 24 unidades UTF-16, fragmentado sem truncar.
let INTERVALO_SOM = 200 // Limite: até 5 envios/s, mais jitter; não é taxa de heartbeat.
let REFRESH_SOM = 1000
let MUDANCA_SOM = 3 // Escala 0..255: suprime pequenas oscilações/repetições.
let ultimoSomEnviado = -1
let ultimoEnvioSom = 0
let proximaLeituraSom = 0
let picoSom = -1 // Máximo capturado desde o último envio/comparação sem mudança.
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
            picoSom = Math.max(picoSom, valor)
            proximaLeituraSom = agora + 20
            if (Rede.venceu(proximoSom) && (ultimoSomEnviado < 0 || Math.abs(picoSom - ultimoSomEnviado) >= MUDANCA_SOM || Rede.decorrido(ultimoEnvioSom) >= REFRESH_SOM)) {
                let som = pins.createBuffer(1)
                som[0] = picoSom
                if (Rede.enviar(Rede.pacote(Rede.S, ID_ESTACAO, Rede.novoToken(), som))) {
                    ultimoSomEnviado = picoSom
                    ultimoEnvioSom = agora
                    picoSom = -1
                }
                // Fila cheia: conserva o pico, mas respeita o mesmo limite de tentativas.
                proximoSom = agora + INTERVALO_SOM + randint(0, 20)
            } else if (Rede.venceu(proximoSom)) {
                // Pico já representado (delta < 3): não o prende até o refresh.
                // A próxima leitura pode informar a queda ou capturar outro evento.
                picoSom = -1
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
