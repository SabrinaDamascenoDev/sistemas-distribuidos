"""
Lógica de negócio da loja (herdada do Trabalho 2).

Novidades do T4:
  * consultar_vendas (para conferir que uma reentrega não duplicou vendas);
  * exportar()/importar(): o worker salva e recupera o estado em disco.
"""
from models.estoque import Estoque
from models.venda import Venda
from models.camiseta import Camiseta
from models.calca import Calca
from models.peca_de_roupa import PecaRoupa

# Só estes métodos podem ser chamados via fila.
METODOS_PERMITIDOS = {"adicionar_camiseta", "adicionar_calca", "consultar_estoque",
                      "registrar_venda", "consultar_vendas"}
# Métodos que não alteram o estado: reexecutá-los numa reentrega é inofensivo.
METODOS_LEITURA = {"consultar_estoque", "consultar_vendas"}


def _peca_de_dict(d):
    if "tamanho" in d:
        return Camiseta(d["id_peca"], d["nome"], d["preco"], d["tamanho"])
    if "material" in d:
        return Calca(d["id_peca"], d["nome"], d["preco"], d["material"])
    return PecaRoupa(d["id_peca"], d["nome"], d["preco"])


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

    def consultar_vendas(self, kwargs):
        return [v.to_dict() for v in self.vendas]

    # ------------------------------------------------------------ persistência
    def exportar(self):
        return {"estoque": self.estoque.to_list(), "vendas": [v.to_dict() for v in self.vendas]}

    def importar(self, dados):
        self.estoque = Estoque()
        for d in dados.get("estoque", []):
            self.estoque.adicionar_item(_peca_de_dict(d))
        self.vendas = []
        for dv in dados.get("vendas", []):
            id_peca = dv["peca_roupa"]["id_peca"]
            # Mantém a agregação: a venda aponta para o mesmo objeto que está no estoque.
            peca = next((i for i in self.estoque.itens if i.id_peca == id_peca), None)
            self.vendas.append(Venda(dv["id_venda"], peca or _peca_de_dict(dv["peca_roupa"]), dv["quantidade"]))