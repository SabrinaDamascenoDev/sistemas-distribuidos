"""
QUESTÃO EXTRA - Cliente do sistema de votação (eleitor ou administrador).

  1. Faz LOGIN por TCP; o servidor responde com o papel do usuário, a lista de
     candidatos, o prazo e o grupo multicast das notas informativas.
  2. Thread "escuta-notas": entra no grupo multicast e exibe as notas dos
     administradores assim que chegam.
  3. Thread "interacao-usuario": menu de eleitor (listar, votar, resultado)
     ou de administrador (adicionar/remover candidatos, enviar nota, resultado).

Executar:
    python -m votacao.cliente --usuario eleitor1 --senha 123
    python -m votacao.cliente --usuario admin --senha admin
"""

import argparse
import getpass
import socket
import threading
import time

from multicast.grupo import criar_socket_receptor, entrar_no_grupo, sair_do_grupo
from serialization.cliente_base import ClienteTCP, ErroRemoto
from votacao.modelo import Candidato, formatar_resultado
from votacao.servidor import ADMIN, PORTA_PADRAO, desempacotar_nota


class ClienteVotacao(ClienteTCP):
    """Stub do cliente: cada método é uma chamada remota (request/reply via TCP)."""

    def __init__(self, host="127.0.0.1", porta=PORTA_PADRAO, verboso=False):
        super().__init__(host, porta, verboso, timeout=5)
        self.token = None
        self.usuario = None
        self.papel = None
        self.sessao = {}

    def login(self, usuario, senha):
        self.sessao = self.chamar("LOGIN", {"usuario": usuario, "senha": senha})
        self.token = self.sessao["token"]
        self.usuario = self.sessao["usuario"]
        self.papel = self.sessao["papel"]
        return self.sessao

    def _com_token(self, operacao, **argumentos):
        return self.chamar(operacao, {"token": self.token, **argumentos})

    def listar_candidatos(self):
        return [Candidato.de_dict(c) for c in self._com_token("LISTAR_CANDIDATOS")]

    def votar(self, numero):
        return self._com_token("VOTAR", numero=numero)

    def status(self):
        return self._com_token("STATUS")

    def resultado(self):
        return self._com_token("RESULTADO")

    def adicionar_candidato(self, nome, partido="", numero=None):
        argumentos = {"nome": nome, "partido": partido}
        if numero is not None:
            argumentos["numero"] = numero
        return Candidato.de_dict(self._com_token("ADICIONAR_CANDIDATO", **argumentos))

    def remover_candidato(self, numero):
        return self._com_token("REMOVER_CANDIDATO", numero=numero)

    def enviar_nota(self, texto):
        return self._com_token("ENVIAR_NOTA", texto=texto)

    def logout(self):
        try:
            self._com_token("LOGOUT")
        except (ErroRemoto, OSError):
            pass


class OuvinteNotas:
    """Thread que escuta as notas informativas enviadas por multicast."""

    def __init__(self, grupo, porta, saida=print, nome=None, interface="0.0.0.0"):
        self.grupo, self.porta, self.interface = grupo, porta, interface
        self.saida = saida
        self.nome = nome
        self.notas = []
        self._parar = threading.Event()
        self._sock = criar_socket_receptor(grupo, porta, interface)
        self._sock.settimeout(0.5)
        entrar_no_grupo(self._sock, grupo, interface)          # joinGroup
        self._thread = threading.Thread(target=self._escutar, name="escuta-notas", daemon=True)
        self._thread.start()

    def _escutar(self):
        while not self._parar.is_set():
            try:
                dados, _ = self._sock.recvfrom(8192)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                nota = desempacotar_nota(dados)
            except ValueError:
                continue
            self.notas.append(nota)
            hora = time.strftime("%H:%M:%S", time.localtime(nota["timestamp"]))
            prefixo = f"<{self.nome}> " if self.nome else "\n"
            self.saida(f"{prefixo}[NOTA {hora} de {nota['autor']}] {nota['mensagem']}")

    def encerrar(self):
        self._parar.set()
        self._thread.join(timeout=2)
        try:
            sair_do_grupo(self._sock, self.grupo, self.interface)  # leaveGroup
        except OSError:
            pass
        self._sock.close()


# == interface de texto ==

def _mostrar_candidatos(candidatos):
    print("Candidatos:")
    for candidato in candidatos:
        print("  ", candidato)


def _mostrar_prazo(estado):
    if estado["aberta"]:
        print(f"Votação aberta: faltam {estado['segundos_restantes']:.0f}s "
              f"({estado['total_votos']} voto(s) até agora)")
    else:
        print("Votação encerrada.")


