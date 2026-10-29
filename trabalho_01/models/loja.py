class Loja:

    def __init__(self, nome, cnpj, pecas=None):
        self.nome = nome
        self.cnpj = cnpj
        self.pecas = list(pecas) if pecas else []

    def __str__(self):
        return f"Loja {self.nome} (CNPJ {self.cnpj}) - {len(self.pecas)} tipos de peça"