# Sistema de Gestão de Loja de Roupas — Trabalho 1 de Sistemas Distribuídos

## 1. Sobre o projeto

O serviço remoto escolhido é um sistema simples de gestão de uma loja de roupas (peças, estoque e vendas). Ele serve de contexto para demonstrar mecanismos de **comunicação entre processos** em Python:

| Item | O que demonstra | Pasta |
|---|---|---|
| 1 e 2 | **Streams:** escrever e ler uma sequência binária de peças usando saída/entrada padrão, arquivo e TCP | `streams/`, `demos_stream/` |
| 3 | **Serialização:** cliente envia pedidos de operação a um servidor TCP; as mensagens são codificadas em JSON | `serialization/` |
| 4 | **Multicast:** clientes se autenticam por TCP e recebem notificações, alertas e atualizações de estoque por UDP multicast (grupo `230.0.0.1`) | `multicast/` |
| Extra | **Votação distribuída:** login, candidatos e votos por TCP; notas informativas por multicast | `votacao/` |

Cada item tem sua própria pasta porque usa um protocolo próprio. Há também testes automatizados em `tests/`.

## 2. Tecnologias utilizadas

- **Python 3** (testado com 3.12), usando **somente a biblioteca padrão**. Não há dependências para instalar.
- `socket` — comunicação TCP e UDP multicast.
- `threading` e `concurrent.futures` — servidores multithread, threads de escuta nos clientes e travas (`Lock`) para proteger estoque e urna.
- `json` — formato das mensagens dos itens 3, 4 e da votação.
- `struct` e `io` — formato binário e fluxos (streams) dos itens 1 e 2.
- `unittest` — testes automatizados.

## 3. Preparação

Execute os comandos **a partir da raiz do projeto** (`trabalho_01/`) e use `python -m pacote.modulo`, sem escrever `.py` no fim.

```bash
cd caminho/para/trabalho_01
python --version
```

## 4. Estrutura do projeto

```text
trabalho_01/
├── README.md
├── models/
│   ├── peca_de_roupa.py       # PecaDeRoupa, subclasses e conversões
│   ├── loja.py                # estado da loja: coleção de peças
│   ├── venda.py               # objeto que representa uma venda
│   └── exemplo.py             # dados de exemplo
├── services/
│   ├── erros.py               # LojaError: erros de negócio
│   ├── estoque_service.py     # operações de estoque
│   ├── vendas.py              # interface/abstração de vendas
│   └── vendas_service.py      # operações de venda
├── streams/
│   ├── loja_output_stream.py  # escrita do formato binário (item 1)
│   └── loja_input_stream.py   # leitura do formato binário (item 2)
├── demos_stream/
│   ├── q1b.py / q1c.py / q1d.py   # item 1: saída padrão, arquivo, TCP
│   └── q2b.py / q2c.py / q2d.py   # item 2: entrada padrão, arquivo, TCP
├── serialization/
│   ├── protocolo.py           # JSON, enquadramento e envio/recebimento
│   ├── servidor_base.py       # servidor request/reply multithread (itens 3, 4 e extra)
│   ├── cliente_base.py        # cliente request/reply (itens 3, 4 e extra)
│   ├── client.py              # cliente do item 3
│   └── server.py              # servidor do item 3
├── multicast/                 # item 4
│   ├── grupo.py               # joinGroup / leaveGroup / sockets multicast
│   ├── mensagens.py           # formato JSON: tipo, mensagem, timestamp, seq
│   ├── servidor.py            # autenticação TCP + envio multicast concorrente
│   ├── cliente.py             # thread de escuta + thread de interação
│   └── demo.py                # demonstração automática com 3 clientes
├── votacao/                   # questão extra
│   ├── modelo.py              # Candidato, Urna (prazo, votos, apuração)
│   ├── servidor.py            # servidor TCP multithread + notas por multicast
│   ├── cliente.py             # cliente eleitor/administrador
│   └── demo.py                # demonstração automática
├── dados/                     # pecas.bin, gerado pelas demos de stream
└── tests/                     # testes automatizados (unittest)
```

## 5. Modelos e serviços

### `models/` — objetos de dados

- `PecaDeRoupa` representa os dados comuns de uma peça (código, nome, marca, tamanho, cor, preço, quantidade).
- `Camiseta`, `Calca`, `Vestido`, `Jaqueta` e `Acessorio` especializam a peça e acrescentam um detalhe específico.
- `Loja` mantém a coleção de peças.
- `Venda` representa o registro de uma venda.
- `exemplo.py` cria os dados iniciais usados nas demonstrações.

