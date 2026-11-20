"""
DEMONSTRAÇÃO AUTOMÁTICA:  python -m demo.demo_desacoplamento

Sobe broker e worker como PROCESSOS separados e prova:
  Cenário 1 - funcionamento normal (cliente só conhece o broker -> desacoplamento espacial)
  Cenário 2 - worker derrubado: cliente CONTINUA enviando; mensagens ficam na fila
              (desacoplamento temporal + retenção de dados)
  Cenário 3 - worker volta e processa o acumulado, sem perder nada, em ordem

TODO (dupla): cenário 4 — worker cai depois de executar e antes do ack (reentrega).
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time

from client.cliente_loja import ClienteLoja
from mq.cliente_broker import ClienteBroker

PORTA = 9100
URL = f"http://127.0.0.1:{PORTA}"
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def titulo(t):
    print(f"\n{'=' * 70}\n{t}\n{'=' * 70}", flush=True)


def subir(modulo, *args):
    return subprocess.Popen([sys.executable, "-u", "-m", modulo, *args], cwd=RAIZ)


def aguardar_broker():
    b = ClienteBroker(URL, timeout=1)
    for _ in range(50):
        try:
            b.estatisticas()
            return
        except Exception:
            time.sleep(0.1)
    raise RuntimeError("broker não subiu")


def main():
    tmp = tempfile.mkdtemp()
    broker = subir("broker.app_broker", "--porta", str(PORTA), "--db", os.path.join(tmp, "broker.db"))
    worker = None
    try:
        aguardar_broker()
        info = ClienteBroker(URL)
        cli = ClienteLoja(URL, nome="demo")

        titulo("CENÁRIO 1: funcionamento normal (cliente só conhece o broker)")
        worker = subir("workers.worker_loja", "--broker", URL)
        print(cli.chamar("adicionar_camiseta", {"id_peca": 1, "nome": "Camiseta Polo", "preco": 89.9, "tamanho": "M"}))
        print(cli.chamar("adicionar_calca", {"id_peca": 2, "nome": "Calça Jeans", "preco": 120.5, "material": "Denim"}))
        print(cli.chamar("registrar_venda", {"id_peca": 1, "quantidade": 2}))

        titulo("CENÁRIO 2: derrubando o worker — o cliente continua enviando")
        worker.kill(); worker.wait()
        print(">>> worker MORTO. Cadastrando 3 camisetas mesmo assim...")
        ids = [cli.enviar("adicionar_camiseta", {"id_peca": n, "nome": f"Camiseta {n}", "preco": 50.0, "tamanho": "G"})
               for n in (3, 4, 5)]
        print(f">>> 3 envios aceitos sem erro. Estado do broker: {info.estatisticas()}")

        titulo("CENÁRIO 3: worker volta e consome o acumulado")
        worker = subir("workers.worker_loja", "--broker", URL)
        for i in ids:
            r = cli.esperar(i, timeout=15)
            print("resposta:", r)
        print(f">>> Estado do broker: {info.estatisticas()}")
        print("\nFIM — nenhuma mensagem perdida.")
    finally:
        for p in (worker, broker):
            if p and p.poll() is None:
                p.kill()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
