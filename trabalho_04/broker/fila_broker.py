"""
BROKER DE FILAS DE MENSAGENS (o "intermediário" da comunicação indireta).

Produtores e consumidores NUNCA se falam: só conhecem o broker.
O broker guarda as mensagens em disco (SQLite) até alguém consumir E confirmar.

Garantias implementadas:
  * Persistência em disco: a mensagem sobrevive à queda do produtor, do consumidor
    e do próprio broker.
  * Ordem FIFO por fila.
  * ack + visibility timeout: consumir() NÃO apaga a mensagem, só a esconde por alguns
    segundos. Só o ack() apaga. Se o consumidor cair antes do ack, o prazo vence e a
    mensagem volta para a fila (entrega "pelo menos uma vez" / at-least-once).
  * Recibo de entrega: cada entrega gera um recibo novo, e ack/nack só valem com o recibo
    da entrega ATUAL. Assim, um consumidor atrasado (cujo prazo venceu e cuja mensagem já
    foi reentregue a outro) não apaga a mensagem que o outro está processando.
  * nack: o consumidor devolve a mensagem (falha temporária) ou a rejeita de vez.
  * Limite de tentativas + Dead Letter Queue: uma mensagem entregue `max_tentativas`
    vezes sem ack (ex.: derruba o worker toda vez, a "mensagem venenosa") é movida para a
    fila "dlq.<fila>" em vez de travar a fila para sempre.
  * Long polling: consumir(espera=N) aguarda até N segundos por uma mensagem, em vez de o
    consumidor ficar perguntando em loop (menos latência e menos requisições).
"""
import json
import sqlite3
import threading
import time
import uuid

PREFIXO_DLQ = "dlq."
MODOS_SYNC = ("FULL", "NORMAL")

# Colunas acrescentadas depois da primeira versão (migração de bancos antigos).
_COLUNAS_NOVAS = {
    "tentativas": "INTEGER NOT NULL DEFAULT 0",
    "recibo": "TEXT",
    "criada_em": "REAL NOT NULL DEFAULT 0",
    "motivo": "TEXT",
}