### `services/` — operações e regras de negócio

- `EstoqueService` concentra as operações sobre peças e estoque.
- `VendasService` realiza vendas e calcula totais.
- `vendas.py` define a abstração (interface) de vendas.
- `erros.py` contém `LojaError`, usado para representar situações inválidas (ex.: estoque insuficiente).

Os modelos guardam os dados; os serviços guardam as regras (como verificar estoque antes de vender). Os servidores de rede apenas recebem as requisições e chamam esses serviços.

## 6. Itens 1 e 2 — Streams

### 6.1 `streams/loja_output_stream.py`

`LojaOutputStream` codifica um conjunto de peças em formato binário e escreve os bytes no destino recebido. O construtor recebe:

1. o stream de destino;
2. a sequência de peças;
3. a quantidade de peças a enviar.

O método `enviar()` escreve primeiro a quantidade de peças e depois os campos de cada uma. Textos são gravados em UTF-8 precedidos do tamanho em bytes; números (código, preço, quantidade) são gravados em binário. A classe usa a interface de fluxo binário do Python (`io.RawIOBase`), equivalente ao `OutputStream` do enunciado.

### 6.2 `streams/loja_input_stream.py`

`LojaInputStream` recebe apenas a origem no construtor. O método `ler_pecas()` lê a quantidade, depois os campos de cada peça **na mesma ordem em que foram escritos**, e reconstrói a subclasse correta de `PecaDeRoupa`. Se a origem terminar antes do esperado, é lançado um erro de fim inesperado de fluxo.

### 6.3 Programas de demonstração (`demos_stream/`)

Os seis arquivos **não são seis implementações do stream**: são programas que ligam o mesmo stream a origens e destinos diferentes, como pede o enunciado.

| Arquivo | Requisito | Função |
|---|---|---|
| `q1b.py` | 1-b | escreve as peças na saída padrão (no terminal mostra os bytes em hexadecimal) |
| `q1c.py` | 1-c | escreve as peças em `dados/pecas.bin` |
| `q1d.py` | 1-d | conecta-se ao servidor TCP e envia as peças |
| `q2b.py` | 2-b | lê peças da entrada padrão |
| `q2c.py` | 2-c | lê as peças de `dados/pecas.bin` |
| `q2d.py` | 2-d | atua como servidor TCP e lê as peças enviadas pelo cliente |

### 6.4 Como testar

```bash
# 1-b: saída padrão
python -m demos_stream.q1b

# 1-b + 2-b: saída padrão ligada à entrada padrão por um pipe
python -m demos_stream.q1b | python -m demos_stream.q2b

# 1-c: grava dados/pecas.bin
python -m demos_stream.q1c

# 2-c: lê o arquivo (rode q1c antes)
python -m demos_stream.q2c

# 2-b com arquivo redirecionado para a entrada padrão
python -m demos_stream.q2b < dados/pecas.bin
```

**1-d + 2-d (TCP, porta `5051`), em dois terminais:**

```bash
python -m demos_stream.q2d    # terminal 1: servidor que recebe
python -m demos_stream.q1d    # terminal 2: cliente que envia
```

O servidor deve mostrar as cinco peças recebidas. Esse servidor espera o formato binário dos streams; ele **não** entende as mensagens JSON do item 3.

## 7. Item 3 — Cliente-servidor com serialização

O cliente envia uma **requisição de operação**, o servidor executa a operação da loja e devolve uma **resposta**. A pasta `serialization/` tem:

- `protocolo.py`: transforma mensagens em bytes (JSON UTF-8) e as envia/recebe por TCP, com um cabeçalho de 4 bytes indicando o tamanho de cada mensagem;
- `server.py`: recebe requisições, chama `EstoqueService`/`VendasService` e devolve respostas;
- `client.py`: monta requisições, recebe respostas e reconstrói objetos `PecaDeRoupa` e `Venda`;
- `servidor_base.py` e `cliente_base.py`: ciclo "aceitar conexão → uma thread por cliente → receber request → executar → enviar reply" (`ServidorTCP`) e o lado cliente (`ClienteTCP`). Os servidores do multicast e da votação herdam dessas classes.

`services/` não é um segundo servidor de rede: é a lógica de negócio chamada pelo `serialization/server.py`.

### 7.1 Formato das mensagens

Requisição:

```json
{
  "operacao": "VENDER_PECA",
  "argumentos": { "codigo": 6, "quantidade": 2 }
}
```

