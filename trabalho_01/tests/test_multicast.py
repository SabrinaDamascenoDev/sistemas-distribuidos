"""Testes da questão 4 (autenticação TCP + mensagens UDP multicast)."""

import time
import unittest

from multicast import mensagens
from multicast.cliente import ClienteNotificacoes
from multicast.grupo import validar_grupo
from multicast.servidor import ServidorNotificacoes
from serialization.cliente_base import ErroRemoto

GRUPO = "230.0.0.1"
PORTA_MC = 5107  # diferente da padrão para não interferir em uma demonstração aberta


def esperar(condicao, limite=3.0):
    fim = time.time() + limite
    while time.time() < fim:
        if condicao():
            return True
        time.sleep(0.05)
    return condicao()


class TesteMensagens(unittest.TestCase):

    def test_formato(self):
        msg = mensagens.criar_mensagem("alerta", "Estoque baixo", seq=3, timestamp=123456789)
        self.assertEqual(msg, {"tipo": "ALERTA", "mensagem": "Estoque baixo",
                               "timestamp": 123456789, "seq": 3})
        self.assertEqual(mensagens.desempacotar(mensagens.empacotar(msg)), msg)

    def test_tipo_invalido(self):
        with self.assertRaises(ValueError):
            mensagens.criar_mensagem("SPAM", "x")

    def test_endereco_classe_d(self):
        self.assertEqual(validar_grupo("230.0.0.1"), "230.0.0.1")
        with self.assertRaises(ValueError):
            validar_grupo("192.168.0.1")


class TesteMulticast(unittest.TestCase):

    def setUp(self):
        self.servidor = ServidorNotificacoes("127.0.0.1", 0, GRUPO, PORTA_MC, verboso=False)
        self.servidor.iniciar_em_segundo_plano()
        self.clientes = []

    def tearDown(self):
        for cliente in self.clientes:
            cliente.encerrar()
        self.servidor.parar()

    def _cliente(self, nome):
        cliente = ClienteNotificacoes(nome, saida=lambda _t: None)
        dados = cliente.autenticar("127.0.0.1", self.servidor.porta, nome, "123")
        self.assertEqual((dados["grupo"], dados["porta"]), (GRUPO, PORTA_MC))
        cliente.iniciar_escuta()
        self.clientes.append(cliente)
        return cliente

    @staticmethod
    def _textos(cliente):
        return [m["mensagem"] for m in cliente.historico]

    def test_autenticacao_recusada(self):
        with self.assertRaises(ErroRemoto):
            ClienteNotificacoes().autenticar("127.0.0.1", self.servidor.porta, "ana", "errada")

    def test_varios_clientes_recebem_e_leave_join(self):
        ana, bruno, carla = (self._cliente(n) for n in ("ana", "bruno", "carla"))
        time.sleep(0.2)

        for tipo in mensagens.TIPOS:
            self.servidor.publicar(tipo, f"msg {tipo}")
        for cliente in (ana, bruno, carla):
            self.assertTrue(esperar(lambda c=cliente: all(f"msg {t}" in self._textos(c)
                                                          for t in mensagens.TIPOS)))

        bruno.sair()                                     # leaveGroup
        self.servidor.publicar(mensagens.ALERTA, "sem bruno")
        self.assertTrue(esperar(lambda: "sem bruno" in self._textos(ana)
                                and "sem bruno" in self._textos(carla)))
        time.sleep(0.3)
        self.assertNotIn("sem bruno", self._textos(bruno))

        bruno.entrar()                                   # joinGroup
        self.servidor.publicar(mensagens.ATUALIZACAO, "com bruno")
        self.assertTrue(esperar(lambda: "com bruno" in self._textos(bruno)))

    def test_rajada_concorrente(self):
        ana = self._cliente("ana")
        time.sleep(0.2)
        enviadas = self.servidor.rajada(20)
        self.assertEqual(len({m["seq"] for m in enviadas}), 20)  # sequência sem repetição
        self.assertTrue(esperar(lambda: sum("rajada" in t for t in self._textos(ana)) == 20))


if __name__ == "__main__":
    unittest.main()