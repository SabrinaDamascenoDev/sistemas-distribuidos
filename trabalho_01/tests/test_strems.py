"""Testes das questões 1 e 2 (LojaOutputStream / LojaInputStream)."""

import io
import os
import socket
import subprocess
import sys
import threading
import unittest

from models.exemplo import criar_loja_exemplo
from streams.loja_input_stream import LojaInputStream
from streams.loja_output_stream import LojaOutputStream

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _resumo(pecas):
    return [(p.tipo, p.codigo, p.nome, p.marca, p.tamanho, p.cor, p.preco, p.quantidade, p.detalhe)
            for p in pecas]


class TesteStreams(unittest.TestCase):

    def setUp(self):
        self.pecas = criar_loja_exemplo().pecas

    def _ida_e_volta(self, quantidade):
        buffer = io.BytesIO()
        LojaOutputStream(buffer, self.pecas, quantidade).enviar()
        buffer.seek(0)
        return LojaInputStream(buffer).ler_pecas()

    def test_todas_as_pecas_ida_e_volta(self):
        self.assertEqual(_resumo(self._ida_e_volta(len(self.pecas))), _resumo(self.pecas))

    def test_envia_apenas_a_quantidade_pedida(self):
        self.assertEqual(_resumo(self._ida_e_volta(2)), _resumo(self.pecas[:2]))
        self.assertEqual(self._ida_e_volta(0), [])

    def test_quantidade_invalida(self):
        with self.assertRaises(ValueError):
            LojaOutputStream(io.BytesIO(), self.pecas, len(self.pecas) + 1)
        with self.assertRaises(ValueError):
            LojaOutputStream(io.BytesIO(), self.pecas, -1)

    def test_fluxo_truncado_gera_eoferror(self):
        buffer = io.BytesIO()
        LojaOutputStream(buffer, self.pecas, len(self.pecas)).enviar()
        truncado = io.BytesIO(buffer.getvalue()[:-5])
        with self.assertRaises(EOFError):
            LojaInputStream(truncado).ler_pecas()

    def test_tcp(self):
        """1-d + 2-d: envio e leitura do mesmo formato através de um socket TCP."""
        servidor = socket.create_server(("127.0.0.1", 0))
        porta = servidor.getsockname()[1]
        recebidas = []

        def receber():
            conexao, _ = servidor.accept()
            with conexao, conexao.makefile("rb") as origem:
                recebidas.extend(LojaInputStream(origem).ler_pecas())

        thread = threading.Thread(target=receber)
        thread.start()
        with socket.create_connection(("127.0.0.1", porta)) as sock, sock.makefile("wb") as destino:
            with LojaOutputStream(destino, self.pecas, len(self.pecas)) as saida:
                saida.enviar()
        thread.join(5)
        servidor.close()
        self.assertEqual(_resumo(recebidas), _resumo(self.pecas))

    def test_pipe_saida_padrao_para_entrada_padrao(self):
        """1-b + 2-b: python -m demos_stream.q1b | python -m demos_stream.q2b"""
        produtor = subprocess.run([sys.executable, "-m", "demos_stream.q1b"], cwd=RAIZ,
                                  capture_output=True, check=True)
        consumidor = subprocess.run([sys.executable, "-m", "demos_stream.q2b"], cwd=RAIZ,
                                    input=produtor.stdout, capture_output=True, check=True)
        self.assertIn("Recebi 5 peças", consumidor.stdout.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()