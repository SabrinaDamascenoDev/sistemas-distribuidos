"""
Camada de rede do broker: expõe o BrokerFilas por HTTP + JSON (como no Trabalho 2).

  POST /publicar  {"fila": "...", "corpo": {...}}          -> {"id": 7}
  POST /consumir  {"fila": "...", "visibilidade": 10}      -> {"mensagem": {...} | null}
  POST /ack       {"id": 7}                                -> {"ok": true}
  GET  /stats                                              -> {"fila": {...}}

TODO (dupla, opcional): long polling (o broker esperar N segundos por mensagem em vez de
responder null na hora). Cuidado: se o consumidor morrer durante a espera, o broker não
pode retirar mensagem para ele (senão quebra a ordem FIFO).
"""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def criar_handler(broker):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): 
            pass

        def _responder(self, dados, status=200):
            corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)

        def do_GET(self):
            if self.path == "/stats":
                self._responder(broker.estatisticas())
            else:
                self._responder({"erro": "rota inexistente"}, 404)

        def do_POST(self):
            try:
                tamanho = int(self.headers.get("Content-Length", 0))
                req = json.loads(self.rfile.read(tamanho).decode("utf-8"))
                if self.path == "/publicar":
                    self._responder({"id": broker.publicar(req["fila"], req["corpo"])})
                elif self.path == "/consumir":
                    self._responder({"mensagem": broker.consumir(req["fila"], float(req.get("visibilidade", 10)))})
                elif self.path == "/ack":
                    self._responder({"ok": broker.ack(req["id"])})
                else:
                    self._responder({"erro": "rota inexistente"}, 404)
            except (KeyError, ValueError) as e:
                self._responder({"erro": f"requisição inválida: {e}"}, 400)

    return Handler


class ServidorBroker:
    def __init__(self, broker, host="127.0.0.1", porta=9000):
        self.httpd = ThreadingHTTPServer((host, porta), criar_handler(broker))
        self.httpd.daemon_threads = True

    def iniciar(self):
        self.httpd.serve_forever()
