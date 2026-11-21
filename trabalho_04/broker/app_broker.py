"""
Ponto de entrada do broker:
  python -m broker.app_broker [--porta 9000] [--db dados/broker.db] [--max-tentativas 3] [--sync FULL]
"""
import argparse
import os

from broker.fila_broker import BrokerFilas, MODOS_SYNC
from broker.servidor_http import ServidorBroker

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--porta", type=int, default=9000)
    ap.add_argument("--db", default="dados/broker.db")
    ap.add_argument("--max-tentativas", type=int, default=3,
                    help="entregas sem ack antes de mandar a mensagem para a DLQ")
    ap.add_argument("--sync", choices=MODOS_SYNC, default="FULL",
                    help="FULL = fsync em todo commit; NORMAL = mais rápido, menos durável")
    a = ap.parse_args()
    os.makedirs(os.path.dirname(a.db) or ".", exist_ok=True)
    srv = ServidorBroker(BrokerFilas(a.db, a.max_tentativas, a.sync), a.host, a.porta)
    print(f"[broker] filas persistentes em {a.db} | http://{a.host}:{a.porta} "
          f"| max_tentativas={a.max_tentativas} sync={a.sync}", flush=True)
    try:
        srv.iniciar()
    except KeyboardInterrupt:
        print("\n[broker] encerrado")