Resposta de sucesso:

```json
{
  "status": "OK",
  "resultado": { "codigo": 1, "codigo_peca": 6, "quantidade": 2 }
}
```

Resposta de erro:

```json
{
  "status": "ERRO",
  "mensagem": "Estoque insuficiente"
}
```

Os campos de `resultado` dependem da operação executada.

### 7.2 Caminho de uma chamada (item 3-a)

1. O cliente monta o dicionário com `operacao` e `argumentos` e o **empacota** em JSON/bytes.
2. O cliente envia a mensagem por TCP.
3. O servidor recebe e **desempacota** a requisição.
4. O servidor chama o serviço correspondente da loja.
5. O servidor **empacota** a resposta e a envia.
6. O cliente **desempacota** a resposta e, se necessário, reconstrói o objeto (`PecaDeRoupa` ou `Venda`).

### 7.3 Operações disponíveis

| Operação | O que faz |
|---|---|
| `LISTAR_PECAS` | retorna as peças cadastradas |
| `ADICIONAR_PECA` | envia uma peça serializada e a adiciona ao estoque |
| `VENDER_PECA` | tenta vender a quantidade solicitada |
| `TOTAL_VENDAS` | retorna a quantidade de vendas e o total vendido |

### 7.4 Como testar

```bash
# Terminal 1 — servidor (porta 5050)
python -m serialization.server

# Terminal 2 — demonstração automática
python -m serialization.client --demo

# Ou o menu interativo
python -m serialization.client
```

O modo `--demo` lista peças, adiciona uma camiseta, vende unidades, mostra uma venda inválida por falta de estoque e consulta o total de vendas.

O servidor atende cada cliente em uma thread separada e usa um `threading.Lock` nas operações que alteram o estoque, evitando que duas requisições simultâneas corrompam o estado. O servidor de serialização usa a porta `5050` e o das demos de stream usa a `5051`, pois falam protocolos diferentes.

## 8. Item 4 — Multicast

### 8.1 Arquitetura

```text
                 (1) AUTENTICAR usuario/senha  ── TCP unicast, porta 5060 ──►
  Cliente  ◄── (2) token + grupo 230.0.0.1 + porta 5007 ──────────────────────  Servidor
     │
     │ (3) joinGroup(230.0.0.1)
     ▼
  ◄════ (4) NOTIFICACAO / ALERTA / ATUALIZACAO ══ UDP multicast 230.0.0.1:5007 ═══ Servidor
```

- **TCP (unicast)** é usado só na autenticação: o servidor confere usuário e senha e só então informa o grupo e a porta multicast. Usa o mesmo protocolo request/reply do item 3.
- **UDP multicast** entrega cada datagrama a todos os clientes que entraram no grupo. `230.0.0.1` é um endereço classe D e a porta `5007` é fixa. O TTL padrão é 1 (as mensagens não saem da rede local).
- **joinGroup / leaveGroup** são implementados com as opções de socket `IP_ADD_MEMBERSHIP` e `IP_DROP_MEMBERSHIP` em `multicast/grupo.py`. Depois de sair do grupo, o cliente deixa de receber as mensagens.

### 8.2 Formato das mensagens

Um datagrama JSON por mensagem:

```json
{
  "tipo": "ALERTA",
  "mensagem": "Estoque baixo de 'Jaqueta de Couro': 2 unidade(s)",
  "timestamp": 1791744000,
  "seq": 7
}
```

`tipo` pode ser `NOTIFICACAO`, `ALERTA` ou `ATUALIZACAO`. O campo `seq` foi acrescentado ao formato sugerido para mostrar a ordem de envio; como o UDP não garante entrega nem ordem, ele pode chegar fora de sequência.

### 8.3 Threads

| Lado | Thread | Função |
|---|---|---|
| Servidor | `accept` + uma por conexão | autenticação TCP |
| Servidor | `simulacao-loja` | simula vendas e reposições com os serviços da loja e publica `ATUALIZACAO` e `ALERTA` (estoque baixo/esgotado) |
| Servidor | pool `envio_0..3` | envios assíncronos e rajadas concorrentes (`rajada N`) |
| Servidor | principal | console do administrador: publica mensagens digitadas |
| Cliente | `escuta-multicast` | fica em `recvfrom()` e exibe cada mensagem assim que chega |
| Cliente | `interacao-usuario` | lê comandos: `sair` (leaveGroup), `entrar` (joinGroup), `historico`, `status`, `fim` |

