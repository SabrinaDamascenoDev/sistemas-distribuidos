"""
Servidor request-reply genérico sobre TCP (reaproveitado pelas questões 3, 4 e extra).

Cada cliente é atendido em uma thread própria. Para cada mensagem:
  1. receber()   -> lê os bytes e DESEMPACOTA o request (bytes -> dict)
  2. executar()  -> lógica da aplicação (implementada pela subclasse)
  3. enviar()    -> EMPACOTA o reply (dict -> bytes) e envia ao cliente

"""

import socket
import threading

from serialization.protocolo import enviar, receber


class ServidorTCP:
    """Classe base: a subclasse implementa executar(operacao, argumentos, endereco)."""

    def __init__(self, host, porta, verboso=True):
        self.verboso = verboso
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind((host, porta))
        self._socket.listen()
        self.host = host
        self.porta = self._socket.getsockname()[1] 
        self._ativo = True

    def _log(self, *args):
        if self.verboso:
            print(*args, flush=True)

    def servir(self):
        self._log(f"{type(self).__name__} aguardando conexões TCP na porta {self.porta}...")
        while self._ativo:
            try:
                conexao, endereco = self._socket.accept()
            except OSError:
                break
            threading.Thread(target=self._atender_cliente, args=(conexao, endereco),
                             name=f"cliente-{endereco[1]}", daemon=True).start()

    def iniciar_em_segundo_plano(self):
        thread = threading.Thread(target=self.servir, name="accept", daemon=True)
        thread.start()
        return thread

    def parar(self):
        self._ativo = False
        try:
            self._socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self._socket.close()

    def _atender_cliente(self, conexao, endereco):
        self._log(f"[+] Cliente conectado: {endereco}")
        with conexao:
            try:
                while True:
                    requisicao = receber(conexao)
                    if requisicao is None:
                        break
                    self._log(f"    REQUEST  de {endereco}: {self._para_log(requisicao)}")
                    resposta = self.processar(requisicao, endereco)
                    self._log(f"    REPLY    para {endereco}: {resposta}")
                    enviar(conexao, resposta)              
            except (ConnectionError, ValueError, OSError) as erro:
                self._log(f"    Conexão com {endereco} encerrada com erro: {erro}")
        self._log(f"[-] Cliente desconectado: {endereco}")
        self.cliente_desconectado(endereco)

    @staticmethod
    def _para_log(requisicao):
        argumentos = requisicao.get("argumentos")
        if isinstance(argumentos, dict) and "senha" in argumentos:
            argumentos = {**argumentos, "senha": "***"}
            return {**requisicao, "argumentos": argumentos}
        return requisicao

    def processar(self, requisicao, endereco=None):
        try:
            operacao = requisicao["operacao"]
            argumentos = requisicao.get("argumentos") or {}
            resultado = self.executar(operacao, argumentos, endereco)
            return {"status": "OK", "resultado": resultado}
        except KeyError as erro:
            return {"status": "ERRO", "mensagem": f"Campo ausente na mensagem: {erro}"}
        except (ValueError, TypeError, PermissionError) as erro:
            return {"status": "ERRO", "mensagem": str(erro)}

    def executar(self, operacao, argumentos, endereco):
        raise NotImplementedError

    def cliente_desconectado(self, endereco):
        """Gancho opcional para as subclasses."""