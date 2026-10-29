class PecaDeRoupa:
    ROTULO_DETALHE = "detalhe" 
    def __init__(self, codigo, nome, marca, tamanho, cor, preco, quantidade):
        self.codigo = int(codigo)       
        self.nome = nome
        self.marca = marca
        self.tamanho = tamanho           
        self.cor = cor
        self.preco = float(preco)          
        self.quantidade = int(quantidade)  

    @property
    def tipo(self):
        return type(self).__name__

    @property
    def detalhe(self):
        raise NotImplementedError("Subclasses devem implementar 'detalhe'")

    def para_dict(self):
        return {
            "tipo": self.tipo,
            "codigo": self.codigo,
            "nome": self.nome,
            "marca": self.marca,
            "tamanho": self.tamanho,
            "cor": self.cor,
            "preco": self.preco,
            "quantidade": self.quantidade,
            "detalhe": self.detalhe,
        }

    def __str__(self):
        return (f"[{self.codigo}] {self.tipo}: {self.nome} ({self.marca}) | "
                f"tam {self.tamanho} | cor {self.cor} | R$ {self.preco:.2f} | "
                f"estoque {self.quantidade} | {self.ROTULO_DETALHE}: {self.detalhe}")

class Camiseta(PecaDeRoupa):
    ROTULO_DETALHE = "manga"

    def __init__(self, codigo, nome, marca, tamanho, cor, preco, quantidade, manga):
        super().__init__(codigo, nome, marca, tamanho, cor, preco, quantidade)
        self.manga = manga 

    @property
    def detalhe(self):
        return self.manga

class Calca(PecaDeRoupa):
    ROTULO_DETALHE = "modelo"

    def __init__(self, codigo, nome, marca, tamanho, cor, preco, quantidade, modelo):
        super().__init__(codigo, nome, marca, tamanho, cor, preco, quantidade)
        self.modelo = modelo 

    @property
    def detalhe(self):
        return self.modelo

class Vestido(PecaDeRoupa):
    ROTULO_DETALHE = "comprimento"

    def __init__(self, codigo, nome, marca, tamanho, cor, preco, quantidade, comprimento):
        super().__init__(codigo, nome, marca, tamanho, cor, preco, quantidade)
        self.comprimento = comprimento  

    @property
    def detalhe(self):
        return self.comprimento

class Jaqueta(PecaDeRoupa):
    ROTULO_DETALHE = "material"

    def __init__(self, codigo, nome, marca, tamanho, cor, preco, quantidade, material):
        super().__init__(codigo, nome, marca, tamanho, cor, preco, quantidade)
        self.material = material  
    @property
    def detalhe(self):
        return self.material

class Acessorio(PecaDeRoupa):
    ROTULO_DETALHE = "categoria"

    def __init__(self, codigo, nome, marca, tamanho, cor, preco, quantidade, categoria):
        super().__init__(codigo, nome, marca, tamanho, cor, preco, quantidade)
        self.categoria = categoria 

    @property
    def detalhe(self):
        return self.categoria

TIPOS_DE_PECA = {
    classe.__name__: classe
    for classe in (Camiseta, Calca, Vestido, Jaqueta, Acessorio)
}


def criar_peca(tipo, codigo, nome, marca, tamanho, cor, preco, quantidade, detalhe):
    if tipo not in TIPOS_DE_PECA:
        raise ValueError(f"Tipo de peça desconhecido: {tipo!r}")
    return TIPOS_DE_PECA[tipo](codigo, nome, marca, tamanho, cor, preco, quantidade, detalhe)


def peca_de_dict(dados):
    return criar_peca(
        dados["tipo"], dados["codigo"], dados["nome"], dados["marca"],
        dados["tamanho"], dados["cor"], dados["preco"], dados["quantidade"],
        dados["detalhe"],
    )