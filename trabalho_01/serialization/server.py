"""
QUESTÃO 3 - Servidor da Loja (TCP).

Fluxo de cada requisição:
  1. receber()      -> lê bytes e DESEMPACOTA o request (bytes -> dict)
  2. processar()    -> usa EstoqueService / VendasService (reconstrói objetos)
  3. enviar()       -> EMPACOTA o reply (dict -> bytes) e envia ao cliente

"""

import argparse
import threading

from models.exemplo import criar_loja_exemplo
from models.peca_de_roupa import peca_de_dict
from serialization.servidor_base import ServidorTCP
from services.estoque_service import EstoqueService
from services.vendas_service import VendasService


class ServidorLoja(ServidorTCP):
    """Recebe, processa e responde as requisições da loja (uma thread por cliente)."""

    def __init__(self, host, porta, loja, verboso=True):
        super().__init__(host, porta, verboso)
        self.estoque = EstoqueService(loja)
        self.vendas = VendasService(self.estoque)
        self._trava = threading.Lock() 

    def executar(self, operacao, args, endereco=None):
        with self._trava:
            return self._executar(operacao, args)

    def _executar(self, operacao, args):
        if operacao == "LISTAR_PECAS":
            return [peca.para_dict() for peca in self.estoque.listar_pecas()]

        if operacao == "ADICIONAR_PECA":
            peca = peca_de_dict(args["peca"])         
            self.estoque.adicionar_peca(peca)
            return peca.para_dict()

        if operacao == "VENDER_PECA":
            venda = self.vendas.vender(int(args["codigo"]), int(args["quantidade"]))
            return venda.para_dict()

        if operacao == "TOTAL_VENDAS":
            return {"quantidade_vendas": len(self.vendas.listar_vendas()),
                    "total": round(self.vendas.total_vendido(), 2)}

        raise ValueError(f"Operação desconhecida: {operacao}")


def main():
    parser = argparse.ArgumentParser(description="Servidor da loja de roupas (Questão 3)")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--porta", type=int, default=5050)
    args = parser.parse_args()

    servidor = ServidorLoja(args.host, args.porta, criar_loja_exemplo())
    try:
        servidor.servir()
    except KeyboardInterrupt:
        print("\nServidor encerrado.")
        servidor.parar()


if __name__ == "__main__":
    main()