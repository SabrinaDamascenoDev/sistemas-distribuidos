"""
CONSUMIDOR / WORKER DA LOJA.

Substitui o "servidor RPC" do Trabalho 2. Em vez de escutar uma porta, ele PUXA comandos da
fila "comandos" do broker, executa a lógica da loja e devolve o resultado na fila "reply_to".

Mensagem de comando:
  {"id_comando": "uuid", "metodo": "registrar_venda", "argumentos": {...}, "reply_to": "resp.x"}

Fluxo: consumir -> executar -> responder -> ACK (só no fim; se cair antes, o broker reentrega).

TODO (dupla): o estado (estoque/vendas) está só em memória e some se o worker cair.
              Salvar o estado em disco e evitar executar o mesmo comando duas vezes
              (reentrega at-least-once!) usando o id_comando.

Uso: python -m workers.worker_loja [--broker URL] [--atraso S]
"""
import argparse
import time

from mq.cliente_broker import ClienteBroker, ErroBroker
from services.loja_service import LojaService, METODOS_PERMITIDOS

FILA_COMANDOS = "comandos"


class WorkerLoja:
    def __init__(self, broker, atraso=0.0):
        self.broker = broker
        self.atraso = atraso
        self.servico = LojaService()

    def _executar(self, cmd):
        metodo = cmd.get("metodo")
        if metodo not in METODOS_PERMITIDOS:
            return {"status": "erro", "mensagem": f"método desconhecido: {metodo}"}
        try:
            return getattr(self.servico, metodo)(cmd.get("argumentos", {}))
        except (KeyError, TypeError) as e:
            return {"status": "erro", "mensagem": f"argumentos inválidos: {e}"}

    def processar(self, msg):
        cmd = msg["corpo"]
        if self.atraso:
            time.sleep(self.atraso)  # simula processamento lento
        resultado = self._executar(cmd)
        print(f"[worker] executou {cmd['metodo']} ({cmd['id_comando'][:8]})", flush=True)
        if cmd.get("reply_to"):
            self.broker.publicar(cmd["reply_to"], {"id_comando": cmd["id_comando"], "resultado": resultado})
        self.broker.ack(msg)

    def rodar(self):
        print("[worker] aguardando comandos na fila 'comandos'...", flush=True)
        while True:
            try:
                msg = self.broker.consumir(FILA_COMANDOS, visibilidade=10)
                if msg:
                    self.processar(msg)
                else:
                    time.sleep(0.2)  # fila vazia: espera um pouco (polling)
            except ErroBroker as e:
                print(f"[worker] {e} — tentando de novo em 1s", flush=True)
                time.sleep(1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--broker", default="http://127.0.0.1:9000")
    ap.add_argument("--atraso", type=float, default=0.0)
    a = ap.parse_args()
    try:
        WorkerLoja(ClienteBroker(a.broker), a.atraso).rodar()
    except KeyboardInterrupt:
        pass
