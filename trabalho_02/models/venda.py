class Venda:
    def __init__(self, id_venda, peca_roupa, quantidade):
        self.id_venda = id_venda
        self.peca_roupa = peca_roupa # agregação
        self.quantidade = quantidade
        self.total = peca_roupa.preco * quantidade

    def to_dict(self):
        return {
            "id_venda": self.id_venda,
            "peca_roupa": self.peca_roupa.to_dict(),
            "quantidade": self.quantidade,
            "total": self.total
        }
