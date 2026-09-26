import copy
import json
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from werkzeug.serving import make_server

import app_radio
from backend_online import EstadoAtual, criar_backend
from estado import dados, lock_dados
from gateway_remote import PublicadorRemoto, estado_publicavel, configurar_publicador

TOKEN = "test-only-not-a-production-secret-0000000000"


class OnlineTests(unittest.TestCase):
    def setUp(self):
        self.now = 100
        self.state = EstadoAtual(clock=lambda: self.now)
        self.app, self.socket = criar_backend(TOKEN, ["https://radio.example"], False, self.state)
        self.client = self.app.test_client()
        self.viewer = self.socket.test_client(self.app)
        self.viewer.get_received()
        with lock_dados:
            dados["stations"].clear()
            dados["connected"] = False

    def tearDown(self):
        self.viewer.disconnect()

    def post(self, payload, token=TOKEN):
        return self.client.post("/api/gateway/state", json=payload,
                                headers={"Authorization": "Bearer " + token})

    def snapshot(self):
        app_radio.processar_radio("CENTRAL_ONLINE|1")
        app_radio.processar_radio("HEARTBEAT|QUARTO")
        app_radio.processar_radio("SOM|QUARTO|42")
        return estado_publicavel()

    def test_gateway_reutiliza_parser_publica_estado_e_som_muda(self):
        payload = self.snapshot()
        self.assertTrue(payload["connected"])
        self.assertTrue(payload["stations"]["QUARTO"]["connected"])
        self.assertEqual(payload["stations"]["QUARTO"]["sound"], 42)
        self.assertNotIn("history", json.dumps(payload))
        self.assertEqual(self.post(payload).status_code, 204)
        event = self.viewer.get_received()[-1]
        self.assertEqual(event["name"], "radio_data")
        self.assertEqual(event["args"][0]["stations"]["QUARTO"]["sound"], 42)
        app_radio.processar_radio("SOM|QUARTO|51")
        self.post(estado_publicavel())
        self.assertEqual(self.viewer.get_received()[-1]["args"][0]["stations"]["QUARTO"]["sound"], 51)
        self.assertNotIn("history", self.client.get("/api/data").text)

    def test_expiracao_estacao_sem_renovar_sinal_no_reenvio(self):
        payload = self.snapshot()
        self.post(payload)
        self.now += 6
        payload["stations"]["QUARTO"]["age"] = 6
        self.post(payload)  # Gateway vivo, estação sem novo heartbeat/dado.
        atual = self.client.get("/api/data").json
        self.assertTrue(atual["connected"])
        self.assertFalse(atual["stations"]["QUARTO"]["connected"])
        payload["stations"]["QUARTO"]["age"] = 0
        self.post(payload)
        self.assertTrue(self.state.obter()["stations"]["QUARTO"]["connected"])

    def test_gateway_desaparece_offline_e_reconecta(self):
        payload = self.snapshot()
        self.post(payload)
        self.now += 11
        atual = self.state.obter()
        self.assertFalse(atual["connected"])
        self.assertFalse(atual["gateway_connected"])
        self.assertFalse(atual["stations"]["QUARTO"]["connected"])
        self.assertNotIn("last_seen", atual["stations"]["QUARTO"])
        self.post(payload)
        self.assertTrue(self.state.obter()["connected"])
        payload["connected"] = False
        self.post(payload)
        self.assertFalse(self.state.obter()["stations"]["QUARTO"]["connected"])

    def test_backend_reinicia_e_gateway_reconstroi(self):
        payload = self.snapshot()
        self.post(payload)
        novo, sock = criar_backend(TOKEN, [], False)
        client = novo.test_client()
        self.assertEqual(client.get("/api/data").json["stations"], {})
        self.assertFalse(client.get("/api/data").json["connected"])
        self.assertEqual(client.post("/api/gateway/state", json=payload,
                                    headers={"Authorization": "Bearer " + TOKEN}).status_code, 204)
        self.assertTrue(client.get("/api/data").json["connected"])

    def test_token_invalido_socket_readonly_cors(self):
        payload = self.snapshot()
        self.assertEqual(self.post(payload, "errado").status_code, 401)
        self.assertEqual(self.client.post("/api/gateway/state", json=payload).status_code, 401)
        self.assertFalse(self.state.obter()["connected"])
        self.viewer.emit("gateway_state", payload)
        self.assertFalse(self.state.obter()["connected"])
        self.assertEqual(self.viewer.emit("radio_ping", {"id": "QUARTO"}, callback=True)["status"], "READ_ONLY")
        allowed = self.client.get("/api/data", headers={"Origin": "https://radio.example"})
        denied = self.client.get("/api/data", headers={"Origin": "https://evil.example"})
        self.assertEqual(allowed.headers["Access-Control-Allow-Origin"], "https://radio.example")
        self.assertNotIn("Access-Control-Allow-Origin", denied.headers)
        self.assertNotIn(TOKEN, allowed.text)

    def test_payloads_invalidos_e_memoria_limitada(self):
        good = self.snapshot()
        for field, value in [("age", float("nan")), ("age", -1), ("sound", 256),
                             ("connected", "true"), ("interval", float("inf"))]:
            payload = copy.deepcopy(good)
            payload["stations"]["QUARTO"][field] = value
            self.assertEqual(self.post(payload).status_code, 400)
        self.assertFalse(self.state.obter()["connected"])
        self.assertEqual(self.post({**good, "stations": {str(i): {} for i in range(65)}}).status_code, 400)
        self.assertEqual(self.client.post("/api/gateway/state", data=b"x" * 65537,
                          headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"}).status_code, 413)
        payload = copy.deepcopy(good)
        payload["stations"]["QUARTO"]["history"] = [42, 51]
        self.post(payload)
        self.assertNotIn("history", self.client.get("/api/data").text)

    def test_http_real_local_gateway_backend_socket(self):
        # Servidor HTTP real no loopback; nenhuma conexão à internet/hardware.
        server = make_server("127.0.0.1", 0, self.app, threaded=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            self.snapshot()
            url = f"http://127.0.0.1:{server.server_port}"
            sender = PublicadorRemoto(url, TOKEN)
            sender.enviar()
            self.assertTrue(self.state.obter()["connected"])
            self.assertEqual(self.viewer.get_received()[-1]["args"][0]["stations"]["QUARTO"]["sound"], 42)
            with self.assertRaises(HTTPError):
                PublicadorRemoto(url, "wrong" * 8).enviar()
            sender.enviar(offline=True)
            self.assertFalse(self.state.obter()["connected"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)

    def test_retry_sem_fila_de_historico(self):
        sender = PublicadorRemoto("https://backend.example", TOKEN)
        stop = threading.Event()
        attempts = []
        def send(offline=False):
            attempts.append(offline)
            if len(attempts) == 1:
                raise OSError("backend temporariamente fora")
            stop.set()
        with patch.object(sender, "enviar", side_effect=send), patch.object(stop, "wait", return_value=False):
            sender.executar(stop)
        self.assertEqual(attempts, [False, False, True])

    def test_socketio_polling_por_http_real(self):
        app, sock = criar_backend(TOKEN, [], False)
        server = make_server("127.0.0.1", 0, app, threaded=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        url = base + "/socket.io/?EIO=4&transport=polling"
        def ler(endereco):
            with urlopen(endereco, timeout=3) as r:
                return r.read().decode()
        def enviar(packet):
            with urlopen(Request(url, data=packet.encode(), headers={"Content-Type": "text/plain"}), timeout=3) as r:
                r.read()
        try:
            handshake = ler(url)
            sid = json.loads(handshake[1:])["sid"]
            url += "&sid=" + sid
            enviar("40")  # Engine.IO message + Socket.IO connect.
            self.assertIn('"radio_data"', ler(url))
            self.snapshot()
            sender = PublicadorRemoto(base, TOKEN)
            for som in (42, 51):
                app_radio.processar_radio(f"SOM|QUARTO|{som}")
                sender.enviar()
                pacotes = ler(url).split("\x1e")
                evento = next(json.loads(p[2:]) for p in pacotes if p.startswith("42"))
                self.assertEqual(evento[0], "radio_data")
                self.assertEqual(evento[1]["stations"]["QUARTO"]["sound"], som)
            enviar("41\x1e1")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)

    def test_config_sem_segredo_falha_e_https_obrigatorio(self):
        with self.assertRaises(ValueError):
            criar_backend("curto", [], False)
        with self.assertRaises(ValueError):
            PublicadorRemoto("http://public.example", TOKEN)
        with self.assertRaises(ValueError):
            PublicadorRemoto("https://user:secret@public.example", TOKEN)
        with patch.dict("os.environ", {"MICROSERIAL_BACKEND_URL": "", "MICROSERIAL_GATEWAY_TOKEN": ""}):
            self.assertIsNone(configurar_publicador())

    def test_monitor_publica_offline_sem_novos_posts(self):
        state = EstadoAtual(gateway_timeout=0.01, station_timeout=0.01)
        app, sock = criar_backend(TOKEN, [], True, state)
        viewer = sock.test_client(app)
        state.receber(self.snapshot())
        try:
            # Executa o monitor real, não apenas chamadas manuais a obter().
            threading.Event().wait(1.1)
            self.assertFalse(viewer.get_received()[-1]["args"][0]["connected"])
        finally:
            app.extensions["radio_online"]["stop"].set()
            viewer.disconnect()


if __name__ == "__main__":
    unittest.main()
