# Trabalho 4 — Comunicação Indireta (Opção C: Filas de Mensagens)

Evolução do sistema da loja de roupas (Trabalho 2). O cliente deixa de chamar o servidor
diretamente (`ClienteProxy("127.0.0.1", 8000)`) e passa a falar **apenas com um broker de filas**.

```
ANTES (T2):  Cliente ──── IP:porta ────► Servidor RPC
AGORA (T4):  Cliente ──► [ BROKER: fila "comandos" ] ◄── Worker da loja
                   ▲      [ fila "resp.<cliente>"  ]──────────┘
                   └──────────── resposta ◄──────────────────
```

## Executar (somente biblioteca padrão, Python 3.8+)
Todos os comandos são rodados de dentro da pasta `trabalho_04/`.

```bash
python -m demo.demo_desacoplamento        # demo automática (6 cenários, ~6 s)
python -m unittest discover -s tests -t . # 28 testes
python -m bench.benchmark                 # mede o overhead (T2 x T4); salva bench/resultados.md
```

### Demonstração ao vivo (3 terminais)
```bash
python -m broker.app_broker       # terminal 1: o intermediário (porta 9000, dados em dados/)
python -m workers.worker_loja     # terminal 2: o consumidor (estado em dados/loja_estado.json)
python -m client.app_cliente      # terminal 3: cliente interativo (menu)
```
Roteiro: cadastre e venda normalmente → **derrube o worker** (Ctrl+C no terminal 2) e continue
cadastrando: o cliente não trava e os comandos ficam na fila (opção 8 mostra) → **religue o
worker**: ele processa o acumulado e a opção 7 traz as respostas; o estoque antigo continua lá.

Opções úteis do worker: `--falhar-antes-ack` (cai depois de executar e antes do ack, para mostrar a
reentrega sem duplicar), `--atraso S` (processamento lento), `--visibilidade S`.
Opções do broker: `--max-tentativas N` (entregas antes da DLQ), `--sync NORMAL` (mais rápido, menos durável).

## O que a demo prova
| Cenário | Propriedade |
|---|---|
| 1. Funcionamento normal | Desacoplamento espacial: cliente e worker só conhecem o broker |
| 2. Worker derrubado, cliente continua enviando | Desacoplamento temporal e retenção das mensagens |
| 3. Worker volta | Processa o acumulado em ordem e recupera o estado do disco |
| 4. Worker cai depois de executar e antes do ack | Reentrega sem duplicar a venda (idempotência) |
| 5. Broker cai (kill -9) com mensagens pendentes | Nada se perde; clientes reconectam sozinhos |
| 6. Mensagem venenosa | Vai para a Dead Letter Queue; o worker segue funcionando |

## Garantias implementadas
- **Broker:** fila persistente em SQLite (WAL), FIFO por fila, *ack* com prazo de visibilidade
  (entrega *at-least-once*), recibo por entrega, `nack`, limite de tentativas com **Dead Letter
  Queue** (`dlq.<fila>`), *long polling* e HTTP/1.1 com conexões persistentes.
- **Worker:** estado (estoque + vendas) salvo atomicamente em disco junto com os `id_comando` já
  processados → uma reentrega não executa o comando de novo (efeito *exactly-once*); mensagens
  malformadas vão para a DLQ; erros inesperados devolvem a mensagem para a fila.
- **Cliente:** tolera o broker cair e voltar enquanto espera uma resposta; descarta respostas duplicadas.

## Estrutura
| Pasta | Papel |
|---|---|
| `broker/` | Intermediário: fila persistente (SQLite) + API HTTP |
| `mq/` | Biblioteca cliente do broker (keep-alive, reconexão) |
| `client/` | Produtor: `cliente_loja.py` (biblioteca) e `app_cliente.py` (menu interativo) |
| `workers/` | Consumidor (lógica da loja) e armazenamento atômico do estado |
| `services/`, `models/` | Domínio herdado do T2 (+ `consultar_vendas`, exportar/importar estado) |
| `demo/`, `tests/`, `bench/` | Demonstração, testes automatizados e benchmark |

## API HTTP do broker
| Rota | Corpo | Resposta |
|---|---|---|
| `POST /publicar` | `{"fila", "corpo"}` | `{"id"}` |
| `POST /consumir` | `{"fila", "visibilidade", "espera"}` | `{"mensagem": {"id", "recibo", "tentativa", "corpo"} \| null}` |
| `POST /ack` | `{"id", "recibo"}` | `{"ok"}` |
| `POST /nack` | `{"id", "recibo", "reenfileirar", "motivo"}` | `{"ok"}` |
| `POST /espiar` | `{"fila", "limite"}` | `{"mensagens": [...]}` (sem consumir) |
| `GET /stats` | — | mensagens prontas e em processamento por fila |
| `GET /metricas` | — | requisições HTTP e conexões TCP recebidas |