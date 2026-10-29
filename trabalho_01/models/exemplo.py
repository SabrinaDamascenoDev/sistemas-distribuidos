from models.loja import Loja
from models.peca_de_roupa import Camiseta, Calca, Vestido, Jaqueta, Acessorio

# exemplo
def criar_loja_exemplo():
    pecas = [
        Camiseta(1, "Camiseta Básica", "Hering", "M", "branca", 49.90, 20, "curta"),
        Calca(2, "Calça Jeans Slim", "Levi's", "40", "azul", 199.90, 10, "jeans"),
        Vestido(3, "Vestido Floral", "Farm", "P", "estampado", 259.00, 5, "midi"),
        Jaqueta(4, "Jaqueta de Couro", "Zara", "G", "preta", 499.90, 3, "couro"),
        Acessorio(5, "Cinto Social", "Colcci", "U", "marrom", 79.90, 15, "cinto"),
    ]
    return Loja("Loja Estilo UFC", "12.345.678/0001-90", pecas)