"""
Lê os bytes gerados pelo LojaOutputStream (mesmo formato descrito lá) e
reconstrói a lista de objetos PecaDeRoupa (desempacotamento / unmarshalling).
"""

import io
import struct

from models.peca_de_roupa import criar_peca


class LojaInputStream(io.RawIOBase):

    def __init__(self, origem):
        super().__init__()
        self.origem = origem


    def readable(self):
        return True

    def readinto(self, buffer):
        dados = self.origem.read(len(buffer))
        tamanho = len(dados)
        buffer[:tamanho] = dados
        return tamanho

    def ler_pecas(self):
        quantidade = self._ler_int()
        return [self._ler_peca() for _ in range(quantidade)]

    def _ler_exato(self, n):
        partes = []
        faltam = n
        while faltam > 0:
            parte = self.read(faltam)
            if not parte:
                raise EOFError("O fluxo terminou antes de chegarem todos os bytes esperados")
            partes.append(parte)
            faltam -= len(parte)
        return b"".join(partes)

    def _ler_int(self):
        return struct.unpack(">i", self._ler_exato(4))[0]

    def _ler_double(self):
        return struct.unpack(">d", self._ler_exato(8))[0]

    def _ler_texto(self):
        tamanho = struct.unpack(">H", self._ler_exato(2))[0]
        return self._ler_exato(tamanho).decode("utf-8")

    def _ler_peca(self):
        tipo = self._ler_texto()
        codigo = self._ler_int()
        nome = self._ler_texto()
        marca = self._ler_texto()
        tamanho = self._ler_texto()
        cor = self._ler_texto()
        preco = self._ler_double()
        quantidade = self._ler_int()
        detalhe = self._ler_texto()
        return criar_peca(tipo, codigo, nome, marca, tamanho, cor, preco, quantidade, detalhe)