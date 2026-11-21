# Resultados do benchmark

Ambiente: Linux 7.3.3-200.fc44.x86_64, Python 3.14.10, 12 CPUs, 21/11/2026 08:49. n = 150 chamadas síncronas por medida; lote assíncrono = 300 comandos.

| Configuração | Leitura mediana (ms) | Leitura p95 (ms) | Escrita mediana (ms) | Escrita p95 (ms) | Req. HTTP por chamada | Conexões TCP por chamada | Publicação assíncrona (msg/s) | Processamento (msg/s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| T2: RPC direto (baseline) | 0.20 | 0.45 | 0.57 | 0.81 | 1.0 | 1.0 | — | 1730 |
| T4a: fila, polling curto, sem keep-alive | 211.51 | 214.91 | 213.13 | 311.52 | 9.0 | 9.0 | 979 | 161 |
| T4b: fila, long polling + keep-alive | 1.00 | 1.71 | 1.94 | 2.71 | 6.0 | 0.0 | 3323 | 319 |
| T4c: T4b + synchronous=NORMAL | 1.38 | 2.61 | 1.84 | 3.23 | 6.0 | 0.0 | 4178 | 410 |

No T2 não há modo assíncrono; a coluna de processamento mostra a vazão das escritas síncronas.
