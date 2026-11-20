"""
BROKER DE FILAS DE MENSAGENS (o "intermediário" da comunicação indireta).

Produtores e consumidores NUNCA se falam: só conhecem o broker.
O broker guarda as mensagens em disco (SQLite) até alguém consumir.

Implementado aqui (versão básica):
  * Persistência em disco.
  * Ordem FIFO por fila.
  * ack + visibility timeout: consumir() NÃO apaga a mensagem, só a esconde por
    alguns segundos. Só o ack() apaga. Se o consumidor cair antes do ack, o prazo
    vence e a mensagem volta para a fila (entrega "pelo menos uma vez").

TODO (dupla): nack, Dead Letter Queue, limite de tentativas, recibo de entrega.
"""
import json
import sqlite3
import threading
import time


class BrokerFilas:
    def __init__(self, caminho_db="dados/broker.db"):
        # check_same_thread=False: o servidor HTTP usa várias threads.
        self._db = sqlite3.connect(caminho_db, check_same_thread=False)
        # Lock: impede duas threads de pegarem a MESMA mensagem ao mesmo tempo.
        self._lock = threading.Lock()
        with self._lock:
            self._db.execute(
                """CREATE TABLE IF NOT EXISTS mensagens (
                       id          INTEGER PRIMARY KEY AUTOINCREMENT,
                       fila        TEXT NOT NULL,
                       corpo       TEXT NOT NULL,
                       visivel_em  REAL NOT NULL DEFAULT 0
                   )"""
            )
            self._db.commit()

    def publicar(self, fila, corpo):
        """Coloca a mensagem na fila (criada implicitamente) e devolve o id."""
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO mensagens (fila, corpo) VALUES (?, ?)",
                (fila, json.dumps(corpo, ensure_ascii=False)),
            )
            self._db.commit()
            return cur.lastrowid

    def consumir(self, fila, visibilidade=10.0):
        """Entrega a próxima mensagem disponível (ou None) e a esconde por `visibilidade` s."""
        with self._lock:
            agora = time.time()
            linha = self._db.execute(
                "SELECT id, corpo FROM mensagens WHERE fila=? AND visivel_em<=? ORDER BY id LIMIT 1",
                (fila, agora),
            ).fetchone()
            if linha is None:
                return None
            self._db.execute("UPDATE mensagens SET visivel_em=? WHERE id=?", (agora + visibilidade, linha[0]))
            self._db.commit()
            return {"id": linha[0], "corpo": json.loads(linha[1])}

    def ack(self, msg_id):
        """Confirma o processamento: só agora a mensagem é apagada de verdade."""
        with self._lock:
            cur = self._db.execute("DELETE FROM mensagens WHERE id=?", (msg_id,))
            self._db.commit()
            return cur.rowcount == 1

    def estatisticas(self):
        """Quantas mensagens há em cada fila."""
        with self._lock:
            agora = time.time()
            linhas = self._db.execute(
                "SELECT fila, SUM(visivel_em<=?), SUM(visivel_em>?) FROM mensagens GROUP BY fila",
                (agora, agora),
            ).fetchall()
        return {f: {"prontas": int(p), "em_processamento": int(e)} for f, p, e in linhas}
