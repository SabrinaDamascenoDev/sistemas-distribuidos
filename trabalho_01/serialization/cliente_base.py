"""
Cliente request-reply genérico sobre TCP (reaproveitado pelas questões 3, 4 e extra).

Para cada chamada remota:
  1. monta o request {"operacao", "argumentos"} e o EMPACOTA (dict -> bytes JSON)
  2. envia com o cabeçalho de tamanho e espera o reply
  3. DESEMPACOTA o reply (bytes -> dict) e devolve o "resultado"
     (ou levanta ErroRemoto se o servidor respondeu status ERRO)
"""

import socket
import threading

from serialization.protocolo import empacotar, enviar, receber


class ErroRemoto(Exception):
    """O servidor respondeu com status ERRO."""


class ClienteTCP:

    def __init__(self, host, porta, verboso=False, timeout=None):
        self.verboso = verboso
        self._socket = socket.create_connection((host, porta), timeout=timeout)
        self._socket.settimeout(None)
        self._trava = threading.Lock()  

    def fechar(self):
        try:
            self._socket.close()
        except OSError:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.fechar()

    def chamar(self, operacao, argumentos=None):
        requisicao = {"operacao": operacao, "argumentos": argumentos or {}}
        if self.verboso:
            corpo = empacotar(requisicao)
            exibicao = requisicao
            if "senha" in requisicao["argumentos"]:
                exibicao = {**requisicao, "argumentos": {**requisicao["argumentos"], "senha": "***"}}
            print(f"   Empacotado ({len(corpo)} bytes): {empacotar(exibicao).decode('utf-8')}")

        with self._trava:
            enviar(self._socket, requisicao)
            resposta = receber(self._socket)
        if resposta is None:
            raise ConnectionError("O servidor encerrou a conexão")

        if self.verboso:
            print(f"   Desempacotado: {resposta}")
        if resposta.get("status") != "OK":
            raise ErroRemoto(resposta.get("mensagem", "erro desconhecido"))
        return resposta.get("resultado")