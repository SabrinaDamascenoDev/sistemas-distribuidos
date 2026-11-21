"""
PRODUTOR: o cliente da loja. Substitui o ClienteProxy (stub RPC) do Trabalho 2.

O cliente só conhece o BROKER. Não sabe quem executa, onde, nem se está ligado agora.

  enviar()  -> assíncrono: publica e volta na hora (desacoplamento temporal)
  esperar() -> busca a resposta na fila de respostas própria (request-reply sobre filas)
  chamar()  -> enviar + esperar (parece uma chamada remota, mas por baixo é uma fila)

Robustez:
  * esperar() tolera o broker cair e voltar dentro do prazo (continua tentando).
  * Respostas duplicadas (o worker pode reenviar numa reentrega) são descartadas.
"""
import time
import uuid

from mq.cliente_broker import ClienteBroker, ErroBroker

FILA_COMANDOS = "comandos"


class ClienteLoja:
    def __init__(self, broker_url="http://127.0.0.1:9000", nome=None, espera=5.0, keep_alive=True):
        self.broker = ClienteBroker(broker_url, keep_alive=keep_alive)
        self.fila_resposta = f"resp.{nome or uuid.uuid4().hex[:8]}"
        self.espera = espera      # long polling na fila de respostas (0 = polling curto)
        self._respostas = {}      # chegaram, mas ainda não foram pedidas
        self._entregues = set()   # já devolvidas ao chamador (descarta duplicatas)

    def enviar(self, metodo, argumentos=None, quer_resposta=True):
        """Publica o comando e volta na hora. Lança ErroBroker se o broker estiver fora."""
        id_comando = uuid.uuid4().hex
        self.broker.publicar(FILA_COMANDOS, {
            "id_comando": id_comando,
            "metodo": metodo,
            "argumentos": argumentos or {},
            "reply_to": self.fila_resposta if quer_resposta else None,
        })
        return id_comando

    def _guardar(self, msg):
        corpo = msg["corpo"]
        id_comando = corpo.get("id_comando")
        if id_comando not in self._entregues:
            self._respostas[id_comando] = corpo.get("resultado")
        try:
            self.broker.ack(msg)
        except ErroBroker:
            pass  # se o ack se perder, a resposta volta e é descartada como duplicata

    def _buscar(self, espera):
        try:
            msg = self.broker.consumir(self.fila_resposta, visibilidade=30, espera=espera)
        except ErroBroker:
            time.sleep(0.5)  # broker fora: tenta de novo na próxima volta
            return False
        if msg is None:
            if not self.espera:
                time.sleep(0.1)  # polling curto
            return False
        self._guardar(msg)
        return True

    def esperar(self, id_comando, timeout=10):
        """Devolve o resultado, ou None se estourar o tempo (worker offline/lento)."""
        fim = time.time() + timeout
        while True:
            if id_comando in self._respostas:
                self._entregues.add(id_comando)
                return self._respostas.pop(id_comando)
            restante = fim - time.time()
            if restante <= 0:
                return None
            self._buscar(min(self.espera, restante))

    def chamar(self, metodo, argumentos=None, timeout=10):
        return self.esperar(self.enviar(metodo, argumentos), timeout)

    def coletar_respostas(self):
        """Pega tudo o que já chegou na fila de respostas, sem esperar. {id_comando: resultado}
        Lança ErroBroker se o broker estiver fora."""
        while True:
            msg = self.broker.consumir(self.fila_resposta, visibilidade=30, espera=0)
            if msg is None:
                break
            self._guardar(msg)
        novas = dict(self._respostas)
        self._entregues.update(novas)
        self._respostas.clear()
        return novas

    def fechar(self):
        self.broker.fechar()