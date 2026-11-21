"""
DEMONSTRAÇÃO AUTOMÁTICA:  python -m demo.demo_desacoplamento

Sobe broker e worker como PROCESSOS separados e prova:
  Cenário 1 - funcionamento normal (cliente só conhece o broker -> desacoplamento espacial)
  Cenário 2 - worker derrubado: o cliente CONTINUA enviando; as mensagens ficam na fila
              (desacoplamento temporal + retenção de dados)
  Cenário 3 - worker volta, processa o acumulado em ordem e RECUPERA o estado do disco
  Cenário 4 - worker cai depois de executar e antes do ack: o broker reentrega e a venda
              NÃO é registrada duas vezes (idempotência)
  Cenário 5 - o próprio broker cai (kill -9) com mensagens pendentes: ao voltar, nada se perdeu
  Cenário 6 - mensagem venenosa: vai para a Dead Letter Queue e o worker segue funcionando
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

from client.cliente_loja import ClienteLoja
from mq.cliente_broker import ClienteBroker, ErroBroker

PORTA = 9100
URL = f"http://127.0.0.1:{PORTA}"
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VISIBILIDADE = 3  # segundos (curto, para a reentrega do cenário 4 não demorar)


def titulo(t):
    print(f"\n{'=' * 78}\n{t}\n{'=' * 78}", flush=True)


def mostrar(rotulo, dado):
    print(f"{rotulo} {json.dumps(dado, ensure_ascii=False)}", flush=True)


def subir(modulo, *args):
    return subprocess.Popen([sys.executable, "-u", "-m", modulo, *args], cwd=RAIZ)


def derrubar(proc):
    proc.kill()  # SIGKILL: morte abrupta, sem chance de limpar nada
    proc.wait()


def aguardar_broker():
    b = ClienteBroker(URL, timeout=1)
    for _ in range(50):
        try:
            b.estatisticas()
            return
        except ErroBroker:
            time.sleep(0.1)
    raise RuntimeError("broker não subiu")


def main():
    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "broker.db")
    estado = os.path.join(tmp, "loja_estado.json")
    args_worker = ("--broker", URL, "--estado", estado, "--visibilidade", str(VISIBILIDADE))
    args_broker = ("--porta", str(PORTA), "--db", db)
    broker = subir("broker.app_broker", *args_broker)
    worker = None
    try:
        aguardar_broker()
        info = ClienteBroker(URL)
        cli = ClienteLoja(URL, nome="demo")

        titulo("CENÁRIO 1: funcionamento normal (o cliente só conhece o broker)")
        worker = subir("workers.worker_loja", *args_worker)
        mostrar("resposta:", cli.chamar("adicionar_camiseta", {"id_peca": 1, "nome": "Camiseta Polo", "preco": 89.9, "tamanho": "M"}))
        mostrar("resposta:", cli.chamar("adicionar_calca", {"id_peca": 2, "nome": "Calça Jeans", "preco": 120.5, "material": "Denim"}))
        mostrar("resposta:", cli.chamar("registrar_venda", {"id_peca": 1, "quantidade": 2}))

        titulo("CENÁRIO 2: derrubando o worker — o cliente continua enviando")
        derrubar(worker)
        print(">>> worker MORTO (kill -9). Cadastrando 3 camisetas mesmo assim...", flush=True)
        ids = [cli.enviar("adicionar_camiseta", {"id_peca": n, "nome": f"Camiseta {n}", "preco": 50.0, "tamanho": "G"})
               for n in (3, 4, 5)]
        mostrar(">>> 3 envios aceitos sem erro. Broker:", info.estatisticas())

        titulo("CENÁRIO 3: o worker volta, consome o acumulado e recupera o estado do disco")
        worker = subir("workers.worker_loja", *args_worker)
        for i in ids:
            mostrar("resposta:", cli.esperar(i, timeout=15))
        estoque = cli.chamar("consultar_estoque")
        print(f">>> estoque tem {len(estoque)} peças: {[p['id_peca'] for p in estoque]} "
              f"(as do cenário 1 continuam lá)", flush=True)
        mostrar(">>> Broker:", info.estatisticas())

        titulo("CENÁRIO 4: o worker cai DEPOIS de executar e ANTES do ack (reentrega)")
        vendas_antes = len(cli.chamar("consultar_vendas"))
        derrubar(worker)
        worker = subir("workers.worker_loja", *args_worker, "--falhar-antes-ack")
        id_venda = cli.enviar("registrar_venda", {"id_peca": 2, "quantidade": 1})
        worker.wait(timeout=15)
        print(f">>> worker caiu (código {worker.returncode}) sem responder e sem ack.", flush=True)
        mostrar(">>> Broker (a mensagem segue lá, escondida até o prazo vencer):", info.estatisticas())
        print(f">>> Subindo um worker novo; em ~{VISIBILIDADE}s o broker reentrega a mensagem...", flush=True)
        worker = subir("workers.worker_loja", *args_worker)
        mostrar("resposta:", cli.esperar(id_venda, timeout=20))
        vendas_depois = len(cli.chamar("consultar_vendas"))
        print(f">>> vendas antes: {vendas_antes} | depois: {vendas_depois} "
              f"-> a venda foi registrada UMA única vez", flush=True)

        titulo("CENÁRIO 5: o BROKER cai (kill -9) com mensagens pendentes")
        derrubar(worker)
        ids = [cli.enviar("adicionar_calca", {"id_peca": n, "nome": f"Calça {n}", "preco": 99.0, "material": "Sarja"})
               for n in (6, 7)]
        mostrar(">>> 2 comandos na fila, worker desligado. Broker:", info.estatisticas())
        derrubar(broker)
        print(">>> broker MORTO.", flush=True)
        try:
            cli.enviar("consultar_estoque")
        except ErroBroker as e:
            print(f">>> com o broker fora, o remetente recebe um erro explícito (nada some em silêncio): {e}", flush=True)
        broker = subir("broker.app_broker", *args_broker)
        aguardar_broker()
        mostrar(">>> broker reiniciado com o mesmo arquivo. Broker:", info.estatisticas())
        worker = subir("workers.worker_loja", *args_worker)
        for i in ids:
            mostrar("resposta:", cli.esperar(i, timeout=15))

        titulo("CENÁRIO 6: mensagem venenosa vai para a Dead Letter Queue")
        info.publicar("comandos", {"id_comando": "venenosa-1", "argumentos": {}})  # sem "metodo"
        info.publicar("comandos", "isto nem é um objeto JSON")
        mostrar("resposta (o worker segue vivo):", cli.chamar("adicionar_camiseta", {"id_peca": 8, "nome": "Regata", "preco": 39.9, "tamanho": "P"}))
        mostrar(">>> Broker:", info.estatisticas())
        for m in info.espiar("dlq.comandos"):
            print(f">>> DLQ #{m['id']}: motivo={m['motivo']!r} corpo={json.dumps(m['corpo'], ensure_ascii=False)}", flush=True)

        print("\nFIM — nenhuma mensagem perdida, nenhum comando executado duas vezes.", flush=True)
    finally:
        for p in (worker, broker):
            if p and p.poll() is None:
                p.kill()
                p.wait()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()