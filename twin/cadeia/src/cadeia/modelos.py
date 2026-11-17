"""Comportamento dos elos emulados (tarefa 3.3; docs/convencoes-fase-3.md §2 e §3). Lógica pura, relógio injetado.

EMULADO (ADR-0002, P-04): estes modelos fazem o papel dos gêmeos de outros grupos enquanto não houver parceiro. Os
números saem dos parâmetros de `config/cadeia.yaml` → `emulados` e do que a Produção publica; não são medição.

Entrada comum: a leitura da Produção (nosso twin-t2t, :4851) feita por `twin_t2t.cliente_cadeia.vigiar` —
`Leitura(status ONLINE|OFFLINE, valores {RitmoProducao, StatusLinha, UltimaPeca, Batimento})`. Cada nova
`UltimaPeca` = uma peça que a Produção concluiu (a primeira observada só fixa a referência). Peças concluídas entre
duas leituras (1 s) ou enquanto a Produção esteve OFFLINE contam como uma: limitação aceita para emulação
(240 peças/h = 1 a cada 15 s).

Lead time de cada elo: medido no relógio DO PRÓPRIO processo do elo (monotônico), nunca comparado com o nosso.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

ONLINE = "ONLINE"
SEM_LEAD_TIME = -1.0
PRODUCAO_PARADA = frozenset({"PARADA", "SEM_DADOS"})

# Fornecedor
OPERANDO, RUPTURA, PARADO = "OPERANDO", "RUPTURA", "PARADO"
# Distribuição
DESPACHANDO, AGUARDANDO_PRODUCAO, OCIOSA = "DESPACHANDO", "AGUARDANDO_PRODUCAO", "OCIOSA"


@dataclass(frozen=True)
class Producao:
    """O que o elo emulado sabe da Produção nesta volta (None = nunca leu)."""

    status: str
    valores: Mapping[str, Any]

    @property
    def online(self) -> bool:
        return self.status == ONLINE


def _num(d: Mapping[str, Any], chave: str, minimo: float = 0.0) -> float:
    v = d.get(chave)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v < minimo:
        raise ValueError(f"emulados.*.{chave} precisa ser número ≥ {minimo}: {v!r}")
    return float(v)


class _ContaPecas:
    """Detecta peça nova pela mudança de `UltimaPeca` da Produção ONLINE."""

    def __init__(self) -> None:
        self.ultima: str | None = None

    def nova(self, producao: Producao | None) -> str | None:
        if producao is None or not producao.online:
            return None
        peca = producao.valores.get("UltimaPeca")
        if not isinstance(peca, str) or not peca:
            return None
        anterior, self.ultima = self.ultima, peca
        return peca if anterior is not None and peca != anterior else None


def _ritmo(instantes: deque, agora: float, janela_s: float) -> float:
    """Unidades com instante em (agora − janela, agora] × 3600/janela (mesma definição do RitmoReal, §1.1)."""
    while instantes and instantes[0][0] <= agora - janela_s:
        instantes.popleft()
    return sum(q for _, q in instantes) * 3600.0 / janela_s


def _media(valores: deque) -> float:
    return sum(valores) / len(valores) if valores else SEM_LEAD_TIME


class ModeloFornecedor:
    """Estoque de kits que a Produção consome; reposição de lote com lead time local.

    - Cada peça nova da Produção consome `consumo_por_peca` (estoque nunca negativo; o que faltou soma `Faltas`).
    - Sem pedido em aberto e estoque < `ponto_pedido` → pedido de `reposicao_lote`, que chega após
      `lead_time_reposicao_s`. `LeadTimeMedio` = média dos pedidos já entregues (pedido → entrega); −1 sem entrega.
    - `RitmoReal` = unidades entregues na janela × 3600/janela.
    - `StatusLinha`: `RUPTURA` (estoque 0) > `PARADO` (Produção OFFLINE: não há consumo para acompanhar) > `OPERANDO`.
    """

    def __init__(self, p: Mapping[str, Any], janela_s: float = 600.0, amostras: int = 20):
        self.estoque = _num(p, "estoque_inicial")
        self.consumo = _num(p, "consumo_por_peca")
        self.lote = _num(p, "reposicao_lote", 1)
        self.lead_time = _num(p, "lead_time_reposicao_s")
        self.ponto_pedido = _num(p, "ponto_pedido")
        self.janela_s = janela_s
        self.pedido_em: float | None = None
        self.entregas: deque = deque()
        self.lead_times: deque = deque(maxlen=amostras)
        self.consumidas = 0
        self.faltas = 0.0
        self.status, self.motivo = PARADO, "Produção ainda não lida"
        self._pecas = _ContaPecas()
        self.eventos: list[str] = []         # o que aconteceu nesta volta (para o log do processo)

    def forcar_estoque(self, valor: float) -> None:
        """Modo de falha provocável (§3): estoque baixo para exercitar RISCO_FALTA na Produção."""
        self.estoque = max(0.0, float(valor))
        self.eventos.append(f"estoque forçado para {self.estoque:g}")

    def passo(self, producao: Producao | None, agora: float) -> None:
        if (peca := self._pecas.nova(producao)) is not None:
            self.consumidas += 1
            falta = max(0.0, self.consumo - self.estoque)
            self.faltas += falta
            self.estoque = max(0.0, self.estoque - self.consumo)
            if falta:
                self.eventos.append(f"peça {peca}: faltaram {falta:g} unidades")
        if self.pedido_em is not None and agora - self.pedido_em >= self.lead_time:
            lt = agora - self.pedido_em
            self.estoque += self.lote
            self.lead_times.append(lt)
            self.entregas.append((agora, self.lote))
            self.pedido_em = None
            self.eventos.append(f"entrega de {self.lote:g} após {lt:.1f} s; estoque {self.estoque:g}")
        if self.pedido_em is None and self.estoque < self.ponto_pedido:
            self.pedido_em = agora
            self.eventos.append(f"pedido de {self.lote:g} (estoque {self.estoque:g} < ponto {self.ponto_pedido:g})")
        if self.estoque <= 0:
            self.status, self.motivo = RUPTURA, "estoque zerado"
        elif producao is None or not producao.online:
            self.status, self.motivo = PARADO, "Produção OFFLINE: consumo desconhecido"
        else:
            self.status = OPERANDO
            self.motivo = f"estoque {self.estoque:g}" + (" (pedido em aberto)" if self.pedido_em is not None else "")

    def saida(self, agora: float) -> dict[str, Any]:
        return {"EstoqueFornecedor": self.estoque, "RitmoReal": _ritmo(self.entregas, agora, self.janela_s),
                "LeadTimeMedio": _media(self.lead_times), "StatusLinha": self.status, "MotivoStatus": self.motivo,
                "PedidoEmAberto": self.pedido_em is not None, "PecasConsumidas": self.consumidas}


class ModeloDistribuicao:
    """Expedição: recebe cada peça nova da Produção, despacha após `tempo_despacho_s` e reage ao ritmo dela.

    - `FilaDistribuicao` = recebidas e não despachadas. `LeadTimeMedio` = média das últimas despachadas (recebida →
      despachada, relógio deste processo); −1 sem despacho. `RitmoReal` = despachos na janela × 3600/janela.
    - **Reação (RF-A3-02):** Produção OFFLINE, `StatusLinha` ∈ {PARADA, SEM_DADOS} ou `RitmoProducao` <
      `ritmo_minimo_producao` → `AGUARDANDO_PRODUCAO` (conta em `Reacoes` a cada entrada nesse estado). Senão
      `DESPACHANDO` com fila, `OCIOSA` sem fila. A fila já recebida continua sendo despachada.
    """

    def __init__(self, p: Mapping[str, Any], janela_s: float = 600.0, amostras: int = 20):
        self.tempo_despacho = _num(p, "tempo_despacho_s")
        self.ritmo_minimo = _num(p, "ritmo_minimo_producao")
        self.janela_s = janela_s
        self.fila: deque = deque()
        self.despachos: deque = deque()
        self.lead_times: deque = deque(maxlen=amostras)
        self.recebidas = 0
        self.reacoes = 0
        self.status, self.motivo = AGUARDANDO_PRODUCAO, "Produção ainda não lida"
        self._pecas = _ContaPecas()
        self.eventos: list[str] = []

    def avaliar(self, producao: Producao | None) -> tuple[str, str]:
        if producao is None or not producao.online:
            return AGUARDANDO_PRODUCAO, "Produção OFFLINE"
        st = producao.valores.get("StatusLinha")
        if st in PRODUCAO_PARADA:
            return AGUARDANDO_PRODUCAO, f"Produção StatusLinha={st}"
        ritmo = producao.valores.get("RitmoProducao")
        if not isinstance(ritmo, (int, float)) or ritmo < self.ritmo_minimo:
            return AGUARDANDO_PRODUCAO, (f"RitmoProducao {ritmo if ritmo is not None else '—'} < "
                                         f"{self.ritmo_minimo:g} peças/h")
        if self.fila:
            return DESPACHANDO, f"{len(self.fila)} na fila; RitmoProducao {ritmo:g} peças/h"
        return OCIOSA, f"fila vazia; RitmoProducao {ritmo:g} peças/h"

    def passo(self, producao: Producao | None, agora: float) -> None:
        if (peca := self._pecas.nova(producao)) is not None:
            self.fila.append((peca, agora))
            self.recebidas += 1
        while self.fila and agora - self.fila[0][1] >= self.tempo_despacho:
            peca, recebida = self.fila.popleft()
            self.lead_times.append(agora - recebida)
            self.despachos.append((agora, 1))
            self.eventos.append(f"despachada {peca} após {agora - recebida:.1f} s")
        status, self.motivo = self.avaliar(producao)
        if status == AGUARDANDO_PRODUCAO and self.status != AGUARDANDO_PRODUCAO:
            self.reacoes += 1
            self.eventos.append(f"REAÇÃO: {self.motivo} -> {AGUARDANDO_PRODUCAO}")
        self.status = status

    def saida(self, agora: float) -> dict[str, Any]:
        return {"FilaDistribuicao": float(len(self.fila)), "RitmoReal": _ritmo(self.despachos, agora, self.janela_s),
                "LeadTimeMedio": _media(self.lead_times), "StatusLinha": self.status, "MotivoStatus": self.motivo,
                "PecasRecebidas": self.recebidas, "Reacoes": self.reacoes}