class BrokerFilas:
    def __init__(self, caminho_db="dados/broker.db", max_tentativas=3, sync="FULL"):
        if sync not in MODOS_SYNC:
            raise ValueError(f"sync deve ser um de {MODOS_SYNC}")
        self.max_tentativas = max_tentativas
        self._fechado = False
        # check_same_thread=False: o servidor HTTP usa várias threads.
        self._db = sqlite3.connect(caminho_db, check_same_thread=False)
        # Condition = lock + "campainha". O lock impede duas threads de pegarem a MESMA
        # mensagem; a campainha acorda quem está esperando em long polling.
        self._cond = threading.Condition()
        with self._cond:
            # WAL: cada commit escreve só no fim de um log (mais barato que o journal padrão).
            self._db.execute("PRAGMA journal_mode=WAL")
            # FULL: fsync em todo commit (sobrevive até a queda de energia).
            # NORMAL: mais rápido; sobrevive à queda do PROCESSO, mas pode perder os
            # últimos commits se a máquina desligar.
            self._db.execute(f"PRAGMA synchronous={sync}")
            self._db.execute(
                """CREATE TABLE IF NOT EXISTS mensagens (
                       id          INTEGER PRIMARY KEY AUTOINCREMENT,
                       fila        TEXT NOT NULL,
                       corpo       TEXT NOT NULL,
                       visivel_em  REAL NOT NULL DEFAULT 0
                   )"""
            )
            self._migrar()
            # Índice (fila, id): achar o início de uma fila não exige varrer a tabela toda.
            self._db.execute("CREATE INDEX IF NOT EXISTS idx_fila_id ON mensagens(fila, id)")
            self._db.commit()

    def _migrar(self):
        existentes = {linha[1] for linha in self._db.execute("PRAGMA table_info(mensagens)")}
        for coluna, ddl in _COLUNAS_NOVAS.items():
            if coluna not in existentes:
                self._db.execute(f"ALTER TABLE mensagens ADD COLUMN {coluna} {ddl}")

    # ------------------------------------------------------------------ produtor
    def publicar(self, fila, corpo):
        """Coloca a mensagem na fila (criada implicitamente) e devolve o id."""
        with self._cond:
            cur = self._db.execute(
                "INSERT INTO mensagens (fila, corpo, criada_em) VALUES (?, ?, ?)",
                (fila, json.dumps(corpo, ensure_ascii=False), time.time()),
            )
            self._db.commit()
            self._cond.notify_all()  # acorda consumidores em long polling
            return cur.lastrowid

    # ---------------------------------------------------------------- consumidor
    def consumir(self, fila, visibilidade=10.0, espera=0.0, ativo=None):
        """
        Entrega a próxima mensagem disponível e a esconde por `visibilidade` segundos.

        espera > 0: long polling (aguarda até `espera` s por uma mensagem).
        ativo: função que diz se quem pediu ainda está conectado. Se o consumidor morrer
               durante a espera, o broker NÃO retira mensagem para ele (senão ela ficaria
               escondida à toa e a ordem FIFO quebraria).
        Devolve {"id", "recibo", "tentativa", "corpo"} ou None.
        """
        limite = time.time() + max(0.0, espera)
        with self._cond:
            while True:
                if self._fechado or (ativo is not None and not ativo()):
                    return None
                msg = self._retirar(fila, visibilidade)
                if msg is not None:
                    return msg
                restante = limite - time.time()
                if restante <= 0:
                    return None
                # Acorda quando alguém publicar (notify) ou a cada 0,5 s, para enxergar
                # mensagens cujo prazo de visibilidade venceu.
                self._cond.wait(min(restante, 0.5))

    def _retirar(self, fila, visibilidade):
        while True:
            agora = time.time()
            linha = self._db.execute(
                "SELECT id, corpo, tentativas FROM mensagens "
                "WHERE fila=? AND visivel_em<=? ORDER BY id LIMIT 1",
                (fila, agora),
            ).fetchone()
            if linha is None:
                return None
            msg_id, corpo, tentativas = linha
            if tentativas >= self.max_tentativas and not fila.startswith(PREFIXO_DLQ):
                # Já foi entregue o máximo de vezes e nunca confirmada: mensagem venenosa.
                self._mover_para_dlq(msg_id, fila, f"excedeu {self.max_tentativas} entregas sem ack")
                continue
            recibo = uuid.uuid4().hex
            self._db.execute(
                "UPDATE mensagens SET visivel_em=?, tentativas=tentativas+1, recibo=? WHERE id=?",
                (agora + visibilidade, recibo, msg_id),
            )
            self._db.commit()
            return {"id": msg_id, "recibo": recibo, "tentativa": tentativas + 1, "corpo": json.loads(corpo)}

    def ack(self, msg_id, recibo):
        """Confirma o processamento: só agora a mensagem é apagada de verdade."""
        with self._cond:
            cur = self._db.execute("DELETE FROM mensagens WHERE id=? AND recibo=?", (msg_id, recibo))
            self._db.commit()
            return cur.rowcount == 1

    def nack(self, msg_id, recibo, reenfileirar=True, motivo=None):
        """
        Devolve a mensagem. reenfileirar=True: volta para a fila na hora (falha temporária;
        conta como tentativa). reenfileirar=False: vai direto para a DLQ (não adianta tentar).
        """
        with self._cond:
            linha = self._db.execute(
                "SELECT fila FROM mensagens WHERE id=? AND recibo=?", (msg_id, recibo)
            ).fetchone()
            if linha is None:
                return False
            if reenfileirar:
                self._db.execute("UPDATE mensagens SET visivel_em=0, recibo=NULL WHERE id=?", (msg_id,))
                self._db.commit()
                self._cond.notify_all()
            else:
                self._mover_para_dlq(msg_id, linha[0], motivo or "rejeitada pelo consumidor")
            return True

    def _mover_para_dlq(self, msg_id, fila, motivo):
        self._db.execute(
            "UPDATE mensagens SET fila=?, visivel_em=0, tentativas=0, recibo=NULL, motivo=? WHERE id=?",
            (PREFIXO_DLQ + fila, motivo, msg_id),
        )
        self._db.commit()

    # ---------------------------------------------------------------- observação
    def estatisticas(self):
        """Quantas mensagens há em cada fila (inclusive as DLQs)."""
        with self._cond:
            agora = time.time()
            linhas = self._db.execute(
                "SELECT fila, SUM(visivel_em<=?), SUM(visivel_em>?) FROM mensagens GROUP BY fila ORDER BY fila",
                (agora, agora),
            ).fetchall()
        return {f: {"prontas": int(p), "em_processamento": int(e)} for f, p, e in linhas}

    def espiar(self, fila, limite=10):
        """Mostra as mensagens de uma fila SEM consumi-las (útil para inspecionar a DLQ)."""
        with self._cond:
            linhas = self._db.execute(
                "SELECT id, tentativas, motivo, corpo FROM mensagens WHERE fila=? ORDER BY id LIMIT ?",
                (fila, limite),
            ).fetchall()
        return [{"id": i, "tentativas": t, "motivo": m, "corpo": json.loads(c)} for i, t, m, c in linhas]

    def fechar(self):
        with self._cond:
            self._fechado = True
            self._cond.notify_all()  # libera quem está em long polling
            self._db.close()