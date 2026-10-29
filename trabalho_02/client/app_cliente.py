import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rpc.cliente_stub import ClienteProxy
import json

def imprimir_json(dado):
    print(json.dumps(dado, indent=2, ensure_ascii=False))

def main():
    loja_stub = ClienteProxy("127.0.0.1", 8000, "ServicoLoja")

    print("1. Adicionando Camiseta")
    args_cam = {"id_peca": 1, "nome": "Camiseta Polo", "preco": 89.90, "tamanho": "M"}
    res = loja_stub.doOperation("adicionar_camiseta", args_cam)
    imprimir_json(res)

    print("\n 2. Adicionando Calça ")
    args_cal = {"id_peca": 2, "nome": "Calça Jeans", "preco": 120.50, "material": "Denim"}
    res = loja_stub.doOperation("adicionar_calca", args_cal)
    imprimir_json(res)

    print("\n 3. Consultando Estoque Remoto ")
    res = loja_stub.doOperation("consultar_estoque", {})
    imprimir_json(res)

    print("\n 4. Registrando Venda ")
    args_venda = {"id_peca": 1, "quantidade": 2}
    res = loja_stub.doOperation("registrar_venda", args_venda)
    imprimir_json(res)

if __name__ == "__main__":
    main()
