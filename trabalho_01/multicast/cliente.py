"""
QUESTÃO 4 - Cliente de notificações da loja.

  1. Autentica-se no servidor por TCP (unicast) e recebe o grupo/porta multicast.
  2. Entra no grupo (joinGroup) e passa a receber os datagramas UDP.
  3. Usa DUAS threads:
       - "escuta-multicast"  : bloqueia em recvfrom() e exibe cada mensagem na hora;
       - "interacao-usuario" : lê comandos do teclado (entrar/sair do grupo etc.).

Executar (abra quantos terminais quiser, um cliente por terminal):
    python -m multicast.cliente --usuario ana --senha 123
    python -m multicast.cliente --usuario bruno --senha 123 --auto 30   (sem teclado)
"""

import argparse
import getpass
import socket
import threading

from multicast import mensagens
from multicast.grupo import criar_socket_receptor, entrar_no_grupo, sair_do_grupo
from serialization.cliente_base import ClienteTCP, ErroRemoto

HOST_PADRAO = "127.0.0.1"
PORTA_AUTH_PADRAO = 5060


class ClienteNotificacoes:

    def __init__(self, nome=None, saida=print, interface="0.0.0.0"):
        self.nome = nome
        self.saida = saida
        self.interface = interface
        self.historico = []
        self.no_grupo = False
        self.token = None
        self.grupo = None
        self.porta = None
        self._host = None
        self._porta_auth = None
        self._sock = None
        self._parar = threading.Event()
        self._thread_escuta = None
        self._trava = threading.Lock()

    def autenticar(self, host, porta, usuario, senha):
        with ClienteTCP(host, porta, timeout=5) as conexao:
            resultado = conexao.chamar("AUTENTICAR", {"usuario": usuario, "senha": senha})
        self.nome = self.nome or resultado["usuario"]
        self.token = resultado["token"]
        self.grupo = resultado["grupo"]
        self.porta = resultado["porta"]
        self._host, self._porta_auth = host, porta
        return resultado

    def iniciar_escuta(self):
        if self.grupo is None:
            raise RuntimeError("Autentique-se antes de entrar no grupo")
        self._sock = criar_socket_receptor(self.grupo, self.porta, self.interface)
        self._sock.settimeout(0.5)  # permite verificar periodicamente se deve parar
        self.entrar()
        self._thread_escuta = threading.Thread(target=self._escutar, name="escuta-multicast", daemon=True)
        self._thread_escuta.start()

    def entrar(self):
        """joinGroup"""
        with self._trava:
            if not self.no_grupo:
                entrar_no_grupo(self._sock, self.grupo, self.interface)
                self.no_grupo = True
                return True
        return False

    def sair(self):
        """leaveGroup"""
        with self._trava:
            if self.no_grupo:
                sair_do_grupo(self._sock, self.grupo, self.interface)
                self.no_grupo = False
                return True
        return False

    def _escutar(self):
        while not self._parar.is_set():
            try:
                dados, _ = self._sock.recvfrom(mensagens.TAMANHO_MAXIMO_DATAGRAMA)
            except socket.timeout:
                continue
            except OSError:
                break  # socket fechado
            try:
                mensagem = mensagens.desempacotar(dados)
            except ValueError:
                continue  # datagrama de outro programa no mesmo grupo: ignora
            self.historico.append(mensagem)
            self.saida(f"{self._prefixo()}{mensagens.formatar(mensagem)}")

    def _prefixo(self):
        return f"<{self.nome}> " if self.nome else ""

    def interagir(self, entrada=input):
        self.saida(AJUDA_CLIENTE)
        while not self._parar.is_set():
            try:
                comando = entrada("").strip().lower()
            except (EOFError, KeyboardInterrupt):
                break
            if comando == "sair":
                self.saida("leaveGroup: você saiu do grupo." if self.sair() else "Você já está fora do grupo.")
            elif comando == "entrar":
                self.saida("joinGroup: você voltou ao grupo." if self.entrar() else "Você já está no grupo.")
            elif comando == "historico":
                for mensagem in self.historico:
                    self.saida("   " + mensagens.formatar(mensagem))
                self.saida(f"   ({len(self.historico)} mensagens recebidas)")
            elif comando == "status":
                estado = "DENTRO do" if self.no_grupo else "FORA do"
                self.saida(f"{self.nome}: {estado} grupo {self.grupo}:{self.porta}, "
                           f"{len(self.historico)} mensagens recebidas")
            elif comando in ("fim", "quit", "exit"):
                break
            elif comando:
                self.saida(AJUDA_CLIENTE)

    def esperar(self, segundos):
        """Modo automático: a thread de interação apenas aguarda."""
        self._parar.wait(segundos)

    def encerrar(self):
        self._parar.set()
        if self._thread_escuta:
            self._thread_escuta.join(timeout=2)
        if self._sock:
            try:
                self.sair()
            except OSError:
                pass
            self._sock.close()
        if self.token and self._host:
            try:
                with ClienteTCP(self._host, self._porta_auth, timeout=2) as conexao:
                    conexao.chamar("SAIR", {"token": self.token})
            except (OSError, ErroRemoto):
                pass


AJUDA_CLIENTE = ("Comandos: sair (leaveGroup) | entrar (joinGroup) | historico | status | fim\n"
                 "As mensagens do grupo aparecem automaticamente.")


def main():
    parser = argparse.ArgumentParser(description="Cliente de notificações multicast (Questão 4)")
    parser.add_argument("--host", default=HOST_PADRAO)
    parser.add_argument("--porta", type=int, default=PORTA_AUTH_PADRAO, help="porta TCP de autenticação")
    parser.add_argument("--usuario")
    parser.add_argument("--senha")
    parser.add_argument("--interface", default="0.0.0.0", help="IP da interface que entra no grupo")
    parser.add_argument("--auto", type=float, metavar="SEGUNDOS",
                        help="não lê o teclado; só escuta durante SEGUNDOS")
    args = parser.parse_args()

    usuario = args.usuario or input("Usuário: ")
    senha = args.senha or getpass.getpass("Senha: ")

    cliente = ClienteNotificacoes(interface=args.interface,
                                  saida=lambda texto: print(texto, flush=True))
    try:
        dados = cliente.autenticar(args.host, args.porta, usuario, senha)
    except ErroRemoto as erro:
        print("Falha na autenticação:", erro)
        return
    except OSError as erro:
        print("Não foi possível conectar ao servidor:", erro)
        return

    print(f"Autenticado como {dados['usuario']}. Entrando no grupo {dados['grupo']}:{dados['porta']}...")
    cliente.iniciar_escuta()

    if args.auto:
        interacao = threading.Thread(target=cliente.esperar, args=(args.auto,), name="interacao-usuario", daemon=True)
    else:
        interacao = threading.Thread(target=cliente.interagir, name="interacao-usuario", daemon=True)
    interacao.start()
    try:
        while interacao.is_alive():
            interacao.join(timeout=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        cliente.encerrar()
        print(f"Cliente encerrado ({len(cliente.historico)} mensagens recebidas).")


if __name__ == "__main__":
    main()