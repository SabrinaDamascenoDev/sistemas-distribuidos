class Venda:
    def __init__(self, codigo, codigo_peca, nome_peca, quantidade, valor_total, data_hora):
        self.codigo = int(codigo)             
        self.codigo_peca = int(codigo_peca)   
        self.nome_peca = nome_peca
        self.quantidade = int(quantidade)
        self.valor_total = float(valor_total)
        self.data_hora = data_hora          

    def para_dict(self):
        return {
            "codigo": self.codigo,
            "codigo_peca": self.codigo_peca,
            "nome_peca": self.nome_peca,
            "quantidade": self.quantidade,
            "valor_total": self.valor_total,
            "data_hora": self.data_hora,
        }

    @staticmethod
    def de_dict(dados):
        return Venda(dados["codigo"], dados["codigo_peca"], dados["nome_peca"],
                     dados["quantidade"], dados["valor_total"], dados["data_hora"])

    def __str__(self):
        return (f"Venda #{self.codigo}: {self.quantidade}x {self.nome_peca} "
                f"= R$ {self.valor_total:.2f} ({self.data_hora})")