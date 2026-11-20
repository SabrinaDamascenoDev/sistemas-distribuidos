from .peca_de_roupa import PecaRoupa

class Calca(PecaRoupa):
    def __init__(self, id_peca, nome, preco, material):
        super().__init__(id_peca, nome, preco)
        self.material = material

    def to_dict(self):
        d = super().to_dict()
        d["material"] = self.material
        return d
