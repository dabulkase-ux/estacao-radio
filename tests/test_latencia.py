import contextlib
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import logging
import http.client
import socket
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import app_radio
from estado import dados, lock_dados, mudanca_remota
from gateway_remote import PublicadorRemoto, estado_publicavel

TOKEN = "latency-test-only-000000000000000000000"


def snapshot(value=1):
    return dict(connected=True, transport="serial", stations={"QUARTO": dict(
        name="Quarto", sound=value, connected=True, age=0, interval=.1)})


@contextlib.contextmanager
def server(callback):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        def log_message(self, *args): pass
        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            code = callback(data, self)
            if code is None: return
            self.send_response(code)
            if code == 302:
                self.send_header("Location", "/nao-seguir")
            self.send_header("Content-Length", "0")
            self.end_headers()
    http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    http.daemon_threads = True
    t = threading.Thread(target=http.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{http.server_port}"
    finally:
        http.shutdown()
        http.server_close()
        t.join(2)


class LatenciaTests(unittest.TestCase):
    def test_queda_tcp_e_reinicio_gateway_enviam_somente_estado_atual(self):
        received, value = [], [1]
        def receive(data, request):
            received.append(data["stations"]["QUARTO"]["sound"])
            if len(received) == 1:
                request.close_connection = True
                request.connection.shutdown(socket.SHUT_RDWR)
                request.connection.close()
                return None
            return 204
        with server(receive) as url:
            p = PublicadorRemoto(url, TOKEN, lambda: snapshot(value[0]))
            with self.assertRaises(http.client.HTTPException): p.enviar()
            self.assertIsNone(p.conexao)
            value[0] = 99
            try: p.enviar()
            finally: p.fechar()
            value[0] = 100
            novo = PublicadorRemoto(url, TOKEN, lambda: snapshot(value[0]))
            try: novo.enviar()
            finally: novo.fechar()
        self.assertEqual(received, [1,99,100])

    def test_http_reusa_conexao_nao_redireciona_e_fecha_em_erro(self):
        rows, status = [], [204]
        def receive(data, request):
            rows.append((request.path, request.client_address[1]))
            self.assertEqual(request.headers["Authorization"], "Bearer " + TOKEN)
            return status[0]
        with server(receive) as url:
            p = PublicadorRemoto(url, TOKEN, snapshot)
            try:
                p.enviar(); p.enviar()
                self.assertEqual(rows[0][1], rows[1][1])
                status[0] = 302
                with self.assertRaises(HTTPError): p.enviar()
                self.assertIsNone(p.conexao)
                self.assertEqual(len(rows), 3)
                self.assertTrue(all(r[0] == "/api/gateway/state" for r in rows))
                status[0] = 204
                p.enviar()  # Reconecta após fechar conexão recusada.
            finally: p.fechar()

    def test_estado_novo_durante_http_lento_substitui_intermediarios(self):
        entered, release, final = threading.Event(), threading.Event(), threading.Event()
        value, received = [1], []
        def receive(data, request):
            if data["connected"]:
                received.append(data["stations"]["QUARTO"]["sound"])
                if len(received) == 1:
                    entered.set(); release.wait(3)
                elif received[-1] == 200: final.set()
            return 204
        with server(receive) as url:
            p = PublicadorRemoto(url, TOKEN, lambda: snapshot(value[0]))
            p.mudanca = threading.Event()
            stop = threading.Event()
            t = threading.Thread(target=p.executar, args=(stop,))
            t.start()
            try:
                self.assertTrue(entered.wait(2))
                for i in range(2,201):
                    value[0] = i; p.mudanca.set()
                release.set()
                self.assertTrue(final.wait(2))
                self.assertEqual(received[:2], [1,200])
            finally:
                release.set(); stop.set(); p.mudanca.set(); t.join(7)
            self.assertFalse(t.is_alive())

    def test_notificacao_parser_e_keepalive_sem_novos_sinais(self):
        with lock_dados:
            dados["stations"].clear()
        received, updated = [], threading.Event()
        def receive(data, request):
            received.append(data)
            if data["stations"].get("QUARTO", {}).get("sound") == 51: updated.set()
            return 204
        with server(receive) as url:
            p = PublicadorRemoto(url, TOKEN)
            stop = threading.Event()
            t = threading.Thread(target=p.executar, args=(stop,))
            t.start()
            try:
                app_radio.processar_radio("CENTRAL_ONLINE|1")
                app_radio.processar_radio("SOM|QUARTO|51")
                self.assertTrue(updated.wait(2))
                n = len(received)
                time.sleep(1.2)
                self.assertGreater(len(received), n)
                self.assertGreater(received[-1]["stations"]["QUARTO"]["age"], .9)
            finally:
                stop.set(); mudanca_remota.set(); t.join(7)

    def test_backoff_nao_e_interrompido_por_telemetria_nova(self):
        attempts, value, stop = [], [1], threading.Event()
        p = PublicadorRemoto("https://backend.example", TOKEN, lambda: snapshot(value[0]))
        p.mudanca = threading.Event()
        def send(offline=False):
            if offline: return
            attempts.append(value[0])
            if len(attempts) == 1: raise OSError("falha simulada")
            stop.set()
        def wait(seconds):
            if stop.is_set(): return True
            self.assertEqual(seconds, 2)
            value[0] = 99
            p.mudanca.set()
            return False
        with patch.object(p, "enviar", side_effect=send), patch.object(stop, "wait", side_effect=wait):
            p.executar(stop)
        self.assertEqual(attempts, [1,99])

    def test_snapshot_nao_copia_historico(self):
        class NaoCopiar:
            def __deepcopy__(self, memo): raise AssertionError("Histórico não deve ser copiado")
        with lock_dados:
            saved = dados["stations"]
            dados["stations"] = {"QUARTO": dict(snapshot()["stations"]["QUARTO"],
                                               last_seen=time.time(), history=NaoCopiar())}
            try:
                result = estado_publicavel()
                self.assertNotIn("history", result["stations"]["QUARTO"])
            finally: dados["stations"] = saved

    def test_diagnostico_nao_expoe_token(self):
        with server(lambda data, request: 204) as url:
            p = PublicadorRemoto(url, TOKEN, snapshot)
            p.diagnostico = True
            anterior = logging.root.manager.disable
            try:
                logging.disable(logging.NOTSET)
                with self.assertLogs("microserial.gateway", level="INFO") as logs:
                    p.enviar()
                self.assertNotIn(TOKEN, str(logs.output))
                self.assertNotIn("Authorization", str(logs.output))
                self.assertIn("ida/volta", str(logs.output))
            finally:
                p.fechar()
                logging.disable(anterior)


if __name__ == "__main__": unittest.main()
