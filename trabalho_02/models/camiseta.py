from .peca_de_roupa import PecaRoupa

class Camiseta(PecaRoupa):
    def __init__(self, id_peca, nome, preco, tamanho):
        super().__init__(id_peca, nome, preco)
        self.tamanho = tamanho
        
    def to_dict(self):
        d = super().to_dict()
        d["tamanho"] = self.tamanho
        return d
