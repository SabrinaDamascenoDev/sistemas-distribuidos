"""
Armazenamento do estado do worker em disco (arquivo JSON legível).

A gravação é ATÔMICA: escreve num arquivo temporário, força para o disco (fsync) e troca
pelo definitivo com os.replace. Se o worker cair no meio, sobra o arquivo antigo inteiro,
nunca um arquivo pela metade. Isso permite salvar, numa única operação, o estado da loja
E a lista de comandos já processados (base da idempotência).
"""
import json
import os


class ArmazenamentoEstado:
    def __init__(self, caminho):
        self.caminho = caminho
        os.makedirs(os.path.dirname(caminho) or ".", exist_ok=True)

    def carregar(self):
        try:
            with open(self.caminho, encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return None

    def salvar(self, dados):
        temporario = self.caminho + ".tmp"
        with open(temporario, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=1)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporario, self.caminho)