def menu_eleitor(cliente, entrada=input):
    while True:
        print("\n[ELEITOR] 1) Candidatos  2) Votar  3) Situação  4) Resultado  0) Sair")
        opcao = entrada("Opção: ").strip()
        if opcao == "1":
            _mostrar_candidatos(cliente.listar_candidatos())
        elif opcao == "2":
            _mostrar_candidatos(cliente.listar_candidatos())
            numero = int(entrada("Número do candidato: "))
            recibo = cliente.votar(numero)
            print(f"Voto registrado em {recibo['candidato']['nome']} às {recibo['horario']} "
                  f"(comprovante {recibo['comprovante']})")
        elif opcao == "3":
            estado = cliente.status()
            _mostrar_prazo(estado)
            print("Você já votou." if estado.get("ja_votou") else "Você ainda não votou.")
        elif opcao == "4":
            print(formatar_resultado(cliente.resultado()))
        elif opcao == "0":
            return
        else:
            print("Opção inválida.")


def menu_admin(cliente, entrada=input):
    while True:
        print("\n[ADMIN] 1) Candidatos  2) Adicionar candidato  3) Remover candidato  "
              "4) Enviar nota  5) Resultado (parcial/final)  0) Sair")
        opcao = entrada("Opção: ").strip()
        if opcao == "1":
            _mostrar_candidatos(cliente.listar_candidatos())
            _mostrar_prazo(cliente.status())
        elif opcao == "2":
            nome = entrada("Nome: ")
            partido = entrada("Chapa/partido: ")
            numero = entrada("Número (vazio = automático): ").strip()
            print("Adicionado:", cliente.adicionar_candidato(nome, partido, int(numero) if numero else None))
        elif opcao == "3":
            resposta = cliente.remover_candidato(int(entrada("Número do candidato: ")))
            print(f"Removido: {resposta['removido']['nome']} "
                  f"({resposta['votos_anulados']} voto(s) anulados; esses eleitores podem votar de novo)")
        elif opcao == "4":
            resposta = cliente.enviar_nota(entrada("Texto da nota: "))
            print(f"Nota #{resposta['seq']} enviada para {resposta['enviada_para']}")
        elif opcao == "5":
            print(formatar_resultado(cliente.resultado()))
        elif opcao == "0":
            return
        else:
            print("Opção inválida.")


def interagir(cliente):
    menu = menu_admin if cliente.papel == ADMIN else menu_eleitor
    while True:
        try:
            menu(cliente)
            return
        except ErroRemoto as erro:
            print("Servidor:", erro)
        except ValueError:
            print("Entrada inválida.")
        except (EOFError, KeyboardInterrupt):
            return
        except (ConnectionError, OSError) as erro:
            print("Conexão perdida:", erro)
            return


def main():
    parser = argparse.ArgumentParser(description="Cliente de votação (Questão extra)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--porta", type=int, default=PORTA_PADRAO)
    parser.add_argument("--usuario")
    parser.add_argument("--senha")
    parser.add_argument("--interface", default="0.0.0.0")
    parser.add_argument("--verboso", action="store_true", help="mostra as mensagens empacotadas")
    args = parser.parse_args()

    usuario = args.usuario or input("Usuário: ")
    senha = args.senha or getpass.getpass("Senha: ")

    try:
        cliente = ClienteVotacao(args.host, args.porta, verboso=args.verboso)
    except OSError as erro:
        print("Não foi possível conectar ao servidor:", erro)
        return
    with cliente:
        try:
            sessao = cliente.login(usuario, senha)
        except ErroRemoto as erro:
            print("Login recusado:", erro)
            return
        print(f"Bem-vindo, {sessao['usuario']} ({sessao['papel']}).")
        _mostrar_candidatos([Candidato.de_dict(c) for c in sessao["candidatos"]])
        _mostrar_prazo(sessao)

        ouvinte = OuvinteNotas(sessao["multicast"]["grupo"], sessao["multicast"]["porta"],
                               saida=lambda texto: print(texto, flush=True), interface=args.interface)
        interacao = threading.Thread(target=interagir, args=(cliente,), name="interacao-usuario", daemon=True)
        interacao.start()
        try:
            while interacao.is_alive():
                interacao.join(timeout=0.5)
        except KeyboardInterrupt:
            pass
        finally:
            ouvinte.encerrar()
            cliente.logout()
            print("Até logo.")


if __name__ == "__main__":
    main()