Como várias threads do servidor publicam ao mesmo tempo, o contador de sequência é protegido por uma trava.

### 8.4 Como testar

**Demonstração automática** (servidor + 3 clientes, leave/join e rajada concorrente):

```bash
python -m multicast.demo
```

**Manual, em vários terminais:**

```bash
# Terminal 1 — servidor (console do administrador + simulação da loja a cada 5 s)
python -m multicast.servidor

# Terminais 2, 3, 4... — um cliente por terminal
python -m multicast.cliente --usuario ana --senha 123
python -m multicast.cliente --usuario bruno --senha 123
python -m multicast.cliente --usuario carla --senha 123 --auto 60   # só escuta por 60 s
```

Usuários: `ana`, `bruno`, `carla`, `davi` (senha `123`) e `admin` (senha `admin`).

Comandos do console do servidor: `n <texto>` (NOTIFICACAO), `a <texto>` (ALERTA), `u <texto>` (ATUALIZACAO), `rajada 10` (10 mensagens concorrentes), `clientes` e `sair`. Para desligar a simulação automática, use `--intervalo 0`.

**Em máquinas diferentes da mesma rede:** use `--host IP_DO_SERVIDOR` no cliente. Se a máquina tiver várias interfaces, informe `--interface IP_LOCAL` no cliente e no servidor.

## 9. Questão extra — Sistema de votação

### 9.1 Funcionamento

- O servidor abre a votação com um **prazo** (`--duracao`, em segundos). Um `threading.Timer` encerra a urna no fim do prazo; depois disso, votos e alterações de candidatos são recusados e o servidor calcula **total de votos, percentuais e vencedor** (ou empate).
- O **eleitor** faz login e recebe a lista de candidatos, o tempo restante e o grupo multicast. Cada eleitor vota uma única vez e só vê o resultado depois do prazo.
- O **administrador** adiciona e remove candidatos, envia **notas informativas** e pode consultar a apuração parcial. Se um candidato é removido, os votos dele são anulados e esses eleitores podem votar de novo.
- **Comunicação:** login, candidatos e votos vão por **TCP** (porta `6000`), com servidor multithread e uma trava na urna. O **UDP multicast** (`230.0.0.2:6001`) é usado **exclusivamente** para as notas dos administradores.
- **Formato dos dados:** JSON com cabeçalho de tamanho (o mesmo `protocolo.py` do item 3). O enunciado sugere protocol buffers, mas aceita JSON.
- Cada cliente tem uma thread `escuta-notas` (multicast) e uma thread `interacao-usuario` (menu).

### 9.2 Operações

| Operação | Quem | Argumentos |
|---|---|---|
| `LOGIN` | todos | `usuario`, `senha` |
| `LISTAR_CANDIDATOS`, `STATUS`, `LOGOUT` | todos | `token` |
| `VOTAR` | eleitor | `token`, `numero` |
| `RESULTADO` | eleitor (após o prazo) / admin (parcial a qualquer momento) | `token` |
| `ADICIONAR_CANDIDATO` | admin | `token`, `nome`, `partido`, `numero` (opcional) |
| `REMOVER_CANDIDATO` | admin | `token`, `numero` |
| `ENVIAR_NOTA` | admin | `token`, `texto` (enviada por multicast) |

### 9.3 Como testar

**Demonstração automática** (prazo de 4 s, 5 eleitores votando em paralelo, erros esperados e resultado final):

```bash
python -m votacao.demo
```

**Manual:**

```bash
# Terminal 1 — servidor com 2 minutos de votação
python -m votacao.servidor --duracao 120

# Terminal 2 — administrador
python -m votacao.cliente --usuario admin --senha admin

# Terminais 3, 4... — eleitores (eleitor1 até eleitor10, senha 123)
python -m votacao.cliente --usuario eleitor1 --senha 123
```

Use `--verboso` no cliente para ver as mensagens empacotadas e desempacotadas.

## 10. Testes automatizados

```bash
python -m unittest discover -s tests -t . -v
```

| Arquivo | O que verifica |
|---|---|
| `tests/test_strems.py` | ida e volta do formato binário, envio parcial (`quantidade`), quantidade inválida, fluxo truncado, TCP e pipe `q1b \| q2b` |
| `tests/test_serialization.py` | empacotamento JSON, mensagem TCP fragmentada, fluxo cliente-servidor, erros de negócio, vendas concorrentes sem vender além do estoque |
| `tests/test_multicast.py` | formato das mensagens, endereço classe D, autenticação recusada, 3 clientes recebendo ao mesmo tempo, leaveGroup/joinGroup, rajada concorrente |
| `tests/test_votacao.py` | apuração (percentuais, vencedor, empate, sem votos), voto duplicado, prazo, remoção de candidato, fluxo completo via rede com nota multicast |

