"""
QUESTÃO EXTRA - Servidor do sistema de votação.

  * TCP unicast (porta 6000), uma thread por cliente: login, lista de
    candidatos, votos, gestão de candidatos e consulta do resultado.
  * UDP multicast (grupo 230.0.0.2, porta 6001): usado EXCLUSIVAMENTE para as
    notas informativas enviadas pelos administradores.
  * Representação externa de dados: JSON (aceito pelo enunciado como
    alternativa a protocol buffers), com cabeçalho de 4 bytes de tamanho
    (serialization/protocolo.py).
  * Prazo: um threading.Timer encerra a urna; depois disso o servidor recusa
    votos e calcula total, percentuais e vencedor.

Operações (request {"operacao", "argumentos"}):
    LOGIN               usuario, senha         -> token, papel, candidatos, prazo, grupo multicast
    LISTAR_CANDIDATOS   token
    VOTAR               token, numero          (eleitor)
    STATUS              token
    RESULTADO           token                  (eleitor: só após o prazo; admin: parcial antes)
    ADICIONAR_CANDIDATO token, nome, partido   (admin)
    REMOVER_CANDIDATO   token, numero          (admin)
    ENVIAR_NOTA         token, texto           (admin -> multicast)
    LOGOUT              token

Executar:  python -m votacao.servidor --duracao 120
"""

import argparse
import hashlib
import hmac
import json
import secrets
import threading
import time

from multicast.grupo import criar_socket_emissor, validar_grupo
from serialization.servidor_base import ServidorTCP
from votacao.modelo import Candidato, Urna, formatar_resultado

PORTA_PADRAO = 6000
GRUPO_PADRAO = "230.0.0.2"
PORTA_MULTICAST_PADRAO = 6001

ELEITOR = "ELEITOR"
ADMIN = "ADMIN"

CANDIDATOS_INICIAIS = (
    Candidato(10, "Ana Ribeiro", "Chapa Integração"),
    Candidato(20, "Bruno Teixeira", "Chapa Inovação"),
    Candidato(30, "Carla Menezes", "Chapa Participação"),
)


def usuarios_padrao(quantidade_eleitores=10):
    usuarios = {f"eleitor{i}": ("123", ELEITOR) for i in range(1, quantidade_eleitores + 1)}
    usuarios["admin"] = ("admin", ADMIN)
    return usuarios


def _hash(senha):
    return hashlib.sha256(senha.encode("utf-8")).hexdigest()


def empacotar_nota(nota):
    return json.dumps(nota, ensure_ascii=False).encode("utf-8")


def desempacotar_nota(dados):
    nota = json.loads(dados.decode("utf-8"))
    if not isinstance(nota, dict) or nota.get("tipo") != "NOTA_INFORMATIVA":
        raise ValueError("Datagrama com formato desconhecido")
    return nota


