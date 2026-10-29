"""Testes da questão extra (sistema de votação)."""

import threading
import time
import unittest

from serialization.cliente_base import ErroRemoto
from votacao.cliente import ClienteVotacao, OuvinteNotas
from votacao.modelo import Candidato, Urna, VotacaoEncerrada
from votacao.servidor import ServidorVotacao


class Relogio:
    def __init__(self):
        self.agora = 1000.0

    def __call__(self):
        return self.agora


class TesteUrna(unittest.TestCase):

    def setUp(self):
        self.relogio = Relogio()
        self.urna = Urna(60, [Candidato(10, "A"), Candidato(20, "B"), Candidato(30, "C")],
                         relogio=self.relogio)

    def test_apuracao_com_percentuais_e_vencedor(self):
        for eleitor, numero in [("e1", 10), ("e2", 10), ("e3", 20), ("e4", 10)]:
            self.urna.votar(eleitor, numero)
        self.relogio.agora += 61
        resultado = self.urna.resultado()
        self.assertFalse(resultado["parcial"])
        self.assertEqual(resultado["total_votos"], 4)
        self.assertEqual([(l["numero"], l["votos"], l["percentual"]) for l in resultado["apuracao"]],
                         [(10, 3, 75.0), (20, 1, 25.0), (30, 0, 0.0)])
        self.assertEqual(resultado["vencedor"]["numero"], 10)

    def test_voto_duplicado_e_candidato_inexistente(self):
        self.urna.votar("e1", 10)
        with self.assertRaises(PermissionError):
            self.urna.votar("e1", 20)
        with self.assertRaises(ValueError):
            self.urna.votar("e2", 99)

    def test_prazo(self):
        with self.assertRaises(PermissionError):
            self.urna.resultado()           # ainda aberta
        self.relogio.agora += 61
        with self.assertRaises(VotacaoEncerrada):
            self.urna.votar("e1", 10)
        with self.assertRaises(VotacaoEncerrada):
            self.urna.adicionar_candidato("D")

    def test_empate_e_sem_votos(self):
        self.relogio.agora += 61
        self.assertEqual(self.urna.resultado()["situacao"], "SEM_VOTOS")
        urna = Urna(60, [Candidato(1, "A"), Candidato(2, "B")], relogio=self.relogio)
        urna.votar("e1", 1)
        urna.votar("e2", 2)
        self.relogio.agora += 61
        resultado = urna.resultado()
        self.assertEqual(resultado["situacao"], "EMPATE")
        self.assertEqual(len(resultado["empatados"]), 2)

    def test_remover_candidato_libera_eleitores(self):
        self.urna.votar("e1", 30)
        candidato, liberados = self.urna.remover_candidato(30)
        self.assertEqual((candidato.numero, liberados), (30, ["e1"]))
        self.urna.votar("e1", 10)            # pode votar de novo
        self.assertEqual(self.urna.total_votos(), 1)


class TesteServidorVotacao(unittest.TestCase):

    def setUp(self):
        self.servidor = ServidorVotacao("127.0.0.1", 0, duracao=1.5, grupo="230.0.0.2",
                                        porta_multicast=6101, verboso=False)
        self.servidor.iniciar_em_segundo_plano()
        self.abertos = []

    def tearDown(self):
        for item in self.abertos:
            (item.encerrar if isinstance(item, OuvinteNotas) else item.fechar)()
        self.servidor.parar()

    def _login(self, usuario, senha="123"):
        cliente = ClienteVotacao("127.0.0.1", self.servidor.porta)
        self.abertos.append(cliente)
        cliente.login(usuario, senha)
        return cliente

    def test_fluxo_completo(self):
        admin = self._login("admin", "admin")
        eleitores = [self._login(f"eleitor{i}") for i in range(1, 5)]
        self.assertEqual([c["numero"] for c in eleitores[0].sessao["candidatos"]], [10, 20, 30])

        ouvinte = OuvinteNotas("230.0.0.2", 6101, saida=lambda _t: None)
        self.abertos.append(ouvinte)
        time.sleep(0.1)
        admin.adicionar_candidato("Novo", "Chapa N", 40)
        admin.enviar_nota("Debate hoje")

        votos = [10, 10, 20, 40]
        threads = [threading.Thread(target=c.votar, args=(n,)) for c, n in zip(eleitores, votos)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(5)

        with self.assertRaisesRegex(ErroRemoto, "já votou"):
            eleitores[0].votar(20)
        with self.assertRaisesRegex(ErroRemoto, "ADMIN"):
            eleitores[1].enviar_nota("hack")
        with self.assertRaisesRegex(ErroRemoto, "em andamento"):
            eleitores[2].resultado()
        self.assertTrue(admin.resultado()["parcial"])

        self.assertTrue(self.servidor.encerrada.wait(5))
        with self.assertRaisesRegex(ErroRemoto, "encerrada"):
            self._login("eleitor9").votar(10)

        resultado = eleitores[3].resultado()
        self.assertEqual(resultado["total_votos"], 4)
        self.assertEqual(resultado["vencedor"]["numero"], 10)
        self.assertEqual(resultado["apuracao"][0]["percentual"], 50.0)
        self.assertEqual([n["mensagem"] for n in ouvinte.notas], ["Debate hoje"])

    def test_login_invalido_e_token_invalido(self):
        cliente = ClienteVotacao("127.0.0.1", self.servidor.porta)
        self.abertos.append(cliente)
        with self.assertRaisesRegex(ErroRemoto, "inválidos"):
            cliente.login("eleitor1", "errada")
        with self.assertRaisesRegex(ErroRemoto, "Sessão inválida"):
            cliente.chamar("LISTAR_CANDIDATOS", {"token": "abc"})


if __name__ == "__main__":
    unittest.main()