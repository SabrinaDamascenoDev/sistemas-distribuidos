"""
QUESTÃO 4 - Servidor de notificações da loja (TCP unicast + UDP multicast).

  * TCP (unicast, porta 5060): autenticação dos clientes. Só depois de um login
    válido o servidor informa o grupo multicast e a porta.
  * UDP (multicast, grupo classe D 230.0.0.1, porta fixa 5007): envio das
    mensagens NOTIFICACAO, ALERTA e ATUALIZACAO para todos os clientes do grupo.

Threads do servidor (envio concorrente):
  - "accept" + uma thread por cliente TCP (autenticação);
  - "simulacao-loja": gera vendas/reposições e publica ATUALIZACAO e ALERTA;
  - console do administrador (thread principal): publica mensagens digitadas;
  - pool de threads "envio-N": publicações assíncronas, inclusive em rajada.
Todas elas chamam publicar() ao mesmo tempo; o número de sequência é protegido
por uma trava.

Executar:
    python -m multicast.servidor                    (console + simulação da loja)
    python -m multicast.servidor --intervalo 0      (sem simulação automática)
"""

import argparse
import hashlib
import hmac
import random
import secrets
import threading
from concurrent.futures import ThreadPoolExecutor, wait

from models.exemplo import criar_loja_exemplo
from multicast import mensagens
from multicast.grupo import criar_socket_emissor, validar_grupo
from serialization.servidor_base import ServidorTCP
from services.erros import LojaError
from services.estoque_service import EstoqueService
from services.vendas_service import VendasService

GRUPO_PADRAO = "230.0.0.1"
PORTA_MULTICAST_PADRAO = 5007
PORTA_AUTH_PADRAO = 5060

USUARIOS_PADRAO = {"ana": "123", "bruno": "123", "carla": "123", "davi": "123", "admin": "admin"}
LIMITE_ESTOQUE_BAIXO = 3


def _hash(senha):
    return hashlib.sha256(senha.encode("utf-8")).hexdigest()


