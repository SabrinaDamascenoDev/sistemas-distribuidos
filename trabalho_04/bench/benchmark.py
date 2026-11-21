"""
BENCHMARK: quanto custa o intermediário?

  python -m bench.benchmark [--n 150] [--lote 300]

Configurações comparadas:
  T2   RPC direto (cliente -> servidor), o baseline do Trabalho 2 (lido de ../trabalho_02)
  T4a  fila, versão inicial: polling curto (worker 0,2 s, cliente 0,1 s) e uma conexão TCP
       por requisição
  T4b  fila otimizada (padrão atual): long polling + conexões persistentes (keep-alive)
  T4c  T4b com o broker em synchronous=NORMAL (menos fsync, menos durável)

Medidas:
  * latência de ida e volta de uma chamada síncrona (leitura e escrita), em ms;
  * requisições HTTP e conexões TCP que o broker recebeu por chamada;
  * vazão no modo assíncrono: publicar `lote` comandos sem esperar resposta e medir em quanto
    tempo o worker esvazia a fila.
O resultado é impresso e salvo em bench/resultados.md.
"""
import argparse
import json
import os
import platform
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime

from client.cliente_loja import ClienteLoja
from mq.cliente_broker import ClienteBroker, ErroBroker

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR_T2 = os.path.join(os.path.dirname(RAIZ), "trabalho_02")
AQUECIMENTO = 20

T2_SERVIDOR = """
import sys
from services.loja_service import LojaService
from rpc.servidor_skeleton import ServidorRPC
s = ServidorRPC('127.0.0.1', int(sys.argv[1]))
s.registrar_objeto('ServicoLoja', LojaService())
s.iniciar()
"""

T2_CLIENTE = """
import json, sys, time
from rpc.cliente_stub import ClienteProxy
porta, n, aquecimento = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
p = ClienteProxy('127.0.0.1', porta, 'ServicoLoja')
for _ in range(aquecimento):
    p.doOperation('consultar_estoque', {})
def medir(f):
    ts = []
    for i in range(n):
        t = time.perf_counter(); f(i); ts.append(time.perf_counter() - t)
    return ts
leitura = medir(lambda i: p.doOperation('consultar_estoque', {}))
escrita = medir(lambda i: p.doOperation('adicionar_camiseta',
                {'id_peca': i, 'nome': 'B', 'preco': 1.0, 'tamanho': 'M'}))
print(json.dumps({'leitura': leitura, 'escrita': escrita}))
"""


def porta_livre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def esperar_porta(porta, limite=10):
    fim = time.time() + limite
    while time.time() < fim:
        try:
            socket.create_connection(("127.0.0.1", porta), timeout=0.2).close()
            return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError(f"nada escutando na porta {porta}")


def resumo(amostras):
    ms = sorted(t * 1000 for t in amostras)
    return {"mediana": statistics.median(ms), "p95": ms[int(0.95 * (len(ms) - 1))], "media": statistics.mean(ms)}


def encerrar(*procs):
    for p in procs:
        if p and p.poll() is None:
            p.kill()
            p.wait()


