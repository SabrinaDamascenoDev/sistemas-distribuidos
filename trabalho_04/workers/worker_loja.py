"""
CONSUMIDOR / WORKER DA LOJA.

Substitui o "servidor RPC" do Trabalho 2. Em vez de escutar uma porta, ele PUXA comandos da
fila "comandos" do broker, executa a lógica da loja e devolve o resultado na fila "reply_to".

Mensagem de comando:
  {"id_comando": "uuid", "metodo": "registrar_venda", "argumentos": {...}, "reply_to": "resp.x"}

Fluxo de cada comando:
  1. consumir (long polling)        o broker esconde a mensagem e entrega um recibo
  2. já processei este id_comando?  sim = é reentrega: reenvia a resposta guardada SEM reexecutar
  3. executar a lógica da loja
  4. salvar estado + id_comando no disco, numa única gravação atômica
  5. publicar a resposta em reply_to
  6. ack                            só agora o broker apaga a mensagem
Se o worker cair em qualquer ponto antes do passo 6, o broker reentrega a mensagem e o
passo 2 garante que o efeito acontece uma única vez:
  entrega at-least-once + processamento idempotente = efeito exactly-once.

Mensagens problemáticas:
  * malformadas (sem id_comando/metodo, não é objeto...)  -> nack sem reenfileirar -> DLQ
  * erro inesperado ao executar (bug, recurso fora)        -> nack com reenfileirar; depois de
    max_tentativas o broker manda para a DLQ. O estado em memória é restaurado do disco.
  * argumentos inválidos (erro do cliente)                 -> responde {"status": "erro"} e dá ack

Uso: python -m workers.worker_loja [--broker URL] [--estado dados/loja_estado.json]
                                   [--atraso S] [--visibilidade S] [--espera S] [--falhar-antes-ack]
"""
import argparse
import os
import threading
import time
from collections import OrderedDict

from mq.cliente_broker import ClienteBroker, ErroBroker
from services.loja_service import LojaService, METODOS_PERMITIDOS, METODOS_LEITURA
from workers.estado import ArmazenamentoEstado

FILA_COMANDOS = "comandos"
MAX_IDS_LEMBRADOS = 1000  # janela de deduplicação (reentregas acontecem em segundos)


class QuedaSimulada(Exception):
    """Usada nos testes no lugar de matar o processo."""


def _derrubar_processo():
    os._exit(1)  # morte abrupta: nada de finally, nada de ack


