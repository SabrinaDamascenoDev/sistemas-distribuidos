"""
Biblioteca cliente do broker (usada por produtores e consumidores).
Ninguém aqui conhece IP/porta de outro componente final — só do broker.
"""
import json
import urllib.request


class ErroBroker(Exception):
    """Broker inalcançável."""


class ClienteBroker:
    def __init__(self, url="http://127.0.0.1:9000", timeout=10):
        self.url = url.rstrip("/")
        self.timeout = timeout

    def _post(self, rota, dados):
        req = urllib.request.Request(
            self.url + rota,
            data=json.dumps(dados).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except OSError as e:  # conexão recusada, timeout...
            raise ErroBroker(f"broker indisponível: {e}") from e

    def publicar(self, fila, corpo):
        return self._post("/publicar", {"fila": fila, "corpo": corpo})["id"]

    def consumir(self, fila, visibilidade=10):
        return self._post("/consumir", {"fila": fila, "visibilidade": visibilidade})["mensagem"]

    def ack(self, msg):
        return self._post("/ack", {"id": msg["id"]})["ok"]

    def estatisticas(self):
        with urllib.request.urlopen(self.url + "/stats", timeout=self.timeout) as r:
            return json.loads(r.read().decode("utf-8"))
