"""
Q2-d: origem = cliente remoto (TCP).  Este programa é o SERVIDOR que recebe.
    python3 -m demos_stream.q2d [porta]     
"""

import socket
import sys

from streams.loja_input_stream import LojaInputStream

HOST = "0.0.0.0"  
PORTA = int(sys.argv[1]) if len(sys.argv) > 1 else 5051


def atender(conexao, endereco):
    print(f"Cliente conectado: {endereco}")
    with conexao, conexao.makefile("rb") as origem:
        with LojaInputStream(origem) as entrada:
            pecas = entrada.ler_pecas()

    print(f"Recebi {len(pecas)} peças:")
    for peca in pecas:
        print("  ", peca)


def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as servidor:
        servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        servidor.bind((HOST, PORTA))
        servidor.listen()
        print(f"Servidor aguardando na porta {PORTA}...")
        while True:
            conexao, endereco = servidor.accept()  
            try:
                atender(conexao, endereco)
            except (EOFError, ConnectionError) as erro:
                print("Falha ao receber:", erro)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nServidor encerrado.")