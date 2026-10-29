"""
Q1-b: destino = saída padrão (System.out).
python3 -m demos_stream.q1b
"""

import sys

from models.exemplo import criar_loja_exemplo
from streams.loja_output_stream import LojaOutputStream


class DestinoHexa:
    """imprime os bytes em hexadecimal (só para ler no terminal)."""

    def write(self, dados):
        sys.stdout.write(dados.hex(" ") + "\n")
        return len(dados)

    def flush(self):
        sys.stdout.flush()


def main():
    pecas = criar_loja_exemplo().pecas

    if sys.stdout.isatty():
        destino = DestinoHexa()       
    else:
        destino = sys.stdout.buffer    

    with LojaOutputStream(destino, pecas, len(pecas)) as saida:
        saida.enviar()


if __name__ == "__main__":
    main()