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
```bash
python -m demo.demo_desacoplamento        # demo automática (3 cenários)
python -m unittest discover -s tests -t . # testes
```
Manual (3 terminais): `python -m broker.app_broker` · `python -m workers.worker_loja` · script usando `ClienteLoja`.

## Estrutura
| Pasta | Papel |
|---|---|
| `broker/` | Intermediário: fila persistente (SQLite) + API HTTP |
| `mq/` | Biblioteca cliente do broker |
| `client/` | Produtor (cliente da loja) |
| `workers/` | Consumidor (executa a lógica da loja) |
| `services/`, `models/` | Domínio herdado do T2 |
| `demo/`, `tests/` | Demonstração e testes |

## Relatório técnico
TODO (dupla): justificativa da escolha + análise de overhead.
