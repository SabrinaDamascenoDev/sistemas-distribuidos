"""Testes da questão 3 (request/reply com serialização JSON sobre TCP)."""

import socket
import struct
import threading
import unittest

from models.exemplo import criar_loja_exemplo
from models.peca_de_roupa import Camiseta
from serialization.client import ClienteLoja, ErroRemoto
from serialization.protocolo import desempacotar, empacotar, receber
from serialization.server import ServidorLoja


class TesteProtocolo(unittest.TestCase):

    def test_empacotar_e_desempacotar(self):
        mensagem = {"operacao": "VENDER_PECA", "argumentos": {"codigo": 2, "texto": "Calça"}}
        self.assertEqual(desempacotar(empacotar(mensagem)), mensagem)

    def test_receber_mensagem_fragmentada(self):
        """O receptor junta os pedaços: TCP não preserva fronteiras de mensagem."""
        a, b = socket.socketpair()
        corpo = empacotar({"x": "á" * 1000})
        dados = struct.pack(">I", len(corpo)) + corpo

        def enviar_em_pedacos():
            for i in range(0, len(dados), 7):
                a.sendall(dados[i:i + 7])
            a.close()

        emissor = threading.Thread(target=enviar_em_pedacos)
        emissor.start()
        with b:
            self.assertEqual(receber(b), {"x": "á" * 1000})
            emissor.join(5)
            self.assertIsNone(receber(b))  # conexão encerrada -> None


class TesteClienteServidor(unittest.TestCase):

    def setUp(self):
        self.servidor = ServidorLoja("127.0.0.1", 0, criar_loja_exemplo(), verboso=False)
        self.servidor.iniciar_em_segundo_plano()

    def tearDown(self):
        self.servidor.parar()

    def _cliente(self):
        return ClienteLoja("127.0.0.1", self.servidor.porta, verboso=False)

    def test_fluxo_completo(self):
        with self._cliente() as cliente:
            self.assertEqual(len(cliente.listar_pecas()), 5)
            nova = cliente.adicionar_peca(Camiseta(6, "Polo", "Marca", "G", "verde", 100.0, 8, "curta"))
            self.assertIsInstance(nova, Camiseta)
            venda = cliente.vender_peca(6, 2)
            self.assertEqual(venda.valor_total, 200.0)
            self.assertEqual(cliente.total_vendas(), {"quantidade_vendas": 1, "total": 200.0})

    def test_erros_de_negocio(self):
        with self._cliente() as cliente:
            with self.assertRaisesRegex(ErroRemoto, "Estoque insuficiente"):
                cliente.vender_peca(4, 99)
            with self.assertRaisesRegex(ErroRemoto, "não encontrada"):
                cliente.vender_peca(999, 1)
            with self.assertRaisesRegex(ErroRemoto, "Já existe"):
                cliente.adicionar_peca(Camiseta(1, "Dup", "M", "P", "x", 1.0, 1, "curta"))
            with self.assertRaisesRegex(ErroRemoto, "desconhecida"):
                cliente.chamar("OPERACAO_INEXISTENTE")

    def test_vendas_concorrentes_nao_vendem_alem_do_estoque(self):
        sucessos, falhas = [], []

        def comprar():
            with self._cliente() as cliente:
                try:
                    sucessos.append(cliente.vender_peca(4, 1))  # jaqueta: estoque 3
                except ErroRemoto:
                    falhas.append(1)

        threads = [threading.Thread(target=comprar) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(5)
        self.assertEqual((len(sucessos), len(falhas)), (3, 7))


if __name__ == "__main__":
    unittest.main()