from datetime import datetime
from models.venda import Venda
from services.erros import LojaError
from services.vendas import Vendas

class VendasService(Vendas):
    def __init__(self, estoque_service):
        self.estoque = estoque_service
        self._vendas = []
        self._proximo_codigo = 1

    def vender(self, codigo_peca, quantidade):
        if quantidade <= 0:
            raise LojaError("A quantidade deve ser maior que zero")

        peca = self.estoque.buscar_peca(codigo_peca)
        if peca is None:
            raise LojaError(f"Peça {codigo_peca} não encontrada")
        if peca.quantidade < quantidade:
            raise LojaError(f"Estoque insuficiente de '{peca.nome}' "
                             f"(disponível: {peca.quantidade})")

        peca.quantidade -= quantidade  
        venda = Venda(
            codigo=self._proximo_codigo,
            codigo_peca=peca.codigo,
            nome_peca=peca.nome,
            quantidade=quantidade,
            valor_total=peca.preco * quantidade,
            data_hora=datetime.now().isoformat(timespec="seconds"),
        )
        self._proximo_codigo += 1
        self._vendas.append(venda)
        return venda

    def listar_vendas(self):
        return list(self._vendas)

    def total_vendido(self):
        return sum(venda.valor_total for venda in self._vendas)