from models.estoque import Estoque
from models.venda import Venda
from models.camiseta import Camiseta
from models.calca import Calca

class LojaService:
    def __init__(self):
        self.estoque = Estoque()
        self.vendas = []
        
    # Método Remoto 1
    def adicionar_camiseta(self, kwargs):
        nova_camiseta = Camiseta(kwargs['id_peca'], kwargs['nome'], kwargs['preco'], kwargs['tamanho'])
        self.estoque.adicionar_item(nova_camiseta)
        return {"status": "sucesso", "mensagem": f"Camiseta {nova_camiseta.nome} adicionada ao estoque."}

    # Método Remoto 2
    def adicionar_calca(self, kwargs):
        nova_calca = Calca(kwargs['id_peca'], kwargs['nome'], kwargs['preco'], kwargs['material'])
        self.estoque.adicionar_item(nova_calca)
        return {"status": "sucesso", "mensagem": f"Calça {nova_calca.nome} adicionada ao estoque."}

    # Método Remoto 3
    def consultar_estoque(self, kwargs):
        return self.estoque.to_list()

    # Método Remoto 4
    def registrar_venda(self, kwargs):
        id_peca = kwargs['id_peca']
        quantidade = kwargs['quantidade']
        
        peca_encontrada = None
        for item in self.estoque.itens:
            if item.id_peca == id_peca:
                peca_encontrada = item
                break
                
        if peca_encontrada:
            id_venda = len(self.vendas) + 1
            nova_venda = Venda(id_venda, peca_encontrada, quantidade)
            self.vendas.append(nova_venda)
            return {"status": "sucesso", "venda": nova_venda.to_dict()}
        else:
            return {"status": "erro", "mensagem": "Peça não encontrada no estoque."}
