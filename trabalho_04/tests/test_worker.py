"""
Testes do worker da loja (sem rede): idempotência, recuperação do estado e mensagens
problemáticas. Rodar: python -m unittest discover -s tests -t .

O worker conversa com o broker pela interface do ClienteBroker (publicar, consumir, ack, nack).
Aqui um adaptador chama o BrokerFilas direto, sem HTTP, para os testes serem rápidos e
determinísticos. A queda do processo é simulada com QuedaSimulada no lugar de os._exit.
"""
import contextlib
import io
import os
import shutil
import tempfile
import time
import unittest
import uuid

from broker.fila_broker import BrokerFilas
from workers.worker_loja import FILA_COMANDOS, QuedaSimulada, WorkerLoja

FILA_RESPOSTA = "resp.teste"
CAMISETA = {"id_peca": 1, "nome": "Camiseta Polo", "preco": 89.9, "tamanho": "M"}
CALCA = {"id_peca": 2, "nome": "Calça Jeans", "preco": 120.5, "material": "Denim"}


class BrokerLocal:
    """Mesma interface do ClienteBroker, mas chamando o BrokerFilas direto (sem rede)."""

    def __init__(self, filas):
        self.filas = filas

    def publicar(self, fila, corpo):
        return self.filas.publicar(fila, corpo)

    def consumir(self, fila, visibilidade=10, espera=0):
        return self.filas.consumir(fila, visibilidade, espera)

    def ack(self, msg):
        return self.filas.ack(msg["id"], msg["recibo"])

    def nack(self, msg, reenfileirar=True, motivo=None):
        return self.filas.nack(msg["id"], msg["recibo"], reenfileirar, motivo)


def _queda_simulada():
    raise QuedaSimulada()


