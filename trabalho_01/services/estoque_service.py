from services.erros import LojaError

class EstoqueService:

    def __init__(self, loja):
        self.loja = loja

    def listar_pecas(self):
        return list(self.loja.pecas)

    def buscar_peca(self, codigo):
        for peca in self.loja.pecas:
            if peca.codigo == codigo:
                return peca
        return None

    def adicionar_peca(self, peca):
        if peca.preco < 0 or peca.quantidade < 0:
            raise LojaError("Preço e quantidade não podem ser negativos")
        if self.buscar_peca(peca.codigo) is not None:
            raise LojaError(f"Já existe uma peça com o código {peca.codigo}")
        self.loja.pecas.append(peca)
        return peca

    def remover_peca(self, codigo):
        peca = self.buscar_peca(codigo)
        if peca is None:
            raise LojaError(f"Peça {codigo} não encontrada")
        self.loja.pecas.remove(peca)
        return peca