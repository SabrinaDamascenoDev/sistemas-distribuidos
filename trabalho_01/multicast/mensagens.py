"""
Formato das mensagens multicast da questão 4 (representação externa em JSON).

    {
      "tipo": "ALERTA",                       NOTIFICACAO | ALERTA | ATUALIZACAO
      "mensagem": "Estoque baixo: ...",
      "timestamp": 1760200000,                segundos desde 1970 (epoch)
      "seq": 7                                número de sequência do servidor
    }

Cada mensagem cabe em um único datagrama UDP, então não é preciso cabeçalho
de tamanho (ao contrário do TCP): um recvfrom() devolve exatamente um datagrama.
"""

import json
import time

NOTIFICACAO = "NOTIFICACAO"
ALERTA = "ALERTA"
ATUALIZACAO = "ATUALIZACAO"
TIPOS = (NOTIFICACAO, ALERTA, ATUALIZACAO)

TAMANHO_MAXIMO_DATAGRAMA = 8192


def criar_mensagem(tipo, mensagem, seq=0, timestamp=None):
    tipo = tipo.upper()
    if tipo not in TIPOS:
        raise ValueError(f"Tipo de mensagem inválido: {tipo!r} (use {', '.join(TIPOS)})")
    return {
        "tipo": tipo,
        "mensagem": str(mensagem),
        "timestamp": int(time.time() if timestamp is None else timestamp),
        "seq": int(seq),
    }


def empacotar(mensagem):
    dados = json.dumps(mensagem, ensure_ascii=False).encode("utf-8")
    if len(dados) > TAMANHO_MAXIMO_DATAGRAMA:
        raise ValueError("Mensagem grande demais para um datagrama")
    return dados


def desempacotar(dados):
    mensagem = json.loads(dados.decode("utf-8"))
    if not isinstance(mensagem, dict) or mensagem.get("tipo") not in TIPOS:
        raise ValueError("Datagrama com formato desconhecido")
    return mensagem


def formatar(mensagem):
    hora = time.strftime("%H:%M:%S", time.localtime(mensagem["timestamp"]))
    return f"[{hora}] #{mensagem.get('seq', 0):<3} {mensagem['tipo']:<11} {mensagem['mensagem']}"