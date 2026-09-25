// ARQUIVO GERADO AUTOMATICAMENTE — NÃO MANTER CÓPIAS MANUAIS.
// Fontes oficiais: microbit/protocolo.ts + microbit/central.ts
// Regenerar: node tools/gerar_makecode.js
// MAKECODE: copie TODO este arquivo para JavaScript. O protocolo já está incluído.
// Comentários dos fontes sobre adicionar protocolo.ts não se aplicam a este arquivo completo.
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

// ==================== PAPEL: CENTRAL ====================
// MICRO:BIT V2 — CENTRAL. Adicione também protocolo.ts ao MakeCode.
Rede.iniciar()
serial.setBaudRate(BaudRate.BaudRate115200)
let ultimaComunicacao = 0
let comunicacaoAtiva = false
let ultimoAviso = 0
let pingId = ""
let pingToken = 0
let pingTentativa = 0
let pingPrazo = 0
let linhaSerial = ""
let descartarLinha = false

function enviarPing() {
    Rede.enviar(Rede.pacote(Rede.P, pingId, pingToken, pins.createBuffer(0), pingTentativa))
    pingPrazo = control.millis() + Rede.ESPERA_ACK
}
function comandoSerial(linha: string) {
    if (linha == "HELLO") {
        serial.writeLine("CENTRAL_ONLINE|1")
        return
    }
    let partes = linha.split("|")
    if (partes.length != 3 || partes[0] != "PING" || !Rede.idValido(partes[1])) return
    let tok = parseInt(partes[2])
    if (isNaN(tok) || tok < 0 || tok > 4294967295 || "" + tok != partes[2]) return
    if (pingId != "") {
        serial.writeLine("CMD|" + partes[1] + "|" + tok + "|BUSY")
        return
    }
    pingId = partes[1]
    pingToken = tok
    pingTentativa = 0
    enviarPing()
}
radio.onReceivedBuffer(function (p) {
    if (!Rede.valido(p)) return
    let t = Rede.tipo(p)
    // ACK refletido da própria Central não comprova vida da estação.
    if (t == Rede.A || t == Rede.P || !Rede.aceitar(p)) return
    let id = Rede.id(p)
    let tok = Rede.token(p)
    let c = Rede.carga(p)
    ultimaComunicacao = control.millis()
    comunicacaoAtiva = true
    basic.showIcon(IconNames.Yes, 0)
    if (t == Rede.H) {
        Rede.enviar(Rede.pacote(Rede.A, id, tok, pins.createBuffer(0), Rede.tentativa(p)))
        serial.writeLine("HEARTBEAT|" + id)
    } else if (t == Rede.S) {
        serial.writeLine("SOM|" + id + "|" + c[0])
    } else if (t == Rede.I) {
        serial.writeLine("ID|" + id)
    } else if (t == Rede.T) {
        serial.writeLine("STATUS|" + id + "|" + (c[0] == 1 ? "ONLINE" : "OFFLINE"))
    } else if (t == Rede.N) {
        serial.writeLine("NPART|" + id + "|" + tok + "|" + (c[0] & 15) + "|" + ((c[0] >> 4) + 1) + "|" + c.slice(1).toHex())
    } else if (t == Rede.Q && id == pingId && tok == pingToken && Rede.tentativa(p) == pingTentativa) {
        serial.writeLine("CMD|" + id + "|" + tok + "|OK")
        pingId = ""
    }
})
basic.showIcon(IconNames.No, 0)
serial.writeLine("CENTRAL_ONLINE|1")
basic.forever(function () {
    let entrada = serial.readString()
    for (let i = 0; i < entrada.length; i++) {
        let ch = entrada.charAt(i)
        if (ch == "\n") {
            if (!descartarLinha) comandoSerial(linhaSerial)
            linhaSerial = ""
            descartarLinha = false
        } else if (ch != "\r" && !descartarLinha) {
            linhaSerial += ch
            if (linhaSerial.length > 48) {
                linhaSerial = ""
                descartarLinha = true
            }
        }
    }
    let agora = control.millis()
    if (pingId != "" && Rede.venceu(pingPrazo)) {
        if (pingTentativa < 2) {
            pingTentativa += 1
            enviarPing()
        } else {
            serial.writeLine("CMD|" + pingId + "|" + pingToken + "|TIMEOUT")
            pingId = ""
        }
    }
    if (Rede.decorrido(ultimoAviso) >= 1000) {
        serial.writeLine("CENTRAL_ONLINE|1")
        ultimoAviso = agora
    }
    if (comunicacaoAtiva && Rede.decorrido(ultimaComunicacao) > 8000) {
        comunicacaoAtiva = false
        basic.showIcon(IconNames.No, 0)
    }
    basic.pause(10)
})
