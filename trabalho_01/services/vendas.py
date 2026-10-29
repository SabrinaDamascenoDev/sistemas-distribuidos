from abc import ABC, abstractmethod

class Vendas(ABC):

    @abstractmethod
    def vender(self, codigo_peca, quantidade):
        """Realiza a venda e devolve um objeto Venda."""

    @abstractmethod
    def listar_vendas(self):
        """Devolve a lista de vendas realizadas."""

    @abstractmethod
    def total_vendido(self):
        """Devolve o valor total (R$) de todas as vendas."""