"""
QUESTÃO 4 - Demonstração automática com VÁRIOS clientes simultâneos.

Sobe o servidor e três clientes (ana, bruno e carla) no mesmo processo, cada
cliente com a sua própria thread de escuta multicast, e executa o roteiro:

  1. os três se autenticam por TCP e entram no grupo 230.0.0.1 (joinGroup);
  2. o servidor envia NOTIFICACAO, ALERTA e ATUALIZACAO -> os três recebem;
  3. o servidor dispara uma rajada concorrente (pool de threads);
  4. bruno sai do grupo (leaveGroup) -> só ana e carla recebem o próximo ALERTA;
  5. bruno volta ao grupo -> todos recebem a ATUALIZACAO final;
  6. tentativa de login com senha errada é recusada pelo servidor.

Executar:  python -m multicast.demo
"""

import sys
import threading
import time

from multicast import mensagens
from multicast.cliente import ClienteNotificacoes
from multicast.servidor import ServidorNotificacoes
from serialization.cliente_base import ErroRemoto

PAUSA = 0.4
_trava_print = threading.Lock()


def imprimir(texto):
    with _trava_print:
        print(texto, flush=True)


def titulo(texto):
    imprimir(f"\n {texto} ")


def executar(grupo="230.0.0.1", porta_multicast=5007, verboso=True):
    servidor = ServidorNotificacoes("127.0.0.1", 0, grupo, porta_multicast, verboso=False)
    servidor.iniciar_em_segundo_plano()
    imprimir(f"Servidor: autenticação TCP na porta {servidor.porta}, multicast {grupo}:{porta_multicast}")

    saida = imprimir if verboso else (lambda _texto: None)
    clientes = {nome: ClienteNotificacoes(nome, saida=saida) for nome in ("ana", "bruno", "carla")}
    try:
        titulo("1) Autenticação TCP + joinGroup")
        for nome, cliente in clientes.items():
            dados = cliente.autenticar("127.0.0.1", servidor.porta, nome, "123")
            cliente.iniciar_escuta()
            imprimir(f"   {nome} autenticado (token {dados['token']}) -> grupo {dados['grupo']}:{dados['porta']}")
        time.sleep(PAUSA)

        titulo("2) Uma mensagem de cada tipo")
        servidor.publicar(mensagens.NOTIFICACAO, "Novo dado disponível: coleção de verão no estoque")
        servidor.publicar(mensagens.ALERTA, "Estoque baixo de 'Jaqueta de Couro': 2 unidade(s)")
        servidor.publicar(mensagens.ATUALIZACAO, "Preço da 'Calça Jeans Slim' agora R$ 179.90")
        time.sleep(PAUSA)

        titulo("3) Rajada de 6 mensagens enviadas concorrentemente")
        servidor.rajada(6)
        time.sleep(PAUSA)

        titulo("4) bruno executa leaveGroup")
        clientes["bruno"].sair()
        servidor.publicar(mensagens.ALERTA, "Esta mensagem NÃO deve chegar para bruno")
        time.sleep(PAUSA)

        titulo("5) bruno executa joinGroup novamente")
        clientes["bruno"].entrar()
        servidor.publicar(mensagens.ATUALIZACAO, "Todos de volta: mensagem final")
        time.sleep(PAUSA)

        titulo("6) Autenticação com senha errada")
        try:
            ClienteNotificacoes().autenticar("127.0.0.1", servidor.porta, "ana", "errada")
        except ErroRemoto as erro:
            imprimir(f"   Servidor recusou: {erro}")

        titulo("Resumo: mensagens recebidas por cliente")
        for nome, cliente in clientes.items():
            imprimir(f"   {nome:<6} {len(cliente.historico):>2} mensagens")
        return {nome: list(cliente.historico) for nome, cliente in clientes.items()}
    finally:
        for cliente in clientes.values():
            cliente.encerrar()
        servidor.parar()


if __name__ == "__main__":
    executar(verboso="-q" not in sys.argv)