class ServidorVotacao(ServidorTCP):

    def __init__(self, host="0.0.0.0", porta=PORTA_PADRAO, duracao=120.0,
                 grupo=GRUPO_PADRAO, porta_multicast=PORTA_MULTICAST_PADRAO,
                 usuarios=None, candidatos=CANDIDATOS_INICIAIS, ttl=1, interface=None,
                 verboso=True):
        super().__init__(host, porta, verboso)
        self.urna = Urna(duracao, [Candidato(c.numero, c.nome, c.partido) for c in candidatos])
        self.grupo = validar_grupo(grupo)
        self.porta_multicast = porta_multicast
        self._emissor = criar_socket_emissor(ttl, interface)
        self._usuarios = {u: (_hash(s), papel) for u, (s, papel) in (usuarios or usuarios_padrao()).items()}
        self._sessoes = {}                      # token -> (usuario, papel)
        self._trava_sessoes = threading.Lock()
        self._seq_notas = 0
        self._trava_notas = threading.Lock()
        self.encerrada = threading.Event()
        self._timer = threading.Timer(duracao, self._encerrar_votacao)
        self._timer.daemon = True
        self._timer.start()

    # ---------- prazo ----------
    def _encerrar_votacao(self):
        resultado = self.urna.encerrar()
        self.encerrada.set()
        self._log("\n> Prazo encerrado: a urna não aceita mais votos.")
        self._log(formatar_resultado(resultado))

    # ---------- sessões ----------
    def _sessao(self, args, papel_exigido=None):
        with self._trava_sessoes:
            sessao = self._sessoes.get(args.get("token"))
        if sessao is None:
            raise PermissionError("Sessão inválida: faça login novamente")
        usuario, papel = sessao
        if papel_exigido and papel != papel_exigido:
            raise PermissionError(f"Operação permitida apenas para {papel_exigido}")
        return usuario, papel

    def _estado(self, usuario=None, papel=None):
        estado = {"aberta": self.urna.aberta(),
                  "prazo": self.urna.prazo,
                  "segundos_restantes": round(self.urna.segundos_restantes(), 1),
                  "total_votos": self.urna.total_votos()}
        if papel == ELEITOR:
            estado["ja_votou"] = self.urna.ja_votou(usuario)
        return estado

    # ---------- despacho das operações ----------
    def executar(self, operacao, args, endereco=None):
        if operacao == "LOGIN":
            return self._login(str(args["usuario"]), str(args["senha"]))

        usuario, papel = self._sessao(args)

        if operacao == "LISTAR_CANDIDATOS":
            return [c.para_dict() for c in self.urna.listar_candidatos()]

        if operacao == "STATUS":
            return self._estado(usuario, papel)

        if operacao == "VOTAR":
            self._sessao(args, ELEITOR)
            candidato = self.urna.votar(usuario, int(args["numero"]))
            self._log(f"    [voto] {usuario} votou (total {self.urna.total_votos()})")
            return {"candidato": candidato.para_dict(),
                    "comprovante": secrets.token_hex(6),
                    "horario": time.strftime("%H:%M:%S")}

        if operacao == "RESULTADO":
            return self.urna.parcial() if papel == ADMIN else self.urna.resultado()

        if operacao == "ADICIONAR_CANDIDATO":
            self._sessao(args, ADMIN)
            candidato = self.urna.adicionar_candidato(args["nome"], args.get("partido", ""),
                                                      args.get("numero"))
            self._log(f"    [admin] {usuario} adicionou {candidato}")
            return candidato.para_dict()

        if operacao == "REMOVER_CANDIDATO":
            self._sessao(args, ADMIN)
            candidato, liberados = self.urna.remover_candidato(int(args["numero"]))
            self._log(f"    [admin] {usuario} removeu {candidato}")
            return {"removido": candidato.para_dict(), "votos_anulados": len(liberados)}

        if operacao == "ENVIAR_NOTA":
            self._sessao(args, ADMIN)
            return self.enviar_nota(usuario, str(args["texto"]))

        if operacao == "LOGOUT":
            with self._trava_sessoes:
                self._sessoes.pop(args["token"], None)
            return {"encerrado": True}

        raise ValueError(f"Operação desconhecida: {operacao}")

    def _login(self, usuario, senha):
        cadastro = self._usuarios.get(usuario)
        if cadastro is None or not hmac.compare_digest(cadastro[0], _hash(senha)):
            raise PermissionError("Usuário ou senha inválidos")
        papel = cadastro[1]
        token = secrets.token_hex(8)
        with self._trava_sessoes:
            self._sessoes[token] = (usuario, papel)
        self._log(f"    [login] {usuario} ({papel})")
        return {"token": token, "usuario": usuario, "papel": papel,
                "candidatos": [c.para_dict() for c in self.urna.listar_candidatos()],
                "multicast": {"grupo": self.grupo, "porta": self.porta_multicast},
                **self._estado(usuario, papel)}

    # ---------- multicast: notas informativas ----------
    def enviar_nota(self, autor, texto):
        if not texto.strip():
            raise ValueError("A nota não pode ser vazia")
        with self._trava_notas:
            self._seq_notas += 1
            nota = {"tipo": "NOTA_INFORMATIVA", "autor": autor, "mensagem": texto,
                    "timestamp": int(time.time()), "seq": self._seq_notas}
        self._emissor.sendto(empacotar_nota(nota), (self.grupo, self.porta_multicast))
        self._log(f"    [multicast -> {self.grupo}:{self.porta_multicast}] nota #{nota['seq']}: {texto}")
        return {"seq": nota["seq"], "enviada_para": f"{self.grupo}:{self.porta_multicast}"}

    def parar(self):
        self._timer.cancel()
        super().parar()
        self._emissor.close()


def main():
    parser = argparse.ArgumentParser(description="Servidor de votação (Questão extra)")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--porta", type=int, default=PORTA_PADRAO)
    parser.add_argument("--duracao", type=float, default=120.0, help="prazo da votação em segundos")
    parser.add_argument("--grupo", default=GRUPO_PADRAO)
    parser.add_argument("--porta-multicast", type=int, default=PORTA_MULTICAST_PADRAO)
    parser.add_argument("--eleitores", type=int, default=10, help="cria eleitor1..eleitorN (senha 123)")
    parser.add_argument("--interface", default=None)
    args = parser.parse_args()

    servidor = ServidorVotacao(args.host, args.porta, args.duracao, args.grupo, args.porta_multicast,
                               usuarios=usuarios_padrao(args.eleitores), interface=args.interface)
    print(f"Votação aberta por {args.duracao:.0f}s | TCP {servidor.porta} | "
          f"notas multicast {servidor.grupo}:{servidor.porta_multicast}")
    print(f"Usuários: eleitor1..eleitor{args.eleitores} (senha 123) e admin (senha admin)")
    try:
        servidor.servir()
    except KeyboardInterrupt:
        print("\nServidor encerrado.")
    finally:
        servidor.parar()


if __name__ == "__main__":
    main()