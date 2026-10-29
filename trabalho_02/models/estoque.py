class Estoque:
    def __init__(self):
        self.itens = [] # Agregação (Lista de objetos PecaRoupa)
        
    def adicionar_item(self, item):
        self.itens.append(item)
        
    def to_list(self):
        return [item.to_dict() for item in self.itens]
