"""Esqueleto de testes (TODO da dupla). Rodar: python -m unittest discover -s tests -t ."""
import os
import tempfile
import unittest

from broker.fila_broker import BrokerFilas


class TestBroker(unittest.TestCase):
    def setUp(self):
        self.b = BrokerFilas(os.path.join(tempfile.mkdtemp(), "b.db"))

    def test_fifo(self):  # exemplo pronto
        for i in range(3):
            self.b.publicar("f", {"n": i})
        ns = []
        for _ in range(3):
            m = self.b.consumir("f")
            ns.append(m["corpo"]["n"])
            self.b.ack(m["id"])
        self.assertEqual(ns, [0, 1, 2])

    # TODO: fila vazia devolve None
    # TODO: mensagem sem ack volta após o visibility timeout (use visibilidade=0.2 e time.sleep)
    # TODO: mensagem sobrevive a fechar e reabrir o BrokerFilas (persistência)


if __name__ == "__main__":
    unittest.main()
