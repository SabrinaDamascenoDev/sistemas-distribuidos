"""
QUESTÃO EXTRA - Modelo da votação: Candidato e Urna.

A Urna guarda candidatos e votos, controla o prazo e faz a apuração.
Todos os métodos são protegidos por uma trava, porque o servidor atende
vários eleitores e administradores ao mesmo tempo (uma thread por cliente).
"""

import threading
import time


class VotacaoEncerrada(PermissionError):
    """Operação recusada porque o prazo da votação terminou."""


class Candidato:

    def __init__(self, numero, nome, partido=""):
        self.numero = int(numero)
        self.nome = str(nome)
        self.partido = str(partido)

    def para_dict(self):
        return {"numero": self.numero, "nome": self.nome, "partido": self.partido}

    @staticmethod
    def de_dict(dados):
        return Candidato(dados["numero"], dados["nome"], dados.get("partido", ""))

    def __str__(self):
        partido = f" ({self.partido})" if self.partido else ""
        return f"{self.numero:>3} - {self.nome}{partido}"


class Urna:

    def __init__(self, duracao_segundos, candidatos=(), relogio=time.time):
        self._relogio = relogio
        self.prazo = relogio() + float(duracao_segundos)
        self._candidatos = {c.numero: c for c in candidatos}
        self._votos = {}                  # eleitor -> número do candidato
        self._encerrada = False
        self._resultado = None
        self._trava = threading.RLock()

    # ---------- prazo ----------
    def aberta(self):
        with self._trava:
            return not self._encerrada and self._relogio() < self.prazo

    def segundos_restantes(self):
        return max(0.0, self.prazo - self._relogio()) if self.aberta() else 0.0

    def _exigir_aberta(self):
        if not self.aberta():
            self.encerrar()
            raise VotacaoEncerrada("A votação está encerrada: o prazo terminou")

    # ---------- candidatos ----------
    def listar_candidatos(self):
        with self._trava:
            return sorted(self._candidatos.values(), key=lambda c: c.numero)

    def adicionar_candidato(self, nome, partido="", numero=None):
        with self._trava:
            self._exigir_aberta()
            nome = str(nome).strip()
            if not nome:
                raise ValueError("O nome do candidato é obrigatório")
            if numero is None:
                numero = max(self._candidatos, default=0) + 1
            numero = int(numero)
            if numero <= 0:
                raise ValueError("O número do candidato deve ser positivo")
            if numero in self._candidatos:
                raise ValueError(f"Já existe candidato com o número {numero}")
            candidato = Candidato(numero, nome, partido)
            self._candidatos[numero] = candidato
            return candidato

    def remover_candidato(self, numero):
        """Remove o candidato; quem votou nele recupera o direito de votar."""
        with self._trava:
            self._exigir_aberta()
            numero = int(numero)
            if numero not in self._candidatos:
                raise ValueError(f"Candidato {numero} não existe")
            candidato = self._candidatos.pop(numero)
            liberados = [e for e, n in self._votos.items() if n == numero]
            for eleitor in liberados:
                del self._votos[eleitor]
            return candidato, liberados

    # ---------- votos ----------
    def votar(self, eleitor, numero):
        with self._trava:
            self._exigir_aberta()
            numero = int(numero)
            if eleitor in self._votos:
                raise PermissionError(f"O eleitor {eleitor} já votou")
            if numero not in self._candidatos:
                raise ValueError(f"Candidato {numero} não existe")
            self._votos[eleitor] = numero
            return self._candidatos[numero]

    def ja_votou(self, eleitor):
        with self._trava:
            return eleitor in self._votos

    def total_votos(self):
        with self._trava:
            return len(self._votos)

    # ---------- apuração ----------
    def encerrar(self):
        """Fecha a urna (idempotente) e calcula o resultado final."""
        with self._trava:
            if self._resultado is None:
                self._encerrada = True
                self._resultado = self._apurar(parcial=False)
            return self._resultado

    def resultado(self):
        with self._trava:
            if self.aberta():
                raise PermissionError(
                    f"Votação em andamento: resultado disponível em {self.segundos_restantes():.0f}s")
            return self.encerrar()

    def parcial(self):
        with self._trava:
            return self.encerrar() if not self.aberta() else self._apurar(parcial=True)

    def _apurar(self, parcial):
        total = len(self._votos)
        contagem = {numero: 0 for numero in self._candidatos}
        for numero in self._votos.values():
            contagem[numero] += 1

        apuracao = []
        for numero, votos in contagem.items():
            candidato = self._candidatos[numero]
            apuracao.append({**candidato.para_dict(), "votos": votos,
                             "percentual": round(100.0 * votos / total, 2) if total else 0.0})
        apuracao.sort(key=lambda linha: (-linha["votos"], linha["numero"]))

        maximo = apuracao[0]["votos"] if apuracao else 0
        lideres = [linha for linha in apuracao if linha["votos"] == maximo and maximo > 0]
        if not lideres:
            situacao = "SEM_VOTOS"
        elif len(lideres) > 1:
            situacao = "EMPATE"
        else:
            situacao = "VENCEDOR"
        return {
            "parcial": parcial,
            "total_votos": total,
            "apuracao": apuracao,
            "situacao": situacao,
            "vencedor": lideres[0] if situacao == "VENCEDOR" else None,
            "empatados": lideres if situacao == "EMPATE" else [],
        }


def formatar_resultado(resultado):
    titulo = "RESULTADO PARCIAL" if resultado["parcial"] else "RESULTADO FINAL"
    linhas = [f"== {titulo} — {resultado['total_votos']} voto(s) =="]
    for linha in resultado["apuracao"]:
        linhas.append(f"  {linha['numero']:>3} {linha['nome']:<22} {linha['votos']:>4} voto(s)  "
                      f"{linha['percentual']:6.2f}%")
    if resultado["situacao"] == "VENCEDOR":
        rotulo = "Liderando" if resultado["parcial"] else "Vencedor"
        linhas.append(f"  {rotulo}: {resultado['vencedor']['nome']} "
                      f"({resultado['vencedor']['percentual']:.2f}%)")
    elif resultado["situacao"] == "EMPATE":
        linhas.append(("  Empate parcial entre: " if resultado["parcial"] else "  Empate entre: ") + ", ".join(c["nome"] for c in resultado["empatados"]))
    else:
        linhas.append("  Nenhum voto registrado.")
    return "\n".join(linhas)