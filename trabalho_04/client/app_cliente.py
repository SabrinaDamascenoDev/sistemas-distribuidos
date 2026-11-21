"""
CLIENTE INTERATIVO DA LOJA (para a demonstração ao vivo).

  python -m client.app_cliente [--broker http://127.0.0.1:9000] [--nome caixa1] [--timeout 5]

Repare: o único endereço que o cliente conhece é o do BROKER.
Roteiro sugerido para a apresentação (3 terminais):
  1) python -m broker.app_broker
  2) python -m workers.worker_loja
  3) python -m client.app_cliente
  - cadastre e venda normalmente;
  - derrube o worker (Ctrl+C no terminal 2) e continue cadastrando: os comandos ficam na fila;
  - opção 8 mostra as mensagens esperando no broker;
  - religue o worker e use a opção 7: as respostas chegam e o estoque não perdeu nada.
"""
import argparse
import json

from client.cliente_loja import ClienteLoja
from mq.cliente_broker import ErroBroker

MENU = """
========= LOJA (via broker de filas) =========
 1) Adicionar camiseta        5) Consultar vendas
 2) Adicionar calça           6) Enviar lote de camisetas sem esperar resposta
 3) Consultar estoque         7) Buscar respostas pendentes
 4) Registrar venda           8) Estado do broker (filas e DLQ)
 0) Sair
"""


def mostrar(dado):
    print(json.dumps(dado, indent=2, ensure_ascii=False))


def ler(texto, tipo=str, padrao=None):
    sufixo = f" [{padrao}]" if padrao is not None else ""
    while True:
        bruto = input(f"{texto}{sufixo}: ").strip()
        if not bruto and padrao is not None:
            return padrao
        try:
            return tipo(bruto)
        except ValueError:
            print("  valor inválido, tente de novo")


class App:
    def __init__(self, broker_url, nome, timeout):
        self.cli = ClienteLoja(broker_url, nome=nome)
        self.timeout = timeout
        self.pendentes = {}  # id_comando -> descrição

    def comando(self, descricao, metodo, argumentos=None):
        try:
            id_cmd = self.cli.enviar(metodo, argumentos)
        except ErroBroker as e:
            print(f"!! Broker indisponível ({e}). O comando NÃO foi enviado.")
            return
        resultado = self.cli.esperar(id_cmd, self.timeout)
        if resultado is None:
            self.pendentes[id_cmd] = descricao
            print(f"-- Sem resposta em {self.timeout:g}s. O worker pode estar offline: o comando "
                  f"está guardado na fila e será processado quando ele voltar (opção 7).")
        else:
            mostrar(resultado)

    def lote(self):
        qtd = ler("Quantas camisetas", int, 3)
        inicio = ler("id_peca inicial", int, 100)
        try:
            for n in range(inicio, inicio + qtd):
                id_cmd = self.cli.enviar("adicionar_camiseta",
                                         {"id_peca": n, "nome": f"Camiseta {n}", "preco": 50.0, "tamanho": "G"})
                self.pendentes[id_cmd] = f"adicionar camiseta {n}"
        except ErroBroker as e:
            print(f"!! Broker indisponível ({e}).")
        print(f"-- {qtd} comandos publicados sem esperar. Pendentes: {len(self.pendentes)}")

    def respostas(self):
        try:
            chegaram = self.cli.coletar_respostas()
        except ErroBroker as e:
            print(f"!! Broker indisponível ({e}).")
            return
        for id_cmd, resultado in chegaram.items():
            print(f"* {self.pendentes.pop(id_cmd, id_cmd[:8])}: {json.dumps(resultado, ensure_ascii=False)}")
        if not chegaram:
            print("-- nenhuma resposta nova")
        print(f"-- ainda pendentes: {len(self.pendentes)}")

    def broker(self):
        try:
            stats = self.cli.broker.estatisticas()
            mostrar(stats or {"(todas as filas vazias)": {}})
            dlqs = [f for f in stats if f.startswith("dlq.")]
            for fila in dlqs:
                print(f"Mensagens em {fila}:")
                for m in self.cli.broker.espiar(fila, 5):
                    print(f"  #{m['id']} motivo={m['motivo']!r} corpo={json.dumps(m['corpo'], ensure_ascii=False)[:80]}")
        except ErroBroker as e:
            print(f"!! Broker indisponível ({e}).")

    def executar(self):
        print(f"Cliente conectado APENAS ao broker {self.cli.broker.url} | fila de respostas: {self.cli.fila_resposta}")
        acoes = {
            "1": lambda: self.comando("adicionar camiseta", "adicionar_camiseta", {
                "id_peca": ler("id_peca", int), "nome": ler("nome", str, "Camiseta"),
                "preco": ler("preço", float, 59.9), "tamanho": ler("tamanho", str, "M")}),
            "2": lambda: self.comando("adicionar calça", "adicionar_calca", {
                "id_peca": ler("id_peca", int), "nome": ler("nome", str, "Calça"),
                "preco": ler("preço", float, 119.9), "material": ler("material", str, "Jeans")}),
            "3": lambda: self.comando("consultar estoque", "consultar_estoque"),
            "4": lambda: self.comando("registrar venda", "registrar_venda", {
                "id_peca": ler("id_peca", int), "quantidade": ler("quantidade", int, 1)}),
            "5": lambda: self.comando("consultar vendas", "consultar_vendas"),
            "6": self.lote,
            "7": self.respostas,
            "8": self.broker,
        }
        while True:
            print(MENU)
            opcao = input("Opção: ").strip()
            if opcao == "0":
                break
            acao = acoes.get(opcao)
            if acao:
                acao()
            else:
                print("opção inválida")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--broker", default="http://127.0.0.1:9000")
    ap.add_argument("--nome", default="caixa1", help="identifica a fila de respostas deste cliente")
    ap.add_argument("--timeout", type=float, default=5.0, help="segundos esperando cada resposta")
    a = ap.parse_args()
    try:
        App(a.broker, a.nome, a.timeout).executar()
    except (KeyboardInterrupt, EOFError):
        print()