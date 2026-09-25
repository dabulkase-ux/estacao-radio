import json
import logging
import subprocess
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import serial
import app_radio
import serial_manager as sm
from estado import dados, lock_dados, obter_estado
from estacoes import atualizar_estacao
from parser import extrair_dados_mensagem
from protocolo_serial import LinhasSerial, NomesFragmentados
from monitor import monitorar_estacoes

logging.disable(logging.CRITICAL)
ROOT = Path(__file__).resolve().parents[1]


class TestIntegracao(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        saida = subprocess.check_output(
            ["node", "--disable-warning=ExperimentalWarning", "tests/rede_sim.js", "--fixture"],
            cwd=ROOT, text=True, encoding="utf-8")
        cls.linhas_reais = json.loads(saida)

    def setUp(self):
        with lock_dados:
            dados["stations"].clear()
            dados.update(connected=False, central_port=None, last_known_port=None,
                         communication_status="disconnected")
        sm.registrar_conexao(None)

    def test_typescript_8_relays_serial_flask_socket_frontend(self):
        cliente = app_radio.socketio.test_client(app_radio.app)
        cliente.get_received()
        nomes = NomesFragmentados()
        # Quebrar cada linha em bytes reproduz leituras parciais na serial.
        leitor = LinhasSerial()
        for linha in self.linhas_reais:
            for byte in (linha + "\r\n").encode():
                for completa in leitor.alimentar(bytes([byte])):
                    if completa.startswith("NPART|"):
                        completa = nomes.receber(completa)
                    if completa:
                        app_radio.processar_radio(completa)
        recebido = cliente.get_received()
        eventos = [x["args"][0] for x in recebido if x["name"] == "radio_data"]
        self.assertTrue(eventos)
        estacao = eventos[-1]["stations"]["QUARTO"]
        self.assertEqual(estacao["name"], "Quarto")
        self.assertEqual(estacao["sound"], 250)
        self.assertTrue(estacao["connected"])
        http = app_radio.app.test_client()
        self.assertEqual(http.get("/api/data").json["stations"]["QUARTO"], estacao)
        self.assertIsInstance(estacao["history"], list)
        self.assertIn(b"data-ping", http.get("/").data)
        cliente.disconnect()

    def test_parser_formatos_e_multiplas_estacoes(self):
        for linha in ["NOME|QUARTO|Quarto", "STATUS|QUARTO|ONLINE", "SOM|QUARTO|255",
                      "HEARTBEAT|COZINHA", "NOME|COZINHA|Cozinha", "R|8|S|COZINHA|17",
                      "ID=QUARTO|NOME=Quarto|SOM=42", "RADIO|QUARTO|Quarto|ONLINE|SOM|22"]:
            self.assertTrue(app_radio.processar_radio(linha), linha)
        stations = obter_estado()["stations"]
        self.assertEqual(stations["COZINHA"]["sound"], 17)
        self.assertEqual(stations["QUARTO"]["sound"], 22)

    def test_invalidos_nao_mudam_estado(self):
        app_radio.processar_radio("HEARTBEAT|QUARTO")
        anterior = obter_estado()
        for linha in ["SOM|QUARTO", "SOM|QUARTO|x", "SOM|QUARTO|256", "SOM|QUARTO|nan",
                      "SOM|12", "STATUS|QUARTO|???", "NOME|QUARTO", "HEARTBEAT|",
                      "ACK|QUARTO", "RETURN|1|ACK|QUARTO", "R|-1|H|QUARTO", "R|a|H|QUARTO",
                      "R|8|S|QUARTO", "R|8|X|QUARTO", "ID=QUARTO|SOM=oops",
                      "RADIO|QUARTO|Quarto|SOM|oops", "RADIO|QUARTO|Quarto|SOM",
                      "ID=COZINHA|SOM|QUARTO|12", "x" * 513]:
            self.assertFalse(app_radio.processar_radio(linha), linha)
        self.assertEqual(anterior, obter_estado())

    def test_linhas_parciais_utf8_invalido_limite(self):
        l = LinhasSerial(20)
        self.assertEqual(l.alimentar(b"SOM|QUA"), [])
        self.assertEqual(l.alimentar(b"RTO|2\r\n"), ["SOM|QUARTO|2"])
        self.assertEqual(l.alimentar(b"\xff\n"), [])
        self.assertEqual(l.alimentar(b"x" * 50 + b"\nID|AA\n"), ["ID|AA"])
        self.assertLessEqual(len(l.buffer), 20)

    def test_fragmentos_fora_de_ordem_incompletos_reinicio(self):
        n = NomesFragmentados()
        partes = [x for x in self.linhas_reais if x.startswith("NPART|")]
        self.assertGreater(len(partes), 1)
        self.assertIsNone(n.receber(partes[-1]))
        self.assertIsNone(n.receber(partes[-1]))
        resultado = None
        for p in partes[:-1]:
            resultado = n.receber(p) or resultado
        self.assertEqual(resultado, "NOME|QUARTO|Quarto")
        self.assertIsNone(n.receber("NPART|QUARTO|1|17|16|aa"))
        with patch("protocolo_serial.time.monotonic", return_value=0):
            n.receber(partes[0])
        with patch("protocolo_serial.time.monotonic", return_value=11):
            self.assertIsNone(n.receber(partes[-1]))
        self.assertLessEqual(len(n.pendentes), 32)

    def test_descoberta_rejeita_ponte_e_usb_generico(self):
        portas = [SimpleNamespace(device="COM1", description="micro:bit"),
                  SimpleNamespace(device="COM2", description="micro:bit"),
                  SimpleNamespace(device="COM3", description="USB unrelated")]
        fechado = []
        def abrir(porta):
            if porta == "COM1":
                raise serial.SerialException("PONTE_ONLINE")
            return SimpleNamespace(close=lambda: fechado.append(porta))
        with patch.dict("os.environ", {"MICROSERIAL_PORT": ""}), patch.object(sm.serial.tools.list_ports, "comports", return_value=portas), patch.object(sm, "abrir_microbit", side_effect=abrir) as mock:
            self.assertEqual(sm.encontrar_microbit(), "COM2")
            self.assertEqual([x.args[0] for x in mock.call_args_list], ["COM1", "COM2"])
        self.assertEqual(fechado, ["COM2"])

    def test_handshake_serial_fragmentado(self):
        partes = iter([b"PONTE_ONLINE\n", b"CENTRAL_ON", b"LINE|1\r\n"])
        fake = SimpleNamespace(write=lambda x: len(x), readline=lambda _: next(partes), close=lambda: None)
        with patch.object(sm.serial, "Serial", return_value=fake):
            self.assertIs(sm.abrir_microbit("COM2"), fake)

    def test_socket_ping_correlacao_resultado_real(self):
        writes = []
        def escrever(b):
            writes.append(b)
            self.assertFalse(sm.receber_resultado("CMD|COZINHA|314|OK") is False)
            sm.receber_resultado("CMD|QUARTO|999|OK")
            for linha in self.linhas_reais:
                if linha.startswith("CMD|"):
                    sm.receber_resultado(linha)
            return len(b)
        sm.registrar_conexao(SimpleNamespace(write=escrever))
        cliente = app_radio.socketio.test_client(app_radio.app)
        with patch.object(sm.secrets, "randbits", return_value=314):
            resposta = cliente.emit("radio_ping", {"id": "QUARTO"}, callback=True)
        self.assertEqual(writes, [b"PING|QUARTO|314\n"])
        self.assertEqual(resposta, {"ok": True, "status": "OK", "id": "QUARTO"})
        self.assertFalse(cliente.emit("radio_ping", {"id": "AA\nHELLO"}, callback=True)["ok"])
        cliente.disconnect()

    def test_ping_sem_conexao_timeout_ocupado_e_falha_escrita(self):
        self.assertEqual(sm.enviar_ping("QUARTO")["status"], "DISCONNECTED")
        def escrever(b):
            self.assertEqual(sm.enviar_ping("COZINHA")["status"], "BUSY")
            sm.receber_resultado("CMD|QUARTO|9|TIMEOUT")
            return len(b)
        sm.registrar_conexao(SimpleNamespace(write=escrever))
        with patch.object(sm.secrets, "randbits", return_value=9):
            self.assertEqual(sm.enviar_ping("QUARTO")["status"], "TIMEOUT")
        sm.registrar_conexao(SimpleNamespace(write=lambda _: 0))
        self.assertEqual(sm.enviar_ping("QUARTO")["status"], "DISCONNECTED")

    def test_leitor_real_serial_parcial_e_desconexao(self):
        stop = threading.Event()
        partes = iter([b"CENTRAL_ONLINE|1\n", b"SOM|QU", b"ARTO|250\n"])
        def ler(_):
            try:
                return next(partes)
            except StopIteration:
                stop.set()
                raise serial.SerialException("USB removido")
        fechou = []
        fake = SimpleNamespace(readline=ler, close=lambda: fechou.append(True))
        with patch.object(app_radio, "encontrar_microbit", return_value="COM2"), patch.object(app_radio, "abrir_microbit", return_value=fake):
            app_radio.ler_microbit(stop)
        self.assertEqual(obter_estado()["stations"]["QUARTO"]["sound"], 250)
        self.assertFalse(obter_estado()["connected"])
        self.assertTrue(fechou)

    def test_monitor_offline_e_recuperacao(self):
        atualizar_estacao(extrair_dados_mensagem("HEARTBEAT|QUARTO"), agora=1)
        stop = threading.Event()
        def publicar():
            stop.set()
        with patch("monitor.time.time", return_value=20):
            monitorar_estacoes(stop, publicar)
        self.assertFalse(obter_estado()["stations"]["QUARTO"]["connected"])
        atualizar_estacao(extrair_dados_mensagem("HEARTBEAT|QUARTO"), agora=21)
        self.assertTrue(obter_estado()["stations"]["QUARTO"]["connected"])
        self.assertIsNone(obter_estado()["stations"]["QUARTO"]["interval"])


if __name__ == "__main__":
    unittest.main()
