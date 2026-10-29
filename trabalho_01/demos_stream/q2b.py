"""
Q2-b: origem = entrada padrão (System.in).

    python3 -m demos_stream.q1b | python3 -m demos_stream.q2b
"""

import sys

from streams.loja_input_stream import LojaInputStream


def main():
    with LojaInputStream(sys.stdin.buffer) as entrada:
        pecas = entrada.ler_pecas()

    print(f"Recebi {len(pecas)} peças pela entrada padrão:")
    for peca in pecas:
        print("  ", peca)


if __name__ == "__main__":
    main()