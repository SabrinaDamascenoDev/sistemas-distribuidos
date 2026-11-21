# Relatório Técnico — Trabalho 4: Comunicação Indireta

**Disciplina:** Sistemas Distribuídos (QXD0043) — UFC Quixadá · **Professor:** Rafael Braga
**Equipe:** Maria Beatriz Ribeiro de Castro e ________________________ · **Abordagem:** Opção C — Filas de Mensagens

## 1. Contexto: o que mudou na arquitetura

No Trabalho 2 o cliente da loja chamava o servidor por RPC sobre HTTP, com o endereço do servidor fixo no código (`ClienteProxy("127.0.0.1", 8000)`). Era acoplamento no espaço (o cliente precisa saber onde o servidor está) e no tempo (se o servidor estivesse fora, a chamada falhava e o comando se perdia). No T4, cliente e worker passaram a conversar só com um **broker de filas persistentes**: o cliente publica comandos na fila `comandos` e o worker, que não escuta nenhuma porta, retira esses comandos do broker. As respostas voltam pela fila `resp.<cliente>` indicada no campo `reply_to` e são associadas ao pedido pelo `id_comando` (*request-reply* sobre filas). O único endereço que cada componente conhece é o do broker.

## 2. Justificativa da escolha

O que trafega na loja são **comandos**: cadastrar uma peça, registrar uma venda. Cada comando precisa ser executado **uma única vez**, por **um** executor, e não pode se perder se esse executor estiver fora do ar. Essa é exatamente a semântica de uma fila ponto a ponto persistente, e as outras abordagens se encaixam pior:

- **Comunicação em grupo (A):** a mensagem é entregue aos membros da visão atual do grupo. Um worker que esteja fora no momento do envio não a recebe depois, a menos que se implemente transferência de estado. Além disso, se todos os membros executassem o comando, a venda seria registrada várias vezes.
- **Publish-subscribe (B):** foi feito para disseminar **eventos** de 1 para N. Para comandos que devem ter um único efeito, isso é o oposto do desejado. E, para um assinante desligado receber os eventos depois, são necessárias assinaturas duráveis, que na prática equivalem a uma fila por assinante.
- **Espaço de tuplas (D):** também desacopla no espaço e no tempo, mas o `take` é destrutivo. Se o worker retirar a tupla e cair antes de terminar, o comando some, a menos que se acrescentem transações. Teríamos de reconstruir ack e reentrega por cima dele.

A fila também oferece de graça o **nivelamento de carga**: rajadas de pedidos se acumulam no broker e o worker as consome no ritmo dele (seção 4).

## 3. Corretude e tratamento de falhas

O broker (`broker/`) guarda as mensagens em SQLite. `consumir()` não apaga a mensagem: apenas a esconde por um prazo de visibilidade e entrega um **recibo**. Só o `ack` com o recibo da entrega atual apaga a mensagem. Com isso a entrega é **pelo menos uma vez**, e o worker torna o processamento **idempotente**: antes de executar, consulta se aquele `id_comando` já foi processado. O estado da loja e a lista de ids processados são gravados juntos numa única operação atômica (arquivo temporário, `fsync` e `os.replace`). Entrega *at-least-once* com processamento idempotente dá **efeito exatamente uma vez**. A tabela abaixo resume o comportamento de cada falha; os cenários citados estão em `demo/demo_desacoplamento.py` e cada mecanismo tem teste automatizado (28 testes no total).

| Falha | Comportamento observado | Mecanismo |
|---|---|---|
| Worker desligado (cen. 2–3) | O cliente continua publicando; os comandos esperam na fila e são processados em ordem quando o worker volta | Fila persistente, FIFO |
| Worker reinicia (cen. 3) | Estoque e vendas são recuperados do disco | Snapshot atômico do estado |
| Worker cai depois de executar e antes do ack (cen. 4) | O broker reentrega a mensagem; o worker novo reconhece o `id_comando`, reenvia a resposta guardada e **não** duplica a venda | Prazo de visibilidade + idempotência |
| Broker cai com mensagens pendentes (cen. 5) | Nada se perde; o remetente recebe um erro explícito; os clientes reconectam sozinhos | SQLite (WAL, `synchronous=FULL`), reconexão |
| Mensagem venenosa (cen. 6) | Vai para `dlq.comandos` e a fila continua andando | `nack` + limite de 3 entregas → Dead Letter Queue |
| Consumidor lento confirma uma mensagem já reentregue a outro | O ack é recusado | Recibo por entrega |
| Cliente cai enquanto espera a resposta | A resposta fica guardada em `resp.<nome>` | Fila de respostas persistente |

## 4. Análise: sobrecarga e complexidade do intermediário

Medimos com `python -m bench.benchmark` (Linux, Python 3.13, 2 CPUs; 150 chamadas síncronas por medida; lote assíncrono de 300 comandos). **T4a** reproduz a comunicação da primeira versão do T4: *polling* curto (worker a cada 0,2 s, cliente a cada 0,1 s) e uma conexão TCP por requisição. **T4b** é a versão final; **T4c** é a T4b com menos `fsync`.