class TestWorker(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.filas = BrokerFilas(os.path.join(self.dir, "b.db"), max_tentativas=3)
        self.broker = BrokerLocal(self.filas)
        self.estado = os.path.join(self.dir, "estado.json")
        # O worker imprime cada comando; aqui isso só poluiria a saída dos testes.
        self._silencio = contextlib.redirect_stdout(io.StringIO())
        self._silencio.__enter__()

    def tearDown(self):
        self._silencio.__exit__(None, None, None)
        self.filas.fechar()
        shutil.rmtree(self.dir, ignore_errors=True)

    # ------------------------------------------------------------------ auxiliares
    def novo_worker(self, **kw):
        """Cria um worker que lê/grava o mesmo arquivo de estado (como um processo reiniciado)."""
        w = WorkerLoja(self.broker, self.estado, **kw)
        w.ao_falhar = _queda_simulada
        return w

    def enviar(self, metodo, argumentos=None):
        """Publica um comando como o ClienteLoja faria e devolve o id_comando."""
        id_comando = uuid.uuid4().hex
        self.filas.publicar(FILA_COMANDOS, {
            "id_comando": id_comando,
            "metodo": metodo,
            "argumentos": argumentos or {},
            "reply_to": FILA_RESPOSTA,
        })
        return id_comando

    def processar_proxima(self, worker, visibilidade=10):
        msg = self.broker.consumir(FILA_COMANDOS, visibilidade=visibilidade)
        self.assertIsNotNone(msg, "nenhum comando disponível na fila")
        worker.processar(msg)
        return msg

    def respostas(self):
        """Retira (e confirma) todas as respostas da fila do cliente, na ordem de chegada."""
        recebidas = []
        while True:
            msg = self.filas.consumir(FILA_RESPOSTA)
            if msg is None:
                return recebidas
            recebidas.append(msg["corpo"])
            self.filas.ack(msg["id"], msg["recibo"])

    # ---------------------------------------------------------------------- testes
    def test_executa_responde_em_reply_to_e_confirma(self):
        w = self.novo_worker()
        id_escrita = self.enviar("adicionar_camiseta", CAMISETA)
        id_leitura = self.enviar("consultar_estoque")
        self.processar_proxima(w)
        self.processar_proxima(w)

        escrita, leitura = self.respostas()
        self.assertEqual(escrita["id_comando"], id_escrita)
        self.assertEqual(escrita["resultado"]["status"], "sucesso")
        self.assertEqual(leitura["id_comando"], id_leitura)
        self.assertEqual(leitura["resultado"][0]["id_peca"], 1)
        # Os dois comandos receberam ack: nada sobrou em fila nenhuma.
        self.assertEqual(self.filas.estatisticas(), {})
        # Só a escrita é lembrada: reexecutar uma leitura numa reentrega é inofensivo.
        self.assertIn(id_escrita, w.processados)
        self.assertNotIn(id_leitura, w.processados)

    def test_reentrega_apos_queda_antes_do_ack_nao_duplica_venda(self):
        """Cenário 4 da demo: executou, salvou o estado e caiu antes de responder e dar ack."""
        w = self.novo_worker()
        self.enviar("adicionar_camiseta", CAMISETA)
        self.processar_proxima(w)
        self.respostas()

        w.falhar_antes_ack = True
        id_venda = self.enviar("registrar_venda", {"id_peca": 1, "quantidade": 2})
        with self.assertRaises(QuedaSimulada):
            self.processar_proxima(w, visibilidade=0.1)
        self.assertEqual(self.respostas(), [])  # caiu antes de responder

        time.sleep(0.25)  # o prazo de visibilidade vence e o broker reentrega
        w2 = self.novo_worker()  # worker reiniciado: estado vem do disco
        msg = self.processar_proxima(w2)

        self.assertEqual(msg["tentativa"], 2)
        self.assertEqual(len(w2.servico.vendas), 1)  # a venda NÃO foi registrada de novo
        [resposta] = self.respostas()  # a resposta guardada é reenviada ao cliente
        self.assertEqual(resposta["id_comando"], id_venda)
        self.assertEqual(resposta["resultado"]["venda"]["quantidade"], 2)
        self.assertEqual(self.filas.estatisticas(), {})

    def test_estado_e_recuperado_do_disco_ao_reiniciar(self):
        w = self.novo_worker()
        self.enviar("adicionar_camiseta", CAMISETA)
        self.enviar("adicionar_calca", CALCA)
        self.enviar("registrar_venda", {"id_peca": 1, "quantidade": 2})
        for _ in range(3):
            self.processar_proxima(w)

        w2 = self.novo_worker()
        estoque = w2.servico.consultar_estoque({})
        self.assertEqual([p["id_peca"] for p in estoque], [1, 2])
        self.assertEqual(estoque[1]["material"], "Denim")  # a subclasse foi reconstruída
        [venda] = w2.servico.consultar_vendas({})
        self.assertAlmostEqual(venda["total"], 2 * 89.9)
        # A venda continua apontando para o mesmo objeto que está no estoque (agregação).
        self.assertIs(w2.servico.vendas[0].peca_roupa, w2.servico.estoque.itens[0])
        self.assertEqual(list(w2.processados), list(w.processados))

    def test_mensagem_malformada_vai_para_dlq_e_a_fila_continua(self):
        self.filas.publicar(FILA_COMANDOS, {"metodo": "registrar_venda"})  # sem id_comando
        self.filas.publicar(FILA_COMANDOS, "isto nem é um objeto")
        id_ok = self.enviar("consultar_estoque")
        w = self.novo_worker()
        for _ in range(3):
            self.processar_proxima(w)

        na_dlq = self.filas.espiar("dlq." + FILA_COMANDOS)
        self.assertEqual(len(na_dlq), 2)
        self.assertTrue(all(m["motivo"] == "mensagem malformada" for m in na_dlq))
        [resposta] = self.respostas()  # o comando válido foi atendido normalmente
        self.assertEqual(resposta, {"id_comando": id_ok, "resultado": []})
        self.assertEqual(self.filas.estatisticas(), {"dlq.comandos": {"prontas": 2, "em_processamento": 0}})

    def test_erro_inesperado_devolve_comando_e_desfaz_alteracao_pela_metade(self):
        w = self.novo_worker()
        self.enviar("adicionar_camiseta", CAMISETA)
        self.processar_proxima(w)
        self.respostas()

        def quebrar_no_meio(argumentos):
            w.servico.vendas.append("venda pela metade")
            raise RuntimeError("falha simulada")

        w.servico.registrar_venda = quebrar_no_meio
        self.enviar("registrar_venda", {"id_peca": 1, "quantidade": 1})
        primeira = self.processar_proxima(w)

        self.assertEqual(w.servico.vendas, [])  # estado relido do disco: nada pela metade
        self.assertEqual(len(w.servico.estoque.itens), 1)
        self.assertEqual(self.respostas(), [])  # erro inesperado não vira resposta

        # O comando voltou para a fila na hora (sem esperar o prazo) e a nova tentativa funciona.
        segunda = self.processar_proxima(w)
        self.assertEqual(segunda["id"], primeira["id"])
        self.assertEqual(segunda["tentativa"], 2)
        self.assertEqual(len(w.servico.vendas), 1)
        [resposta] = self.respostas()
        self.assertEqual(resposta["resultado"]["status"], "sucesso")

    def test_pedido_invalido_responde_erro_sem_travar_a_fila(self):
        w = self.novo_worker()
        id_sem_tamanho = self.enviar("adicionar_camiseta", {"id_peca": 1, "nome": "X", "preco": 10.0})
        id_desconhecido = self.enviar("apagar_tudo")
        self.processar_proxima(w)
        self.processar_proxima(w)

        resultados = {r["id_comando"]: r["resultado"] for r in self.respostas()}
        self.assertEqual(resultados[id_sem_tamanho]["status"], "erro")
        self.assertIn("argumentos inválidos", resultados[id_sem_tamanho]["mensagem"])
        self.assertEqual(resultados[id_desconhecido],
                         {"status": "erro", "mensagem": "método desconhecido: apagar_tudo"})
        # Erro do cliente não é falha do worker: os comandos são confirmados e não vão para a DLQ.
        self.assertEqual(self.filas.estatisticas(), {})
        self.assertEqual(w.servico.estoque.itens, [])


if __name__ == "__main__":
    unittest.main()