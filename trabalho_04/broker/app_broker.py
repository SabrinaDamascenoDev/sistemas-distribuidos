"""Ponto de entrada do broker:  python -m broker.app_broker [--porta 9000] [--db dados/broker.db]"""
import argparse
import os

from broker.fila_broker import BrokerFilas
from broker.servidor_http import ServidorBroker

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--porta", type=int, default=9000)
    ap.add_argument("--db", default="dados/broker.db")
    a = ap.parse_args()
    os.makedirs(os.path.dirname(a.db) or ".", exist_ok=True)
    srv = ServidorBroker(BrokerFilas(a.db), a.host, a.porta)
    print(f"[broker] filas persistentes em {a.db} | http://{a.host}:{a.porta}", flush=True)
    try:
        srv.iniciar()
    except KeyboardInterrupt:
        print("\n[broker] encerrado")