class WorkerLoja:
    def __init__(self, broker, caminho_estado=None, atraso=0.0, visibilidade=10.0, espera=5.0,
                 falhar_antes_ack=False):
        self.broker = broker
        self.atraso = atraso
        self.visibilidade = visibilidade
        self.espera = espera
        self.falhar_antes_ack = falhar_antes_ack
        self.ao_falhar = _derrubar_processo
        self.armazenamento = ArmazenamentoEstado(caminho_estado) if caminho_estado else None
        self.servico = LojaService()
        self.processados = OrderedDict()  # id_comando -> resultado já enviado
        self._parar = threading.Event()
        self._carregar_estado()

    # --------------------------------------------------------------- estado
    def _carregar_estado(self):
        self.servico = LojaService()
        self.processados = OrderedDict()
        dados = self.armazenamento.carregar() if self.armazenamento else None
        if dados:
            self.servico.importar(dados["loja"])
            self.processados = OrderedDict((i, r) for i, r in dados.get("processados", []))

    def _salvar_estado(self):
        if self.armazenamento:
            self.armazenamento.salvar({
                "loja": self.servico.exportar(),
                "processados": list(self.processados.items()),
            })

    def resumo_estado(self):
        return (f"{len(self.servico.estoque.itens)} peças, {len(self.servico.vendas)} vendas, "
                f"{len(self.processados)} comandos lembrados")

    # --------------------------------------------------------------- execução
    @staticmethod
    def _comando_valido(cmd):
        return (isinstance(cmd, dict)
                and isinstance(cmd.get("id_comando"), str) and cmd["id_comando"]
                and isinstance(cmd.get("metodo"), str)
                and isinstance(cmd.get("argumentos", {}), dict)
                and (cmd.get("reply_to") is None or isinstance(cmd["reply_to"], str)))

    def _executar(self, cmd):
        metodo = cmd["metodo"]
        if metodo not in METODOS_PERMITIDOS:
            return {"status": "erro", "mensagem": f"método desconhecido: {metodo}"}
        try:
            return getattr(self.servico, metodo)(cmd.get("argumentos", {}))
        except (KeyError, TypeError, ValueError) as e:
            return {"status": "erro", "mensagem": f"argumentos inválidos: {e!r}"}

    def _responder(self, cmd, resultado):
        if cmd.get("reply_to"):
            self.broker.publicar(cmd["reply_to"], {"id_comando": cmd["id_comando"], "resultado": resultado})

    def processar(self, msg):
        cmd = msg["corpo"]
        if not self._comando_valido(cmd):
            print(f"[worker] mensagem {msg['id']} malformada -> DLQ: {str(cmd)[:60]}", flush=True)
            self.broker.nack(msg, reenfileirar=False, motivo="mensagem malformada")
            return

        id_cmd = cmd["id_comando"]
        if id_cmd in self.processados:
            print(f"[worker] {cmd['metodo']} ({id_cmd[:8]}) JÁ processado — reentrega nº "
                  f"{msg.get('tentativa')}: reenviando a resposta sem reexecutar", flush=True)
            self._responder(cmd, self.processados[id_cmd])
            self.broker.ack(msg)
            return

        if self.atraso:
            time.sleep(self.atraso)  # simula processamento lento
        try:
            resultado = self._executar(cmd)
        except Exception as e:  # falha inesperada: devolve para a fila
            print(f"[worker] erro inesperado em {cmd['metodo']} ({id_cmd[:8]}): {e!r} — devolvendo "
                  f"para a fila (tentativa {msg.get('tentativa')})", flush=True)
            self._carregar_estado()  # descarta qualquer alteração pela metade
            self.broker.nack(msg, reenfileirar=True, motivo=repr(e))
            return

        if cmd["metodo"] not in METODOS_LEITURA:
            self.processados[id_cmd] = resultado
            while len(self.processados) > MAX_IDS_LEMBRADOS:
                self.processados.popitem(last=False)
            self._salvar_estado()  # estado + id juntos, de forma atômica
            if self.falhar_antes_ack:
                print(f"[worker] >>> SIMULANDO QUEDA após executar {cmd['metodo']} ({id_cmd[:8]}): "
                      f"estado salvo, mas SEM resposta e SEM ack", flush=True)
                self.ao_falhar()

        print(f"[worker] executou {cmd['metodo']} ({id_cmd[:8]})", flush=True)
        self._responder(cmd, resultado)
        self.broker.ack(msg)

    # --------------------------------------------------------------- laço
    def rodar(self):
        print(f"[worker] estado: {self.resumo_estado()} | aguardando comandos na fila "
              f"'{FILA_COMANDOS}'...", flush=True)
        broker_fora = False
        while not self._parar.is_set():
            try:
                msg = self.broker.consumir(FILA_COMANDOS, visibilidade=self.visibilidade, espera=self.espera)
                if broker_fora:
                    print("[worker] broker voltou", flush=True)
                    broker_fora = False
                if msg:
                    self.processar(msg)
                elif not self.espera:
                    time.sleep(0.2)  # polling curto (modo sem long polling)
            except ErroBroker as e:
                if not broker_fora:
                    print(f"[worker] {e} — tentando de novo a cada 1 s", flush=True)
                    broker_fora = True
                time.sleep(1)
        getattr(self.broker, "fechar", lambda: None)()

    def parar(self):
        self._parar.set()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--broker", default="http://127.0.0.1:9000")
    ap.add_argument("--estado", default="dados/loja_estado.json",
                    help="arquivo onde o estado da loja é salvo (um worker por arquivo)")
    ap.add_argument("--atraso", type=float, default=0.0, help="simula processamento lento (s)")
    ap.add_argument("--visibilidade", type=float, default=10.0,
                    help="segundos que a mensagem fica escondida antes de ser reentregue")
    ap.add_argument("--espera", type=float, default=5.0, help="long polling (s); 0 = polling curto")
    ap.add_argument("--sem-keep-alive", action="store_true", help="abre uma conexão TCP por requisição")
    ap.add_argument("--falhar-antes-ack", action="store_true",
                    help="derruba o worker logo após executar o 1º comando de escrita, antes do ack")
    a = ap.parse_args()
    try:
        WorkerLoja(ClienteBroker(a.broker, keep_alive=not a.sem_keep_alive), a.estado, a.atraso,
                   a.visibilidade, a.espera, a.falhar_antes_ack).rodar()
    except KeyboardInterrupt:
        pass