## 11. Problemas comuns

| Sintoma | Possível causa e solução |
|---|---|
| `ModuleNotFoundError` | Confira se está na raiz `trabalho_01/` e use os nomes reais dos pacotes. |
| `python -m demos_stream.q1b.py` falha | Com `-m`, não se usa `.py`: execute `python -m demos_stream.q1b`. |
| `ConnectionRefusedError` | O servidor correspondente não está rodando ou o endereço/porta não confere. |
| `Address already in use` | Já existe um processo usando a porta; encerre-o ou escolha outra. |
| `Falha ao receber: O fluxo terminou antes de chegarem todos os bytes esperados` | O receptor lê um protocolo diferente do enviado, ou a conexão fechou antes do fim. Use `q1d` com `q2d` (binário) e `serialization.client` com `serialization.server` (JSON). |
| `q2b` parece parado | Está aguardando bytes na entrada padrão; use o pipe ou o redirecionamento de arquivo. |
| `dados/pecas.bin` não existe | Execute primeiro `python -m demos_stream.q1c`. |
| A demo de serialização acusa código duplicado | O servidor mantém o estado em memória; reinicie-o para voltar aos dados iniciais. |
| Cliente multicast autentica mas não recebe nada | Firewall bloqueando UDP, rede sem multicast (comum em Wi-Fi) ou interface errada: tente `--interface IP_LOCAL` no cliente e no servidor. Na mesma máquina funciona pela interface local. |
| Votação recusa votos logo no início | O prazo (`--duracao`) já terminou; reinicie o servidor com um prazo maior. |

## 12. Roteiro de demonstração

1. Mostre `models/peca_de_roupa.py` e `models/venda.py` (objetos) e `services/` (regras de negócio).
2. Mostre `streams/loja_output_stream.py` e `streams/loja_input_stream.py`.
3. Execute `q1b | q2b`, depois `q1c` e `q2c`, depois `q2d` e `q1d` em dois terminais.
4. Execute `serialization.server` e `serialization.client --demo`.
5. Execute `multicast.servidor` e três `multicast.cliente`; envie mensagens pelo console, faça `sair`/`entrar` em um cliente e uma `rajada 10`.
6. Execute `votacao.servidor --duracao 90`, um admin e dois eleitores: adicione um candidato, envie uma nota, vote, tente votar duas vezes e mostre o resultado após o prazo.
7. Rode os testes automatizados.

## 13. Relação com o enunciado

| Requisito | Onde está |
|---|---|
| 2 classes de dados e 2 de serviço | `models/` (`PecaDeRoupa` e subclasses, `Loja`, `Venda`) e `services/` (`EstoqueService`, `VendasService`) |
| 1-a: destino, conjunto e quantidade no construtor | `streams/loja_output_stream.py` |
| 1-b / 1-c / 1-d: saída padrão, arquivo, TCP | `demos_stream/q1b.py`, `q1c.py`, `q1d.py` |
| 2-a: origem no construtor | `streams/loja_input_stream.py` |
| 2-b / 2-c / 2-d: entrada padrão, arquivo, TCP | `demos_stream/q2b.py`, `q2c.py`, `q2d.py` |
| 3 e 3-a: serialização, request/reply empacotados e desempacotados | `serialization/protocolo.py`, `client.py`, `server.py` |
| 4-a: grupo classe D, porta fixa, joinGroup/leaveGroup | `multicast/grupo.py` e comandos `entrar`/`sair` do cliente |
| 4-b: NOTIFICACAO, ALERTA e ATUALIZACAO em JSON | `multicast/mensagens.py`, `multicast/servidor.py` |
| 4-c: vários clientes recebendo ao mesmo tempo | `multicast/demo.py` e vários `multicast.cliente` |
| 4-d: thread de escuta + thread de interação; servidor multithread | `multicast/cliente.py`, `multicast/servidor.py` (seção 8.3) |
| 4-e: TCP na autenticação, UDP multicast nas mensagens | `multicast/servidor.py` (`AUTENTICAR` e `publicar()`) |
| Extra: votação com prazo, apuração, admin e notas por multicast | `votacao/` (seção 9) |
| Testes | `tests/` (seção 10) |