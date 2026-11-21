"""
Camada de rede do broker: expõe o BrokerFilas por HTTP + JSON (como no Trabalho 2).

  POST /publicar  {"fila": "...", "corpo": {...}}                         -> {"id": 7}
  POST /consumir  {"fila": "...", "visibilidade": 10, "espera": 5}        -> {"mensagem": {...} | null}
  POST /ack       {"id": 7, "recibo": "..."}                              -> {"ok": true}
  POST /nack      {"id": 7, "recibo": "...", "reenfileirar": false, "motivo": "..."} -> {"ok": true}
  POST /espiar    {"fila": "dlq.comandos", "limite": 10}                  -> {"mensagens": [...]}
  GET  /stats                                                             -> {"fila": {...}}
  GET  /metricas                                                          -> {"requisicoes_http": n, "conexoes_tcp": m}

Otimizações de desempenho:
  * HTTP/1.1 com conexões persistentes (keep-alive): o cliente reaproveita a mesma conexão
    TCP em vez de abrir uma por requisição.
  * Long polling em /consumir ("espera"): a requisição fica aberta até chegar mensagem.
    Antes de retirar uma mensagem para quem está esperando, o broker confere se a conexão
    ainda está viva; se o consumidor morreu, nada é retirado para ele.
"""
import json
import select
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ESPERA_MAXIMA = 20.0  # segundos de long polling, no máximo


class Metricas:
    def __init__(self):
        self._lock = threading.Lock()
        self.requisicoes = 0
        self.conexoes = 0

    def contar(self, campo):
        with self._lock:
            setattr(self, campo, getattr(self, campo) + 1)

    def como_dict(self):
        with self._lock:
            return {"requisicoes_http": self.requisicoes, "conexoes_tcp": self.conexoes}


def _texto(req, campo):
    valor = req[campo]
    if not isinstance(valor, str) or not valor:
        raise ValueError(f"'{campo}' deve ser texto não vazio")
    return valor


def _numero(req, campo, padrao, minimo, maximo):
    valor = float(req.get(campo, padrao))
    return min(max(valor, minimo), maximo)


class ConexoesAbertas:
    """Guarda as conexões ativas para que parar() as derrube (como numa queda real)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._socks = set()

    def adicionar(self, sock):
        with self._lock:
            self._socks.add(sock)

    def remover(self, sock):
        with self._lock:
            self._socks.discard(sock)

    def derrubar_todas(self):
        with self._lock:
            socks, self._socks = list(self._socks), set()
        for s in socks:
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def criar_handler(broker, metricas, conexoes):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"  # habilita keep-alive
        timeout = 60                   # fecha conexões ociosas depois de 60 s
        # Sem estas duas linhas o keep-alive fica MAIS LENTO: cabeçalho e corpo saem em dois
        # send() e o algoritmo de Nagle segura o 2º até o ACK, que o cliente atrasa ~40 ms.
        disable_nagle_algorithm = True  # TCP_NODELAY
        wbufsize = -1                   # cabeçalho + corpo num único envio

        def log_message(self, *args):
            pass

        def setup(self):
            super().setup()
            metricas.contar("conexoes")
            conexoes.adicionar(self.connection)

        def finish(self):
            try:
                super().finish()
            finally:
                conexoes.remover(self.connection)

        def _responder(self, dados, status=200):
            corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
            try:
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                self.wfile.write(corpo)
            except (BrokenPipeError, ConnectionResetError):
                # Cliente sumiu. Se era uma entrega, a mensagem volta sozinha quando o
                # prazo de visibilidade vencer (at-least-once).
                self.close_connection = True

        def _cliente_ativo(self):
            """True se a conexão do cliente ainda está aberta (usado no long polling)."""
            try:
                prontos, _, _ = select.select([self.connection], [], [], 0)
                if not prontos:
                    return True  # nada para ler: conexão aberta e ociosa
                return self.connection.recv(1, socket.MSG_PEEK) != b""  # b"" = fechou
            except (OSError, ValueError):
                return False

        def do_GET(self):
            metricas.contar("requisicoes")
            if self.path == "/stats":
                self._responder(broker.estatisticas())
            elif self.path == "/metricas":
                self._responder(metricas.como_dict())
            else:
                self._responder({"erro": "rota inexistente"}, 404)

        def do_POST(self):
            metricas.contar("requisicoes")
            try:
                tamanho = int(self.headers.get("Content-Length", 0))
                req = json.loads(self.rfile.read(tamanho).decode("utf-8"))
                if not isinstance(req, dict):
                    raise ValueError("o corpo deve ser um objeto JSON")
                if self.path == "/publicar":
                    self._responder({"id": broker.publicar(_texto(req, "fila"), req["corpo"])})
                elif self.path == "/consumir":
                    espera = _numero(req, "espera", 0, 0, ESPERA_MAXIMA)
                    msg = broker.consumir(
                        _texto(req, "fila"),
                        visibilidade=_numero(req, "visibilidade", 10, 0.1, 3600),
                        espera=espera,
                        ativo=self._cliente_ativo if espera > 0 else None,
                    )
                    self._responder({"mensagem": msg})
                elif self.path == "/ack":
                    self._responder({"ok": broker.ack(int(req["id"]), _texto(req, "recibo"))})
                elif self.path == "/nack":
                    ok = broker.nack(int(req["id"]), _texto(req, "recibo"),
                                     bool(req.get("reenfileirar", True)), req.get("motivo"))
                    self._responder({"ok": ok})
                elif self.path == "/espiar":
                    limite = int(_numero(req, "limite", 10, 1, 1000))
                    self._responder({"mensagens": broker.espiar(_texto(req, "fila"), limite)})
                else:
                    self._responder({"erro": "rota inexistente"}, 404)
            except (KeyError, ValueError, TypeError) as e:
                self._responder({"erro": f"requisição inválida: {e}"}, 400)

    return Handler


class _ServidorHTTP(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        # Cliente que cai no meio da conversa é rotina num sistema distribuído: não poluir o log.
        if isinstance(sys.exc_info()[1], OSError):
            return
        super().handle_error(request, client_address)


class ServidorBroker:
    def __init__(self, broker, host="127.0.0.1", porta=9000):
        self.metricas = Metricas()
        self._conexoes = ConexoesAbertas()
        self.httpd = _ServidorHTTP((host, porta), criar_handler(broker, self.metricas, self._conexoes))

    @property
    def porta(self):
        return self.httpd.server_address[1]

    def iniciar(self):
        self.httpd.serve_forever()

    def parar(self):
        """Para de aceitar conexões e derruba as abertas (keep-alive e long polling)."""
        self.httpd.shutdown()
        self.httpd.server_close()
        self._conexoes.derrubar_todas()