# ------------------------------------------------------------------ T2
def medir_t2(n):
    if not os.path.isdir(DIR_T2):
        return None
    porta = porta_livre()
    srv = subprocess.Popen([sys.executable, "-c", T2_SERVIDOR, str(porta)], cwd=DIR_T2,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        esperar_porta(porta)
        saida = subprocess.run([sys.executable, "-c", T2_CLIENTE, str(porta), str(n), str(AQUECIMENTO)],
                               cwd=DIR_T2, capture_output=True, text=True, check=True).stdout
        dados = json.loads(saida)
    finally:
        encerrar(srv)
    escrita = dados["escrita"]
    return {"leitura": resumo(dados["leitura"]), "escrita": resumo(escrita),
            "req_por_op": 1.0, "conexoes_por_op": 1.0,
            "publicacao": None, "processamento": len(escrita) / sum(escrita)}


# ------------------------------------------------------------------ T4
def medir_t4(n, lote, espera, keep_alive, sync):
    tmp = tempfile.mkdtemp()
    porta = porta_livre()
    url = f"http://127.0.0.1:{porta}"
    broker = subprocess.Popen([sys.executable, "-m", "broker.app_broker", "--porta", str(porta),
                               "--db", os.path.join(tmp, "b.db"), "--sync", sync],
                              cwd=RAIZ, stdout=subprocess.DEVNULL)
    args_worker = ["--broker", url, "--estado", os.path.join(tmp, "estado.json"), "--espera", str(espera)]
    if not keep_alive:
        args_worker.append("--sem-keep-alive")
    worker = None
    cli = ClienteLoja(url, nome="bench", espera=espera, keep_alive=keep_alive)
    info = ClienteBroker(url)
    try:
        esperar_porta(porta)
        worker = subprocess.Popen([sys.executable, "-m", "workers.worker_loja", *args_worker],
                                  cwd=RAIZ, stdout=subprocess.DEVNULL)
        for _ in range(AQUECIMENTO):
            if cli.chamar("consultar_estoque", timeout=15) is None:
                raise RuntimeError("worker não respondeu no aquecimento")

        def medir(metodo, argumentos):
            ts = []
            for i in range(n):
                t = time.perf_counter()
                if cli.chamar(metodo, argumentos(i), timeout=15) is None:
                    raise RuntimeError(f"{metodo} sem resposta")
                ts.append(time.perf_counter() - t)
            return ts

        m0 = info.metricas()
        leitura = medir("consultar_estoque", lambda i: {})
        m1 = info.metricas()
        escrita = medir("adicionar_camiseta",
                        lambda i: {"id_peca": i, "nome": "B", "preco": 1.0, "tamanho": "M"})

        inicio = time.perf_counter()
        for i in range(lote):
            cli.enviar("adicionar_camiseta", {"id_peca": 10_000 + i, "nome": "L", "preco": 1.0, "tamanho": "M"},
                       quer_resposta=False)
        publicado = time.perf_counter()
        while "comandos" in info.estatisticas():
            time.sleep(0.02)
        drenado = time.perf_counter()
    finally:
        cli.fechar()
        info.fechar()
        encerrar(worker, broker)
        shutil.rmtree(tmp, ignore_errors=True)

    req = m1["requisicoes_http"] - m0["requisicoes_http"] - 1   # -1: a própria leitura de métricas
    con = m1["conexoes_tcp"] - m0["conexoes_tcp"] - (0 if keep_alive else 1)
    return {"leitura": resumo(leitura), "escrita": resumo(escrita),
            "req_por_op": req / n, "conexoes_por_op": con / n,
            "publicacao": lote / (publicado - inicio), "processamento": lote / (drenado - inicio)}


CONFIGS = [
    ("T2: RPC direto (baseline)", None),
    ("T4a: fila, polling curto, sem keep-alive", dict(espera=0, keep_alive=False, sync="FULL")),
    ("T4b: fila, long polling + keep-alive", dict(espera=5, keep_alive=True, sync="FULL")),
    ("T4c: T4b + synchronous=NORMAL", dict(espera=5, keep_alive=True, sync="NORMAL")),
]


def tabela(resultados, n, lote):
    def f(v, casas=1):
        return "—" if v is None else f"{v:.{casas}f}"
    linhas = [
        f"Ambiente: {platform.system()} {platform.release()}, Python {platform.python_version()}, "
        f"{os.cpu_count()} CPUs, {datetime.now():%d/%m/%Y %H:%M}. "
        f"n = {n} chamadas síncronas por medida; lote assíncrono = {lote} comandos.",
        "",
        "| Configuração | Leitura mediana (ms) | Leitura p95 (ms) | Escrita mediana (ms) | Escrita p95 (ms) "
        "| Req. HTTP por chamada | Conexões TCP por chamada | Publicação assíncrona (msg/s) | Processamento (msg/s) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for nome, r in resultados:
        if r is None:
            linhas.append(f"| {nome} | (pasta ../trabalho_02 não encontrada) |||||||| ")
            continue
        linhas.append(
            f"| {nome} | {f(r['leitura']['mediana'], 2)} | {f(r['leitura']['p95'], 2)} "
            f"| {f(r['escrita']['mediana'], 2)} | {f(r['escrita']['p95'], 2)} "
            f"| {f(r['req_por_op'])} | {f(r['conexoes_por_op'])} "
            f"| {f(r['publicacao'], 0)} | {f(r['processamento'], 0)} |")
    linhas += ["", "No T2 não há modo assíncrono; a coluna de processamento mostra a vazão das escritas síncronas."]
    return "\n".join(linhas)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=150, help="chamadas síncronas por medida")
    ap.add_argument("--lote", type=int, default=300, help="comandos no teste de vazão assíncrona")
    a = ap.parse_args()
    resultados = []
    for nome, cfg in CONFIGS:
        print(f"medindo {nome} ...", flush=True)
        try:
            r = medir_t2(a.n) if cfg is None else medir_t4(a.n, a.lote, **cfg)
        except (RuntimeError, ErroBroker, subprocess.CalledProcessError) as e:
            print(f"  falhou: {e}", flush=True)
            r = None
        resultados.append((nome, r))
    texto = tabela(resultados, a.n, a.lote)
    print("\n" + texto)
    with open(os.path.join(RAIZ, "bench", "resultados.md"), "w", encoding="utf-8") as fsaida:
        fsaida.write("# Resultados do benchmark\n\n" + texto + "\n")


if __name__ == "__main__":
    main()