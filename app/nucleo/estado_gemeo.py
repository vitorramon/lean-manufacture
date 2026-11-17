"""Estado do gêmeo publicado no T2T (tarefa 3.1, RF-A3-01/11; ADR-0011, ADR-0028; docs/convencoes-fase-3.md §1).

Uma definição só, usada pelo servidor `twin-t2t` (que publica em `EstadoGemeo.*`) e, se preciso, pelo dashboard.
Recebe os resumos por peça de `nucleo.dados` (`Dados.pecas()`): o lead time de cada peça vem de `nucleo.pecas`
(ADR-0027), aqui só se agrega. Nada consulta o banco além de `Dados`; nada depende da origem do dado além do filtro
opcional `apenas_medidas` (ADR-0013).

Definições:

- **Instante de referência** `ref`: modo `agora` (padrão, operação ao vivo) = relógio deste processo, que roda na
  mesma máquina do gateway que carimbou os `ts`; modo `ultimo_evento` = `ts` do último evento do banco, para reler
  um banco gravado (demonstração/evidência; declarado no nó `Referencia`).
- **RitmoReal** (peças/h) = peças com evento de saída (`fim_trecho`) em `(ref − janela, ref]` × 3600 / janela;
  com a janela de 600 s, × 6 (ADR-0011 item 1). Conta toda peça com saída, inclusive a incompleta (saída sem
  entrada): é produção que saiu.
- **LeadTimeMedio** (s) = média do lead time LOCAL (`saida − entrada`, relógio do gateway) das últimas N peças
  concluídas até `ref`. Sem peça concluída: `None` (publicado como −1, convenções §1).
- **UltimaPeca** = peça da saída mais recente até `ref` ("" se nenhuma).
- **StatusLinha**, em ordem: `SEM_DADOS` (banco indisponível ou nenhum evento de peça); `PARADA` (nenhum leitor do
  ponto de saída com sessão aberta em `ref`, ou nenhuma saída há mais de `parada_sem_saida_s`); `RISCO_FALTA`
  (produzindo, fornecedor ONLINE e estoque < `estoque_minimo`; tarefa 3.3a); senão `PRODUZINDO`.
- **Lead time da cadeia** (RF-A3-04) = soma dos lead times LOCAIS dos elos ONLINE com valor (≥ 0). Elo OFFLINE ou
  sem valor fica fora da soma e é listado em `excluidos`; nunca entra como zero. Nunca se subtraem relógios de
  máquinas diferentes.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from statistics import fmean

from nucleo.parametros_cadeia import ParametrosT2T
from nucleo.pecas import CONCLUIDA, ResumoPeca

PRODUZINDO, PARADA, RISCO_FALTA, SEM_DADOS = "PRODUZINDO", "PARADA", "RISCO_FALTA", "SEM_DADOS"
STATUS_LINHA = (PRODUZINDO, PARADA, RISCO_FALTA, SEM_DADOS)
ONLINE, OFFLINE = "ONLINE", "OFFLINE"
MODO_AGORA, MODO_ULTIMO_EVENTO = "agora", "ultimo_evento"
MODOS_REFERENCIA = (MODO_AGORA, MODO_ULTIMO_EVENTO)
SEM_LEAD_TIME = -1.0            # valor publicado quando não há lead time (nunca 0)


@dataclass(frozen=True)
class EstadoGemeo:
    ritmo_real: float                       # peças/h
    pecas_na_janela: int
    ultima_peca: str
    lead_time_medio_s: float | None
    lead_time_amostras: int
    pecas_em_processo: int
    status_linha: str
    motivo: str
    origem: str                             # origens dos eventos considerados, separadas por vírgula
    referencia: datetime | None
    modo_referencia: str

    @property
    def lead_time_publicado(self) -> float:
        return SEM_LEAD_TIME if self.lead_time_medio_s is None else self.lead_time_medio_s


@dataclass(frozen=True)
class LeadTimeCadeia:
    soma_s: float | None                    # None = nenhum elo com valor
    incluidos: tuple[str, ...]
    excluidos: tuple[tuple[str, str], ...]  # (elo, motivo)

    @property
    def completo(self) -> bool:
        return not self.excluidos and bool(self.incluidos)


def ritmo(saidas: Iterable[datetime], ref: datetime, janela_s: float) -> tuple[int, float]:
    inicio = ref - timedelta(seconds=janela_s)
    n = sum(1 for t in saidas if inicio < t <= ref)
    return n, n * 3600.0 / janela_s


def lead_time_medio(resumos: Iterable[ResumoPeca], ref: datetime, amostras: int) -> tuple[float | None, int]:
    concl = sorted((r for r in resumos if r.situacao == CONCLUIDA and r.lead_time_s is not None
                    and r.saida is not None and r.saida <= ref), key=lambda r: r.saida)[-amostras:]
    return (fmean(r.lead_time_s for r in concl) if concl else None), len(concl)


def status_linha(tem_eventos: bool, saida_online: bool, ultima_saida: datetime | None, ref: datetime,
                 parada_sem_saida_s: float, estoque_fornecedor: float | None = None,
                 estoque_minimo: float | None = None) -> tuple[str, str]:
    """(status, motivo). `estoque_fornecedor` None = fornecedor OFFLINE ou não lido: não decide nada."""
    if not tem_eventos:
        return SEM_DADOS, "nenhum evento de peça no banco"
    if not saida_online:
        return PARADA, "leitor do ponto de saída sem sessão aberta (fonte parada ou offline)"
    if ultima_saida is None:
        return PARADA, "nenhuma peça saiu ainda"
    idade = (ref - ultima_saida).total_seconds()
    if idade > parada_sem_saida_s:
        return PARADA, f"sem saída há {idade:.0f} s (limite {parada_sem_saida_s:.0f} s)"
    if estoque_fornecedor is not None and estoque_minimo is not None and estoque_fornecedor < estoque_minimo:
        return RISCO_FALTA, (f"estoque do fornecedor {estoque_fornecedor:g} < mínimo {estoque_minimo:g} "
                             "(dado do vizinho, RF-A3-09)")
    sufixo = "" if estoque_fornecedor is not None else "; estoque do fornecedor não lido"
    return PRODUZINDO, f"última saída há {idade:.0f} s{sufixo}"


def texto_decisao(status: str, estoque_fornecedor: float | None, estoque_minimo: float) -> str:
    """Texto de `Cadeia.Decisao` (RF-A3-09). Parte da comparação `estoque < mínimo`, não do status: com a linha
    `PARADA`/`SEM_DADOS` e o estoque abaixo do mínimo, diz que o status prevalece sobre `RISCO_FALTA` (a mesma
    precedência de `status_linha` e de `nucleo.cadeia.decidir`). Fornecedor OFFLINE (None) não decide nada."""
    if estoque_fornecedor is None:
        return "sem decisão: estoque do fornecedor não lido (OFFLINE)"
    e, m = estoque_fornecedor, estoque_minimo
    if e >= m:
        return f"estoque do fornecedor {e:g} ≥ mínimo {m:g}: nenhuma ação (StatusLinha {status})"
    if status == RISCO_FALTA:
        return f"estoque do fornecedor {e:g} < mínimo {m:g} (dado do vizinho, RF-A3-09) → StatusLinha {RISCO_FALTA}"
    if status in (PARADA, SEM_DADOS):
        return f"estoque do fornecedor {e:g} < mínimo {m:g}; StatusLinha {status} prevalece sobre {RISCO_FALTA}"
    return f"estoque do fornecedor {e:g} < mínimo {m:g}; StatusLinha {status} ainda não reflete o estoque"


def calcular(resumos: Sequence[ResumoPeca], saida_online: bool, ref: datetime | None, params: ParametrosT2T,
             modo: str = MODO_AGORA, estoque_fornecedor: float | None = None,
             estoque_minimo: float | None = None) -> EstadoGemeo:
    """EstadoGemeo a partir dos resumos por peça. `ref` None só quando não há eventos (modo `ultimo_evento`)."""
    if params.apenas_medidas:
        resumos = [r for r in resumos if r.medida]
    if not resumos or ref is None:
        st, motivo = status_linha(False, saida_online, None, ref or datetime.now(UTC), params.parada_sem_saida_s)
        return EstadoGemeo(0.0, 0, "", None, 0, 0, st, motivo, "", ref, modo)
    com_saida = [r for r in resumos if r.saida is not None and r.saida <= ref]
    n, rr = ritmo((r.saida for r in com_saida), ref, params.janela_ritmo_s)
    ultima = max(com_saida, key=lambda r: r.saida, default=None)
    lt, k = lead_time_medio(resumos, ref, params.lead_time_amostras)
    st, motivo = status_linha(True, saida_online, ultima.saida if ultima else None, ref, params.parada_sem_saida_s,
                              estoque_fornecedor, estoque_minimo)
    em_processo = sum(1 for r in resumos if r.situacao == "aberta" and r.entrada is not None and r.entrada <= ref)
    origens = {o or "desconhecida" for r in resumos if r.primeiro <= ref for o in r.origens}
    return EstadoGemeo(rr, n, ultima.peca if ultima else "", lt, k, em_processo, st, motivo,
                       ",".join(sorted(origens)), ref, modo)


def ler_estado(dados, params: ParametrosT2T, modo: str = MODO_AGORA, agora: datetime | None = None,
               estoque_fornecedor: float | None = None, estoque_minimo: float | None = None) -> EstadoGemeo:
    """Estado a partir de um `nucleo.dados.Dados` aberto (somente leitura)."""
    if modo not in MODOS_REFERENCIA:
        raise ValueError(f"modo de referência desconhecido: {modo!r} (use {MODOS_REFERENCIA})")
    resumos = dados.pecas()
    if modo == MODO_ULTIMO_EVENTO:
        ref = max((r.ultimo for r in resumos), default=None)
    else:
        ref = agora or datetime.now(UTC)
    return calcular(resumos, saida_online(dados, ref) if ref else False, ref, params, modo,
                    estoque_fornecedor, estoque_minimo)


def saida_online(dados, ref: datetime) -> bool:
    """Algum dispositivo que lê o ponto de fim do trecho tinha sessão aberta em `ref` (tabela `sessoes`)."""
    leitores = [d for d in dados.dispositivos if dados.trecho.fim in dados.eventos_do_dispositivo(d)]
    return any(s.inicio <= ref and (s.fim is None or ref <= s.fim)
               for d in leitores for s in dados.sessoes(d))


def lead_time_cadeia(elos: Mapping[str, tuple[str, float | None]]) -> LeadTimeCadeia:
    """{elo: (ONLINE|OFFLINE, lead time local em s ou None)} → soma dos locais (RF-A3-04)."""
    incluidos, excluidos, soma = [], [], 0.0
    for nome, (status, valor) in elos.items():
        if status != ONLINE:
            excluidos.append((nome, "OFFLINE"))
        elif valor is None or valor < 0:
            excluidos.append((nome, "sem lead time"))
        else:
            incluidos.append(nome)
            soma += valor
    return LeadTimeCadeia(soma if incluidos else None, tuple(incluidos), tuple(excluidos))
