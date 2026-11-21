"""Testes de integração: cliente, broker HTTP e worker de verdade (em threads)."""
import os
import shutil
import tempfile
import threading
import time
import unittest

from broker.fila_broker import BrokerFilas
from broker.servidor_http import ServidorBroker
from client.cliente_loja import ClienteLoja
from mq.cliente_broker import ClienteBroker, ErroBroker, RequisicaoInvalida
from workers.worker_loja import WorkerLoja


class TestIntegracao(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.fila = BrokerFilas(os.path.join(self.dir, "b.db"))
        self.servidor = self._subir_servidor(0)  # porta 0 = qualquer porta livre
        self.url = f"http://127.0.0.1:{self.servidor.porta}"
        self.workers = []
        self.clientes = []

    def tearDown(self):
        for w, t in self.workers:
            w.parar()
            t.join(timeout=3)
        for c in self.clientes:
            c.fechar()
        self.servidor.parar()
        self.fila.fechar()
        shutil.rmtree(self.dir, ignore_errors=True)

    def _subir_servidor(self, porta):
        s = ServidorBroker(self.fila, "127.0.0.1", porta)
        threading.Thread(target=s.iniciar, daemon=True).start()
        return s

    def broker(self):
        b = ClienteBroker(self.url)
        self.clientes.append(b)
        return b

    def loja(self, **kw):
        c = ClienteLoja(self.url, **kw)
        self.clientes.append(c)
        return c

    def subir_worker(self):
        w = WorkerLoja(ClienteBroker(self.url), os.path.join(self.dir, "estado.json"), espera=0.5)
        t = threading.Thread(target=w.rodar, daemon=True)
        t.start()
        self.workers.append((w, t))
        return w

    def test_request_reply_pelo_broker(self):
        self.subir_worker()
        cli = self.loja()
        r = cli.chamar("adicionar_calca", {"id_peca": 9, "nome": "Jeans", "preco": 100.0, "material": "Denim"})
        self.assertEqual(r["status"], "sucesso")
        self.assertEqual(cli.chamar("consultar_estoque")[0]["id_peca"], 9)

    def test_envio_com_worker_desligado_e_resposta_quando_ele_volta(self):
        cli = self.loja()
        id_cmd = cli.enviar("consultar_estoque")             # ninguém consumindo
        self.assertIsNone(cli.esperar(id_cmd, timeout=0.3))  # sem resposta ainda...
        self.subir_worker()
        self.assertEqual(cli.esperar(id_cmd, timeout=5), [])  # ...mas nada se perdeu

    def test_cliente_descarta_resposta_duplicada(self):
        cli = self.loja(espera=0.2)
        id_cmd = cli.enviar("consultar_estoque")
        for _ in range(2):  # worker reenviou a resposta numa reentrega
            self.fila.publicar(cli.fila_resposta, {"id_comando": id_cmd, "resultado": "ok"})
        self.assertEqual(cli.esperar(id_cmd, timeout=2), "ok")
        self.assertEqual(cli.coletar_respostas(), {})

    def test_long_polling_http_entrega_assim_que_publica(self):
        b = self.broker()
        outro = self.broker()
        threading.Timer(0.3, outro.publicar, args=("f", {"n": 1})).start()
        inicio = time.time()
        m = b.consumir("f", espera=5)
        self.assertEqual(m["corpo"], {"n": 1})
        self.assertLess(time.time() - inicio, 2.0)

    def test_keep_alive_reaproveita_conexao(self):
        b = self.broker()
        antes = b.metricas()["conexoes_tcp"]
        for i in range(20):
            b.publicar("f", {"n": i})
        self.assertEqual(b.metricas()["conexoes_tcp"], antes)  # nenhuma conexão nova

    def test_reconecta_sozinho_quando_o_broker_reinicia(self):
        b = self.broker()
        b.publicar("f", {"n": 1})  # conexão persistente aberta
        porta = self.servidor.porta
        self.servidor.parar()
        with self.assertRaises(ErroBroker):
            b.publicar("f", {"n": 2})  # broker fora: erro explícito
        self.servidor = self._subir_servidor(porta)
        b.publicar("f", {"n": 3})      # voltou: funciona sem recriar o cliente
        self.assertEqual(self.fila.estatisticas()["f"]["prontas"], 2)

    def test_requisicao_invalida_recebe_400(self):
        with self.assertRaises(RequisicaoInvalida):
            self.broker()._requisitar("POST", "/publicar", {"corpo": {}})  # sem fila


if __name__ == "__main__":
    unittest.main()