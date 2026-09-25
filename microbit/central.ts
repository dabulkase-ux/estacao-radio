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
