"""Lógica de negócio da loja (herdada do Trabalho 2, sem mudanças)."""
from models.estoque import Estoque
from models.venda import Venda
from models.camiseta import Camiseta
from models.calca import Calca

# Só estes métodos podem ser chamados via fila.
METODOS_PERMITIDOS = {"adicionar_camiseta", "adicionar_calca", "consultar_estoque", "registrar_venda"}


class LojaService:
    def __init__(self):
        self.estoque = Estoque()
        self.vendas = []

    def adicionar_camiseta(self, kwargs):
        c = Camiseta(kwargs["id_peca"], kwargs["nome"], kwargs["preco"], kwargs["tamanho"])
        self.estoque.adicionar_item(c)
        return {"status": "sucesso", "mensagem": f"Camiseta {c.nome} adicionada ao estoque."}

    def adicionar_calca(self, kwargs):
        c = Calca(kwargs["id_peca"], kwargs["nome"], kwargs["preco"], kwargs["material"])
        self.estoque.adicionar_item(c)
        return {"status": "sucesso", "mensagem": f"Calça {c.nome} adicionada ao estoque."}

    def consultar_estoque(self, kwargs):
        return self.estoque.to_list()

    def registrar_venda(self, kwargs):
        peca = next((i for i in self.estoque.itens if i.id_peca == kwargs["id_peca"]), None)
        if peca is None:
            return {"status": "erro", "mensagem": "Peça não encontrada no estoque."}
        venda = Venda(len(self.vendas) + 1, peca, kwargs["quantidade"])
        self.vendas.append(venda)
        return {"status": "sucesso", "venda": venda.to_dict()}
