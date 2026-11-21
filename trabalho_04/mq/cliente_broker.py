"""
Biblioteca cliente do broker (usada por produtores e consumidores).
Ninguém aqui conhece IP/porta de outro componente final — só do broker.

keep_alive=True (padrão): reaproveita a mesma conexão TCP entre requisições (HTTP/1.1).
Se a conexão reaproveitada tiver morrido (ex.: broker reiniciou), reconecta uma vez,
de forma transparente. Uma instância deve ser usada por uma única thread.
"""
import http.client
import json
import socket
from urllib.parse import urlsplit


class ErroBroker(Exception):
    """Broker inalcançável (ou recusou a requisição)."""


class RequisicaoInvalida(ErroBroker):
    """O broker respondeu, mas recusou a requisição (HTTP 4xx)."""


class ClienteBroker:
    def __init__(self, url="http://127.0.0.1:9000", timeout=10, keep_alive=True):
        partes = urlsplit(url)
        self.url = url.rstrip("/")
        self.host = partes.hostname or "127.0.0.1"
        self.porta = partes.port or 80
        self.timeout = timeout
        self.keep_alive = keep_alive
        self._conn = None

    # ------------------------------------------------------------------ transporte
    def _fechar(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _requisitar(self, metodo, rota, dados=None, timeout=None):
        timeout = timeout or self.timeout
        corpo = None if dados is None else json.dumps(dados).encode("utf-8")
        cabecalhos = {"Content-Type": "application/json"}
        if not self.keep_alive:
            cabecalhos["Connection"] = "close"
        for _ in range(2):
            reaproveitada = self._conn is not None
            try:
                if not reaproveitada:
                    self._conn = http.client.HTTPConnection(self.host, self.porta, timeout=timeout)
                    self._conn.connect()
                    # Desliga o algoritmo de Nagle (ver broker/servidor_http.py).
                    self._conn.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                self._conn.sock.settimeout(timeout)
                self._conn.request(metodo, rota, body=corpo, headers=cabecalhos)
                resp = self._conn.getresponse()
                bruto = resp.read()
                if not self.keep_alive or resp.will_close:
                    self._fechar()
            except (OSError, http.client.HTTPException) as e:
                self._fechar()
                # Só vale tentar de novo se a falha foi numa conexão velha (o broker pode ter
                # reiniciado). Timeout ou conexão nova recusada = broker realmente fora.
                if reaproveitada and not isinstance(e, socket.timeout):
                    continue
                raise ErroBroker(f"broker indisponível: {e}") from e
            resposta = json.loads(bruto.decode("utf-8")) if bruto else {}
            if resp.status >= 400:
                raise RequisicaoInvalida(f"broker recusou ({resp.status}): {resposta.get('erro')}")
            return resposta
        raise ErroBroker("broker indisponível")  # não deve chegar aqui

    # ------------------------------------------------------------------ operações
    def publicar(self, fila, corpo):
        return self._requisitar("POST", "/publicar", {"fila": fila, "corpo": corpo})["id"]

    def consumir(self, fila, visibilidade=10, espera=0):
        """espera > 0 = long polling: o broker segura a resposta até chegar mensagem."""
        resp = self._requisitar("POST", "/consumir",
                                {"fila": fila, "visibilidade": visibilidade, "espera": espera},
                                timeout=self.timeout + espera)
        return resp["mensagem"]

    def ack(self, msg):
        return self._requisitar("POST", "/ack", {"id": msg["id"], "recibo": msg["recibo"]})["ok"]

    def nack(self, msg, reenfileirar=True, motivo=None):
        return self._requisitar("POST", "/nack", {"id": msg["id"], "recibo": msg["recibo"],
                                                  "reenfileirar": reenfileirar, "motivo": motivo})["ok"]

    def espiar(self, fila, limite=10):
        return self._requisitar("POST", "/espiar", {"fila": fila, "limite": limite})["mensagens"]

    def estatisticas(self):
        return self._requisitar("GET", "/stats")

    def metricas(self):
        return self._requisitar("GET", "/metricas")

    def fechar(self):
        self._fechar()