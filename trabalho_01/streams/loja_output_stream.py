"""
Envia, byte a byte, os dados de um conjunto (array/lista) de PecaDeRoupa
para um destino qualquer: System.out, arquivo ou conexão TCP.
"""

import io
import struct

class LojaOutputStream(io.RawIOBase):

    def __init__(self, destino, pecas, quantidade):
        super().__init__()
        self.destino = destino
        if quantidade < 0 or quantidade > len(pecas):
            self.destino = None  # nada a descarregar quando o objeto for finalizado
            raise ValueError(f"quantidade ({quantidade}) deve estar entre 0 e {len(pecas)}")
        self.pecas = pecas
        self.quantidade = quantidade

    def writable(self):
        return True

    def write(self, dados):
        self.destino.write(dados)
        return len(dados)

    def flush(self):
        if not self.closed and self.destino is not None and hasattr(self.destino, "flush"):
            self.destino.flush()

    def close(self):
        if not self.closed:
            try:
                self.flush()
            except ValueError: 
                pass
            super().close()

    def enviar(self):
        self.write(struct.pack(">i", self.quantidade))
        for peca in self.pecas[:self.quantidade]:
            self.write(self._empacotar_peca(peca))
        self.flush()

    @staticmethod
    def _texto(texto):
        dados = texto.encode("utf-8")
        return struct.pack(">H", len(dados)) + dados

    def _empacotar_peca(self, peca):
        return (
            self._texto(peca.tipo)
            + struct.pack(">i", peca.codigo)
            + self._texto(peca.nome)
            + self._texto(peca.marca)
            + self._texto(peca.tamanho)
            + self._texto(peca.cor)
            + struct.pack(">d", peca.preco)
            + struct.pack(">i", peca.quantidade)
            + self._texto(peca.detalhe)
        )