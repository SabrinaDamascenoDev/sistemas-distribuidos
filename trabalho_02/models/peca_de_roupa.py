class PecaRoupa:
    def __init__(self, id_peca, nome, preco):
        self.id_peca = id_peca
        self.nome = nome
        self.preco = preco
        
    def to_dict(self):
        return {"id_peca": self.id_peca, "nome": self.nome, "preco": self.preco}
