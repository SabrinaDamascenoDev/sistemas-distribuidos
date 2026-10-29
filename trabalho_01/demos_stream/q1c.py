"""
Q1-c: destino = arquivo (FileOutputStream).

Gera o arquivo dados/pecas.bin (use depois em q2c e q2b).
"""

import os

from models.exemplo import criar_loja_exemplo
from streams.loja_output_stream import LojaOutputStream

ARQUIVO = os.path.join("dados", "pecas.bin")


def main():
    pecas = criar_loja_exemplo().pecas
    os.makedirs("dados", exist_ok=True)

    with open(ARQUIVO, "wb") as arquivo:                
        with LojaOutputStream(arquivo, pecas, len(pecas)) as saida:
            saida.enviar()

    print(f"{len(pecas)} peças gravadas em {ARQUIVO} ({os.path.getsize(ARQUIVO)} bytes)")


if __name__ == "__main__":
    main()