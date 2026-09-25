// MICRO:BIT V2 — PONTE. Adicione também protocolo.ts ao MakeCode.
// Sem estação configurada: encaminha todos os tipos válidos.
Rede.iniciar()
radio.onReceivedBuffer(function (pacote) {
    Rede.repetir(pacote)
})
basic.showIcon(IconNames.Yes, 0)
serial.writeLine("PONTE_ONLINE")