class ServidorNotificacoes(ServidorTCP):

    def __init__(self, host="0.0.0.0", porta_auth=PORTA_AUTH_PADRAO, grupo=GRUPO_PADRAO,
                 porta_multicast=PORTA_MULTICAST_PADRAO, usuarios=None, ttl=1,
                 interface=None, verboso=True, trabalhadores=4):
        super().__init__(host, porta_auth, verboso)
        self.grupo = validar_grupo(grupo)
        self.porta_multicast = porta_multicast
        self._emissor = criar_socket_emissor(ttl, interface)
        self._usuarios = {u: _hash(s) for u, s in (usuarios or USUARIOS_PADRAO).items()}
        self._sessoes = {}                       # token -> usuário
        self._trava_sessoes = threading.Lock()
        self._seq = 0
        self._trava_seq = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=trabalhadores, thread_name_prefix="envio")
        self._parar = threading.Event()

    def executar(self, operacao, args, endereco=None):
        if operacao == "AUTENTICAR":
            return self._autenticar(str(args["usuario"]), str(args["senha"]))
        if operacao == "SAIR":
            with self._trava_sessoes:
                usuario = self._sessoes.pop(args["token"], None)
            if usuario is None:
                raise PermissionError("Token inválido")
            self.publicar_async(mensagens.NOTIFICACAO, f"{usuario} saiu do serviço")
            return {"encerrado": True}
        raise ValueError(f"Operação desconhecida: {operacao}")

    def _autenticar(self, usuario, senha):
        esperado = self._usuarios.get(usuario)
        if esperado is None or not hmac.compare_digest(esperado, _hash(senha)):
            raise PermissionError("Usuário ou senha inválidos")
        token = secrets.token_hex(8)
        with self._trava_sessoes:
            self._sessoes[token] = usuario
        self._log(f"    [auth] {usuario} autenticado")
        self.publicar_async(mensagens.NOTIFICACAO, f"{usuario} entrou no serviço de notificações")
        return {"token": token, "usuario": usuario, "grupo": self.grupo,
                "porta": self.porta_multicast, "tipos": list(mensagens.TIPOS)}

    def clientes_autenticados(self):
        with self._trava_sessoes:
            return sorted(self._sessoes.values())

    #  UDP: publicação multicast 
    def publicar(self, tipo, texto):
        """Monta, empacota e envia UMA mensagem ao grupo. Pode ser chamado por várias threads."""
        with self._trava_seq:
            self._seq += 1
            seq = self._seq
        mensagem = mensagens.criar_mensagem(tipo, texto, seq)
        self._emissor.sendto(mensagens.empacotar(mensagem), (self.grupo, self.porta_multicast))
        self._log(f"    [multicast -> {self.grupo}:{self.porta_multicast} "
                  f"| {threading.current_thread().name}] {mensagens.formatar(mensagem)}")
        return mensagem

    def publicar_async(self, tipo, texto):
        """Entrega a publicação ao pool de threads e devolve um Future (None se encerrado)."""
        try:
            return self._pool.submit(self.publicar, tipo, texto)
        except RuntimeError:  # pool já encerrado
            return None

    def rajada(self, quantidade):
        """Dispara várias mensagens AO MESMO TEMPO (demonstração de envio concorrente)."""
        futuros = [self.publicar_async(random.choice(mensagens.TIPOS), f"Mensagem {i + 1} da rajada")
                   for i in range(quantidade)]
        wait(futuros)
        return [f.result() for f in futuros]

    #  simulação da loja (produz ATUALIZACAO / ALERTA) 
    def iniciar_simulacao_loja(self, intervalo=4.0, loja=None):
        estoque = EstoqueService(loja or criar_loja_exemplo())
        vendas = VendasService(estoque)

        def simular():
            while not self._parar.wait(intervalo):
                peca = random.choice(estoque.listar_pecas())
                if peca.quantidade == 0 or random.random() < 0.2:
                    reposicao = random.randint(5, 10)
                    peca.quantidade += reposicao
                    self.publicar(mensagens.ATUALIZACAO,
                                  f"Reposição: +{reposicao} '{peca.nome}' (estoque {peca.quantidade})")
                    continue
                try:
                    venda = vendas.vender(peca.codigo, random.randint(1, 3))
                except LojaError:
                    continue
                self.publicar(mensagens.ATUALIZACAO,
                              f"Venda: {venda.quantidade}x '{peca.nome}' = R$ {venda.valor_total:.2f} "
                              f"(estoque {peca.quantidade})")
                if peca.quantidade == 0:
                    self.publicar(mensagens.ALERTA, f"'{peca.nome}' ESGOTADA!")
                elif peca.quantidade <= LIMITE_ESTOQUE_BAIXO:
                    self.publicar(mensagens.ALERTA,
                                  f"Estoque baixo de '{peca.nome}': {peca.quantidade} unidade(s)")

        thread = threading.Thread(target=simular, name="simulacao-loja", daemon=True)
        thread.start()
        return thread

    #  console do administrador 
    def console(self, entrada=input):
        atalhos = {"n": mensagens.NOTIFICACAO, "a": mensagens.ALERTA, "u": mensagens.ATUALIZACAO}
        print(AJUDA_CONSOLE)
        while not self._parar.is_set():
            try:
                linha = entrada("admin> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not linha:
                continue
            comando, _, texto = linha.partition(" ")
            comando = comando.lower()
            if comando in atalhos and texto:
                self.publicar_async(atalhos[comando], texto)
            elif comando == "rajada":
                quantidade = int(texto) if texto.isdigit() else 10
                self.rajada(quantidade)
            elif comando == "clientes":
                print("Clientes autenticados:", ", ".join(self.clientes_autenticados()) or "nenhum")
            elif comando in ("sair", "quit", "exit"):
                break
            else:
                print(AJUDA_CONSOLE)

    def parar(self):
        self._parar.set()
        self._pool.shutdown(wait=True)
        super().parar()
        self._emissor.close()


AJUDA_CONSOLE = """Comandos do administrador:
  n <texto>     envia NOTIFICACAO       a <texto>   envia ALERTA
  u <texto>     envia ATUALIZACAO       rajada <N>  envia N mensagens concorrentes
  clientes      lista os autenticados   sair        encerra o servidor"""


def main():
    parser = argparse.ArgumentParser(description="Servidor de notificações multicast (Questão 4)")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--porta-auth", type=int, default=PORTA_AUTH_PADRAO)
    parser.add_argument("--grupo", default=GRUPO_PADRAO)
    parser.add_argument("--porta-multicast", type=int, default=PORTA_MULTICAST_PADRAO)
    parser.add_argument("--ttl", type=int, default=1, help="1 = não sai da rede local")
    parser.add_argument("--interface", default=None, help="IP da interface de saída do multicast")
    parser.add_argument("--intervalo", type=float, default=5.0,
                        help="segundos entre eventos simulados da loja (0 desliga)")
    parser.add_argument("--sem-console", action="store_true", help="não lê comandos do teclado")
    args = parser.parse_args()

    servidor = ServidorNotificacoes(args.host, args.porta_auth, args.grupo, args.porta_multicast,
                                    ttl=args.ttl, interface=args.interface)
    print(f"Autenticação TCP na porta {servidor.porta} | multicast em {servidor.grupo}:{servidor.porta_multicast}")
    servidor.iniciar_em_segundo_plano()
    if args.intervalo > 0:
        servidor.iniciar_simulacao_loja(args.intervalo)
    try:
        if args.sem_console:
            servidor._parar.wait()
        else:
            servidor.console()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.parar()
        print("\nServidor encerrado.")


if __name__ == "__main__":
    main()