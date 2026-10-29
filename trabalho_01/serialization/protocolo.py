"""
QUESTÃO 3 - Protocolo de comunicação (usado por cliente E servidor).

Camadas de uma mensagem:

  1) OBJETO  ->  dict            (peca.para_dict()  /  peca_de_dict())
  2) dict    ->  bytes JSON      (empacotar()       /  desempacotar())
  3) bytes   ->  socket TCP      (enviar()          /  receber())

Formato externo escolhido: JSON em UTF-8
"""

import json
import struct

TAMANHO_MAXIMO = 1_000_000  


def empacotar(mensagem):
    return json.dumps(mensagem, ensure_ascii=False).encode("utf-8")


def desempacotar(corpo):
    return json.loads(corpo.decode("utf-8"))


def enviar(sock, mensagem):
    corpo = empacotar(mensagem)
    sock.sendall(struct.pack(">I", len(corpo)) + corpo)


def _receber_exato(sock, n):
    partes = []
    faltam = n
    while faltam > 0:
        parte = sock.recv(faltam)
        if not parte:  
            return None
        partes.append(parte)
        faltam -= len(parte)
    return b"".join(partes)


def receber(sock):
    cabecalho = _receber_exato(sock, 4)
    if cabecalho is None:
        return None
    tamanho = struct.unpack(">I", cabecalho)[0]
    if tamanho > TAMANHO_MAXIMO:
        raise ValueError(f"Mensagem grande demais: {tamanho} bytes")
    corpo = _receber_exato(sock, tamanho)
    if corpo is None:
        return None
    return desempacotar(corpo)