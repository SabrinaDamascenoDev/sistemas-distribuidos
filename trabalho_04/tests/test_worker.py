"""Testes do broker de filas (sem rede). Rodar: python -m unittest discover -s tests -t ."""
import os
import shutil
import sqlite3
import tempfile
import threading
import time
import unittest

from broker.fila_broker import BrokerFilas


class TestBroker(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.db = os.path.join(self.dir, "b.db")
        self.b = BrokerFilas(self.db, max_tentativas=3)

    def tearDown(self):
        try:
            self.b.fechar()
        except sqlite3.ProgrammingError:
            pass
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_fifo(self):
        for i in range(3):
            self.b.publicar("f", {"n": i})
        ns = []
        for _ in range(3):
            m = self.b.consumir("f")
            ns.append(m["corpo"]["n"])
            self.assertTrue(self.b.ack(m["id"], m["recibo"]))
        self.assertEqual(ns, [0, 1, 2])

    def test_fila_vazia_devolve_none(self):
        self.assertIsNone(self.b.consumir("nao-existe"))

    def test_filas_sao_independentes(self):
        self.b.publicar("a", {"x": 1})
        self.assertIsNone(self.b.consumir("b"))
        self.assertEqual(self.b.consumir("a")["corpo"], {"x": 1})

    def test_mensagem_em_processamento_fica_invisivel(self):
        self.b.publicar("f", {"n": 1})
        self.assertIsNotNone(self.b.consumir("f", visibilidade=5))
        self.assertIsNone(self.b.consumir("f"))

    def test_sem_ack_volta_apos_visibility_timeout(self):
        self.b.publicar("f", {"n": 1})
        primeira = self.b.consumir("f", visibilidade=0.2)
        time.sleep(0.3)
        segunda = self.b.consumir("f")
        self.assertEqual(segunda["id"], primeira["id"])
        self.assertEqual(segunda["tentativa"], 2)

    def test_persistencia_apos_fechar_e_reabrir(self):
        self.b.publicar("f", {"pedido": 42})
        self.b.fechar()
        reaberto = BrokerFilas(self.db)
        try:
            self.assertEqual(reaberto.consumir("f")["corpo"], {"pedido": 42})
        finally:
            reaberto.fechar()

    def test_ack_com_recibo_vencido_nao_apaga(self):
        """Consumidor atrasado não pode apagar a mensagem que já foi reentregue a outro."""
        self.b.publicar("f", {"n": 1})
        atrasado = self.b.consumir("f", visibilidade=0.1)
        time.sleep(0.2)
        atual = self.b.consumir("f", visibilidade=5)
        self.assertFalse(self.b.ack(atrasado["id"], atrasado["recibo"]))
        self.assertTrue(self.b.ack(atual["id"], atual["recibo"]))
        self.assertEqual(self.b.estatisticas(), {})

    def test_nack_reenfileira_na_hora(self):
        self.b.publicar("f", {"n": 1})
        m = self.b.consumir("f", visibilidade=60)
        self.assertTrue(self.b.nack(m["id"], m["recibo"], reenfileirar=True))
        de_novo = self.b.consumir("f")
        self.assertEqual(de_novo["id"], m["id"])
        self.assertEqual(de_novo["tentativa"], 2)

    def test_nack_sem_reenfileirar_vai_para_dlq(self):
        self.b.publicar("f", {"n": 1})
        m = self.b.consumir("f")
        self.b.nack(m["id"], m["recibo"], reenfileirar=False, motivo="formato inválido")
        self.assertIsNone(self.b.consumir("f"))
        [na_dlq] = self.b.espiar("dlq.f")
        self.assertEqual(na_dlq["motivo"], "formato inválido")
        self.assertEqual(na_dlq["corpo"], {"n": 1})

    def test_mensagem_venenosa_vai_para_dlq_apos_limite(self):
        """Simula um consumidor que morre toda vez (nunca dá ack): não pode travar a fila."""
        self.b.publicar("f", {"veneno": True})
        self.b.publicar("f", {"normal": True})
        for tentativa in (1, 2, 3):
            m = self.b.consumir("f", visibilidade=0.05)
            self.assertEqual((m["corpo"], m["tentativa"]), ({"veneno": True}, tentativa))
            time.sleep(0.1)
        seguinte = self.b.consumir("f")
        self.assertEqual(seguinte["corpo"], {"normal": True})  # a fila andou
        self.assertEqual(self.b.espiar("dlq.f")[0]["corpo"], {"veneno": True})

    def test_long_polling_recebe_mensagem_publicada_durante_a_espera(self):
        threading.Timer(0.2, self.b.publicar, args=("f", {"n": 1})).start()
        inicio = time.time()
        m = self.b.consumir("f", espera=3)
        self.assertEqual(m["corpo"], {"n": 1})
        self.assertLess(time.time() - inicio, 1.0)  # acordou na hora, não esperou os 3 s

    def test_long_polling_respeita_o_prazo(self):
        inicio = time.time()
        self.assertIsNone(self.b.consumir("f", espera=0.3))
        self.assertGreaterEqual(time.time() - inicio, 0.3)

    def test_long_polling_nao_retira_para_consumidor_que_sumiu(self):
        self.b.publicar("f", {"n": 1})
        self.assertIsNone(self.b.consumir("f", espera=1, ativo=lambda: False))
        self.assertEqual(self.b.estatisticas()["f"], {"prontas": 1, "em_processamento": 0})

    def test_estatisticas(self):
        self.b.publicar("f", {"n": 1})
        self.b.publicar("f", {"n": 2})
        self.b.consumir("f", visibilidade=60)
        self.assertEqual(self.b.estatisticas(), {"f": {"prontas": 1, "em_processamento": 1}})

    def test_migra_banco_criado_pela_versao_anterior(self):
        antigo = os.path.join(self.dir, "antigo.db")
        con = sqlite3.connect(antigo)
        con.execute("CREATE TABLE mensagens (id INTEGER PRIMARY KEY AUTOINCREMENT, fila TEXT NOT NULL, "
                    "corpo TEXT NOT NULL, visivel_em REAL NOT NULL DEFAULT 0)")
        con.execute("INSERT INTO mensagens (fila, corpo) VALUES ('f', '{\"velha\": true}')")
        con.commit()
        con.close()
        b = BrokerFilas(antigo)
        try:
            m = b.consumir("f")
            self.assertEqual(m["corpo"], {"velha": True})
            self.assertTrue(b.ack(m["id"], m["recibo"]))
        finally:
            b.fechar()


if __name__ == "__main__":
    unittest.main()