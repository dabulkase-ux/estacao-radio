"""Benchmark HTTP/1.1 em loopback; nunca lê .env nem acessa Render/hardware."""
import copy
import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import statistics
import subprocess
import sys
import threading
import time
import tracemalloc

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gateway_remote import PublicadorRemoto

TOKEN = "benchmark-only-not-production-00000000000"


class Server(ThreadingHTTPServer):
    daemon_threads = True


def run(cls, load=False, delay=0, stations=1):
    rows, latencies, generated = [], [], {}
    lock, ready = threading.Lock(), threading.Event()
    snapshot = {"connected": True, "transport": "serial", "stations": {}}
    def update(seq):
        with lock:
            generated[seq] = time.perf_counter()
            snapshot["stations"] = {
                f"ST{i:02}": dict(name=str(seq), connected=True, sound=seq % 256, age=0, interval=.01)
                for i in range(stations)}
        changed.set()
    def get():
        with lock:
            return copy.deepcopy(snapshot)
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        def log_message(self, *args): pass
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if payload["connected"]:
                seq = int(next(iter(payload["stations"].values()))["name"])
                with lock:
                    latency = (time.perf_counter() - generated[seq]) * 1000
                rows.append((seq, latency, self.client_address[1]))
                ready.set()
            time.sleep(delay)
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()
    server = Server(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    sender = cls(f"http://127.0.0.1:{server.server_port}", TOKEN, obter=get)
    changed = threading.Event()
    sender.mudanca = changed
    stop = threading.Event()
    update(0)
    worker = threading.Thread(target=sender.executar, args=(stop,), daemon=True)
    tracemalloc.start()
    cpu, started = time.process_time(), time.perf_counter()
    worker.start()
    try:
        assert ready.wait(3)
        if load:
            for seq in range(1, 201):
                update(seq)
                time.sleep(.01)  # 100 mudanças/s, não 100 requisições/s.
            deadline = time.perf_counter() + 3
            while rows[-1][0] != 200 and time.perf_counter() < deadline:
                time.sleep(.01)
            assert rows[-1][0] == 200
            latencies = [r[1] for r in rows[1:]]
        else:
            for seq, phase in enumerate((.05, .17, .31, .47, .68, .89), 1):
                time.sleep(phase)
                ready.clear()
                update(seq)
                deadline = time.perf_counter() + 3
                while not any(r[0] == seq for r in rows) and time.perf_counter() < deadline:
                    time.sleep(.002)
                latencies.append(next(r[1] for r in rows if r[0] == seq))
        elapsed = time.perf_counter() - started
        cpu = time.process_time() - cpu
        _, peak = tracemalloc.get_traced_memory()
        return dict(load=load, stations=stations, response_delay_ms=delay * 1000,
                    publications=len(rows), generated=200 if load else 6,
                    connections=len({r[2] for r in rows}),
                    median_ms=round(statistics.median(latencies), 2),
                    max_ms=round(max(latencies), 2), cpu_s=round(cpu,3),
                    elapsed_s=round(elapsed,3), peak_kib=round(peak/1024),
                    final_value=rows[-1][0])
    finally:
        stop.set()
        changed.set()
        worker.join(7)
        server.shutdown()
        server.server_close()
        tracemalloc.stop()
        assert not worker.is_alive()


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    baseline = subprocess.check_output(["git", "show", "536afe1:gateway_remote.py"], text=True, encoding="utf-8")
    namespace = {}
    exec(compile(baseline, "gateway_v0_0_2.py", "exec"), namespace)
    results = []
    for name, cls in (("v0.0.2", namespace["PublicadorRemoto"]), ("atual", PublicadorRemoto)):
        results.append(dict(version=name, **run(cls)))
        results.append(dict(version=name, **run(cls, load=True, stations=8)))
        results.append(dict(version=name, **run(cls, load=True, stations=8, delay=.25)))
    print(json.dumps(results, indent=2))
