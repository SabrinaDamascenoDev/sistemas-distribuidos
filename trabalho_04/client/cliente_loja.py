"""
PRODUTOR: o cliente da loja. Substitui o ClienteProxy (stub RPC) do Trabalho 2.

O cliente só conhece o BROKER. Não sabe quem executa, onde, nem se está ligado agora.

  enviar()  -> assíncrono: publica e volta na hora (desacoplamento temporal)
  esperar() -> busca a resposta na fila de respostas própria (request-reply sobre filas)
  chamar()  -> enviar + esperar (parece uma chamada remota, mas por baixo é uma fila)
"""
import time
import uuid

from mq.cliente_broker import ClienteBroker

FILA_COMANDOS = "comandos"


class ClienteLoja:
    def __init__(self, broker_url="http://127.0.0.1:9000", nome=None):
        self.broker = ClienteBroker(broker_url)
        self.fila_resposta = f"resp.{nome or uuid.uuid4().hex[:8]}"
        self._respostas = {}  # respostas que chegaram fora de ordem

    def enviar(self, metodo, argumentos=None, quer_resposta=True):
        id_comando = uuid.uuid4().hex
        self.broker.publicar(FILA_COMANDOS, {
            "id_comando": id_comando,
            "metodo": metodo,
            "argumentos": argumentos or {},
            "reply_to": self.fila_resposta if quer_resposta else None,
        })
        return id_comando

    def esperar(self, id_comando, timeout=10):
        """Devolve o resultado, ou None se estourar o tempo (worker offline/lento)."""
        fim = time.time() + timeout
        while time.time() < fim:
            if id_comando in self._respostas:
                return self._respostas.pop(id_comando)
            msg = self.broker.consumir(self.fila_resposta, visibilidade=30)
            if msg:
                self._respostas[msg["corpo"]["id_comando"]] = msg["corpo"]["resultado"]
                self.broker.ack(msg)
            else:
                time.sleep(0.1)
        return None

    def chamar(self, metodo, argumentos=None, timeout=10):
        return self.esperar(self.enviar(metodo, argumentos), timeout)
