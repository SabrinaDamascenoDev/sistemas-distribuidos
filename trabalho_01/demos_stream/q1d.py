"""
Q1-d: destino = servidor remoto (TCP).  Este programa é o CLIENTE que envia.

1) Em um terminal:  python -m demos_stream.q2d_servidor_tcp
2) Em outro:        python -m demos_stream.q1d_cliente_tcp [host] [porta]
"""

import socket
import sys

from models.exemplo import criar_loja_exemplo
from streams.loja_output_stream import LojaOutputStream

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORTA = int(sys.argv[2]) if len(sys.argv) > 2 else 5051


def main():
    pecas = criar_loja_exemplo().pecas

    with socket.create_connection((HOST, PORTA)) as sock:
        print(f"Conectado a {HOST}:{PORTA}. Enviando {len(pecas)} peças...")
        with sock.makefile("wb") as destino:
            with LojaOutputStream(destino, pecas, len(pecas)) as saida:
                saida.enviar()
    print("Envio concluído.")


if __name__ == "__main__":
    main()