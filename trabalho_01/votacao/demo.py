"""
QUESTÃO EXTRA - Demonstração automática do sistema de votação.

Roteiro (servidor com prazo curto, tudo no mesmo processo):
  1. admin faz login, adiciona e remove candidatos e envia uma nota (multicast);
  2. cinco eleitores fazem login AO MESMO TEMPO (threads), recebem a lista de
     candidatos e a nota informativa;
  3. os eleitores votam concorrentemente; erros esperados: voto duplicado,
     eleitor tentando adicionar candidato, resultado pedido antes do prazo;
  4. o prazo termina: voto atrasado é recusado e o resultado final é exibido.

Executar:  python -m votacao.demo
"""

import threading
import time

from serialization.cliente_base import ErroRemoto
from votacao.cliente import ClienteVotacao, OuvinteNotas
from votacao.modelo import formatar_resultado
from votacao.servidor import ServidorVotacao

_trava_print = threading.Lock()


def imprimir(texto):
    with _trava_print:
        print(texto, flush=True)


def titulo(texto):
    imprimir(f"\n {texto} ")


def esperar_erro(descricao, funcao, *args):
    try:
        funcao(*args)
        imprimir(f"   !! {descricao}: deveria ter falhado")
        return None
    except ErroRemoto as erro:
        imprimir(f"   {descricao}: servidor recusou -> {erro}")
        return str(erro)


def executar(duracao=4.0, grupo="230.0.0.2", porta_multicast=6001):
    servidor = ServidorVotacao("127.0.0.1", 0, duracao, grupo, porta_multicast, verboso=False)
    servidor.iniciar_em_segundo_plano()
    imprimir(f"Servidor de votação na porta {servidor.porta}; prazo de {duracao:.0f}s; "
             f"notas em {grupo}:{porta_multicast}")

    eleitores = [f"eleitor{i}" for i in range(1, 6)]
    escolhas = {"eleitor1": 10, "eleitor2": 20, "eleitor3": 10, "eleitor4": 40, "eleitor5": 10}
    clientes, ouvintes = {}, {}
    admin = ClienteVotacao("127.0.0.1", servidor.porta)
    try:
        titulo("1) Login dos eleitores em paralelo (TCP) + entrada no grupo de notas")

        def entrar(nome):
            cliente = ClienteVotacao("127.0.0.1", servidor.porta)
            sessao = cliente.login(nome, "123")
            clientes[nome] = cliente
            ouvintes[nome] = OuvinteNotas(sessao["multicast"]["grupo"], sessao["multicast"]["porta"],
                                          saida=imprimir, nome=nome)
            numeros = [c["numero"] for c in sessao["candidatos"]]
            imprimir(f"   {nome} logado como {sessao['papel']}; candidatos recebidos: {numeros}")

        threads = [threading.Thread(target=entrar, args=(n,)) for n in eleitores]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        titulo("2) Administrador gerencia candidatos e envia nota informativa (multicast)")
        admin.login("admin", "admin")
        imprimir(f"   adicionado: {admin.adicionar_candidato('Diego Farias', 'Chapa Renovação', 40)}")
        imprimir(f"   adicionado: {admin.adicionar_candidato('Elisa Prado', 'Chapa Temporária')}")
        removido = admin.remover_candidato(41)
        imprimir(f"   removido: {removido['removido']['nome']}")
        admin.enviar_nota("Candidato 40 (Diego Farias) entrou na disputa. Atualizem a lista!")
        time.sleep(0.4)

        titulo("3) Votos concorrentes")

        def votar(nome):
            recibo = clientes[nome].votar(escolhas[nome])
            imprimir(f"   {nome} votou em {recibo['candidato']['nome']} (comprovante {recibo['comprovante']})")

        threads = [threading.Thread(target=votar, args=(n,)) for n in eleitores]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        titulo("4) Situações que o servidor deve recusar")
        esperar_erro("eleitor1 votando de novo", clientes["eleitor1"].votar, 20)
        esperar_erro("eleitor2 tentando adicionar candidato", clientes["eleitor2"].adicionar_candidato, "X")
        esperar_erro("eleitor3 pedindo o resultado antes do prazo", clientes["eleitor3"].resultado)
        intruso = ClienteVotacao("127.0.0.1", servidor.porta)
        esperar_erro("login com senha errada", intruso.login, "eleitor1", "errada")
        intruso.fechar()
        imprimir("   Admin pode ver a parcial antes do prazo:")
        imprimir(formatar_resultado(admin.resultado()))
        admin.enviar_nota("Faltam poucos segundos para o encerramento!")

        restante = admin.status()["segundos_restantes"]
        titulo(f"5) Aguardando o fim do prazo (~{restante:.1f}s)")
        servidor.encerrada.wait(restante + 2)
        tardio = ClienteVotacao("127.0.0.1", servidor.porta)
        tardio.login("eleitor6", "123")
        esperar_erro("eleitor6 votando após o prazo", tardio.votar, 10)
        esperar_erro("admin adicionando candidato após o prazo", admin.adicionar_candidato, "Tarde")
        tardio.fechar()

        titulo("6) Resultado final consultado por um eleitor")
        resultado = clientes["eleitor5"].resultado()
        imprimir(formatar_resultado(resultado))
        imprimir("\nNotas recebidas por multicast: " +
                 ", ".join(f"{n}={len(o.notas)}" for n, o in ouvintes.items()))
        return resultado, {n: list(o.notas) for n, o in ouvintes.items()}
    finally:
        for ouvinte in ouvintes.values():
            ouvinte.encerrar()
        for cliente in clientes.values():
            cliente.fechar()
        admin.fechar()
        servidor.parar()


if __name__ == "__main__":
    executar()