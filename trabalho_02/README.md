# Trabalho 2 - Sistemas Distribuídos: Implementação de RPC/RMI

**Universidade Federal do Ceará (UFC) - Campus Quixadá**  
**Disciplina:** Sistemas Distribuídos (QXD0043)  
**Professor:** Rafael Braga  

---

## 📌 Sobre o Projeto

Este projeto consiste na reimplementação da camada de comunicação do **Trabalho 1** (que utilizava Sockets TCP/UDP e Multicast), agora utilizando o modelo de **Chamada de Procedimento Remoto (RPC) / Invocação Remota de Métodos (RMI)**. 

A comunicação cliente-servidor foi estruturada seguindo o protocolo **requisição-resposta** (Capítulo 5 do livro-texto). Conforme as restrições da atividade, a criação manual de *sockets* de baixo nível foi evitada; em vez disso, o protocolo foi encapsulado sobre HTTP (usando as bibliotecas nativas `http.server` e `urllib.request` do Python).

## 🏗️ Estrutura de Pastas e Arquivos

O repositório está organizado utilizando os padrões do middleware RMI e do padrão de projeto *Proxy*/*Skeleton*:

```text
trabalho_02/
├── models/                  # Classes de Entidade (Domínio)
│   ├── peca_de_roupa.py
│   ├── camiseta.py
│   ├── calca.py
│   ├── venda.py
│   └── estoque.py
├── rpc/                     # Camada de Middleware RPC
│   ├── mensagem.py          # Empacotamento/Desempacotamento de Mensagens
│   ├── cliente_stub.py      # Implementação do Proxy (doOperation)
│   └── servidor_skeleton.py # Implementação do Skeleton (getRequest / sendReply)
├── services/                # Lógica de Negócio (Servente)
│   └── loja_service.py      # Métodos que serão invocados remotamente
├── server/
│   └── app_servidor.py      # Ponto de entrada do Servidor
├── client/
│   └── app_cliente.py       # Ponto de entrada do Cliente
└── README.md
```

## 🧩 Modelagem do Domínio (Requisitos de POO)

O projeto atende estritamente às exigências estruturais orientadas a objetos estipuladas no trabalho:

1. **Mínimo de 4 Entidades:**
   * `PecaRoupa`, `Camiseta`, `Calca`, `Venda` (e a auxiliar `Estoque`).
2. **Duas composições do tipo Extensão ("é-um" / Herança):**
   * `Camiseta` herda de `PecaRoupa`.
   * `Calca` herda de `PecaRoupa`.
3. **Duas composições do tipo Agregação ("tem-um"):**
   * A classe `Venda` possui uma instância de `PecaRoupa`.
   * A classe `Estoque` possui uma lista de instâncias de `PecaRoupa`.

## ⚙️ Protocolo de Requisição-Resposta e Middleware

A passagem de parâmetros foi implementada misturando conceitos de **passagem por referência** (para a execução de objetos remotos no servidor) e **passagem por valor** (usando representação externa de dados em formato **JSON**).

### Formato da Mensagem (JSON)
As mensagens transitam na rede com o seguinte esquema (baseado nos slides do Cap. 5):

**Requisição (Request):**
```json
{
  "messageType": 0,
  "requestID": 1,
  "objectReference": "ServicoLoja",
  "methodID": "adicionar_camiseta",
  "arguments": {"id_peca": 1, "nome": "Camiseta Polo", "preco": 89.90, "tamanho": "M"}
}
```

**Resposta (Reply):**
```json
{
  "messageType": 1,
  "requestID": 1,
  "result": {"status": "sucesso", "mensagem": "Camiseta Polo adicionada ao estoque."}
}
```

### Operações do Protocolo
* **`doOperation` (Cliente Stub):** Empacota os parâmetros em JSON, envia para o servidor via POST HTTP e bloqueia (*chamada síncrona*) até receber a resposta, retornando o resultado desempacotado.
* **`getRequest` (Servidor Skeleton):** Emulado pelo método `do_POST` do `BaseHTTPRequestHandler`, responsável por ler o fluxo de bytes de entrada e convertê-lo em um dicionário Python. A partir do `methodID`, repassa a execução para o Servente (Dispatcher).
* **`sendReply` (Servidor Skeleton):** Empacota o valor retornado pela execução local em JSON e envia o *response* de volta para o *Host* e *Port* do cliente que originou a requisição.

## 🚀 Como Executar o Projeto

**Pré-requisitos:** Python 3.6 ou superior instalado. Nenhuma biblioteca externa (`pip install`) é necessária, o projeto utiliza apenas pacotes nativos (*built-in*).

1. Abra um terminal na pasta raiz do projeto (`trabalho_02/`).
2. **Inicie o Servidor:**
   ```bash
   python server/app_servidor.py
   ```
   *O terminal informará que o Servidor RMI/RPC está rodando em `http://127.0.0.1:8000`*.

3. **Execute o Cliente:**
   Abra uma *nova janela* ou aba do terminal (mantendo o servidor ativo) e rode:
   ```bash
   python client/app_cliente.py
   ```
   *O cliente invocará automaticamente os 4 métodos remotos exigidos (`adicionar_camiseta`, `adicionar_calca`, `consultar_estoque` e `registrar_venda`) e imprimirá os resultados retornados pelo servidor.*