| Configuração | Leitura (mediana) | Escrita (mediana) | Req. HTTP / chamada | Conexões TCP novas / chamada | Publicação assíncrona | Processamento |
|---|---:|---:|---:|---:|---:|---:|
| T2: RPC direto | 0,28 ms | 0,23 ms | 1 | 1 | — | 2.310/s* |
| T4a: *polling* curto | 207,9 ms | 208,2 ms | 9 | 9 | 657/s | 129/s |
| T4b: *long polling* + keep-alive | 4,76 ms | 5,95 ms | 6 | 0 | 891/s | 170/s |
| T4c: T4b + `synchronous=NORMAL` | 1,76 ms | 3,55 ms | 6 | 0 | 2.952/s | 183/s |

\* No T2 não existe modo assíncrono: o valor é a vazão das escritas síncronas.

**De onde vem a sobrecarga.**

1. **Mais idas e voltas na rede.** Uma chamada que no T2 era uma requisição virou seis no T4: publicar, consumir e confirmar no worker, publicar a resposta, consumir e confirmar no cliente. Os saltos passaram de 1 para 2.
2. **Durabilidade.** Cada uma dessas etapas é um commit no SQLite. Comparando T4b com T4c, cerca de 63% da latência de leitura (3 dos 4,8 ms) é `fsync`.
3. ***Polling*.** No T4a, a latência é dominada pelos intervalos de espera (~208 ms) e não pela rede, e cada chamada gera três consultas vazias e nove conexões TCP.
4. **Estado do worker.** O worker processa ~170 comandos/s, contra ~2.300 escritas/s do T2. A cada escrita ele regrava o estado inteiro e faz `fsync`, um custo que cresce com o tamanho do estoque.

Uma descoberta inesperada: a primeira versão com keep-alive ficou **mais lenta** (132 ms por chamada e 23 msg/s). O servidor HTTP enviava cabeçalho e corpo em dois `send()`, e o algoritmo de Nagle segurava o segundo pacote até o ACK, que o cliente atrasa ~40 ms. Ligar `TCP_NODELAY` e enviar a resposta num único `write` resolveu. Parte do custo de um middleware está nos detalhes do transporte.

**Complexidade de gerenciamento.**

- Há mais um processo para operar e monitorar: as rotas `/stats` e `/metricas` e a DLQ, que precisa de alguém olhando.
- O broker é um **ponto único de falha**. No cenário 5 nada se perde, mas o sistema para enquanto o broker está fora.
- A entrega *at-least-once* obriga os consumidores a serem idempotentes.
- O prazo de visibilidade precisa ser maior que o tempo máximo de processamento; senão a mensagem é reentregue durante a execução.
- A ordem FIFO vale por fila e enfraquece quando há reentregas ou vários workers.
- Filas de resposta de clientes que nunca voltam ficam órfãs.

Em troca, o produtor publica de 5 a 16 vezes mais rápido do que o worker processa, sem esperar por ele. A fila absorve picos que, no T2, travariam o cliente ou fariam requisições falharem.

## 5. Como mitigamos a perda de desempenho

**Implementado e medido:**

- ***Long polling*:** o broker segura o `/consumir` até chegar uma mensagem. A latência caiu de 208 para 4,8 ms (−97,7%) e as requisições por chamada caíram de 9 para 6. Antes de retirar uma mensagem para quem está esperando, o broker confere se a conexão ainda está viva, para não esconder mensagens destinadas a um consumidor morto.
- **Conexões persistentes com `TCP_NODELAY`:** nenhuma conexão TCP nova por chamada, e reconexão transparente se o broker reiniciar.
- **Índice `(fila, id)` e modo WAL no SQLite:** achar o início da fila não exige varrer a tabela quando há acúmulo, e cada commit fica mais barato.
- **`--sync NORMAL` como opção:** corta 63% da latência de leitura. Mantivemos `FULL` como padrão porque o modo `NORMAL` pode perder os últimos commits numa queda de energia (não numa queda do processo), e numa loja vendas confirmadas não podem sumir. É uma troca explícita entre durabilidade e desempenho.

**Próximos passos que avaliamos:**

- Consumir e confirmar em lote, com *group commit*, para diluir o `fsync`.
- Trocar o snapshot completo do worker por um log só de acréscimo.
- Usar o modo assíncrono (`enviar()` sem esperar) nas operações que não precisam de resposta imediata.
- Ter vários workers concorrentes com o estado particionado por `id_peca`.
- Replicar o broker (primário–backup) para eliminar o ponto único de falha.
- Num ambiente real, adotar um broker maduro (RabbitMQ, por exemplo), que já traz essas otimizações.

**Reprodução:** `python -m demo.demo_desacoplamento` (6 cenários), `python -m unittest discover -s tests -t .` (28 testes), `python -m bench.benchmark` (tabela acima; os números variam conforme a máquina).