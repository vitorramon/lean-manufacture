"""Estado da cadeia de gêmeos lido do `twin-t2t` por OPC UA, só leitura (tarefa 3.4; RF-A3-04, RF-A3-05, RF-A3-09).

Contrato: docs/convencoes-fase-3.md §1.3, §4, §5 e §6 (ADR-0011, ADR-0028). O dashboard não fala com os vizinhos:
lê o NOSSO servidor T2T (`T2T_URL`, padrão `opc.tcp://localhost:4851`), onde o cliente da cadeia (tarefa 3.2)
espelha cada vizinho em `Cadeia.<Elo>.*` e o twin publica `EstadoGemeo.*` (o nosso elo, Produção). Nada daqui
escreve no OPC UA, no SQLite ou no AAS. A página "Cadeia" só formata o que este módulo entrega (ADR-0010).

Definições (as mesmas do twin, sem cópia):

- **Elo ONLINE/OFFLINE:** o de `Cadeia.<Elo>.Status`. Os valores espelhados de um elo só valem com `ONLINE`
  (convenções §1.3): elo OFFLINE aparece sem ritmo nem lead time ("—"), nunca com o último valor como se fosse atual.
  A Produção (nós) está ONLINE quando o twin respondeu.
- **Lead time da cadeia** = soma dos `LeadTimeMedio` LOCAIS dos elos ONLINE com valor ≥ 0, pela mesma função do
  twin (`nucleo.estado_gemeo.lead_time_cadeia`). Elo OFFLINE ou com −1 fica fora e é sinalizado; nunca entra como
  zero. Nenhum relógio de outra máquina é subtraído. O valor que o twin publicou (`Cadeia.LeadTimeCadeia`) vem junto
  para conferência.
- **Decisão com dado do vizinho** (RF-A3-09): "estoque do Fornecedor X < limite Y → StatusLinha Z", com Y de
  `config/cadeia.yaml` (`decisao.estoque_minimo`) e Z o `StatusLinha` que o twin publicou. Fornecedor OFFLINE → sem
  decisão (o valor velho não decide nada). `PARADA`/`SEM_DADOS` prevalecem sobre `RISCO_FALTA`.

Twin fora do ar (RNF-02, como `nucleo.aas_leitura`): depois de uma falha de conexão, as leituras ao mesmo `url` são
puladas por `PAUSA_APOS_FALHA_S` e devolvem "indisponível" na hora, para a página não travar a cada atualização.

Tudo é emulado (ADR-0002). O rótulo da Produção sai de `EstadoGemeo.Origem` cruzado com `config/origens.yaml`
(`medida`), o mesmo critério de `kpis.apresentar` na página Rastreio (ADR-0013, ADR-0025): origem fora de `medida`
(`roteiro`, `teste`, desconhecida) → "demonstração (inclui dado sintético)"; `godot` → planta virtual determinística
(demonstração, não medição física); `hardware` → ESP32 físico. Duas marcas separadas por elo: `substituto` = elo
EMULADO por nós no lugar de um grupo parceiro (P-04, Fornecedor e Distribuição) e `dado_emulado` = o dado do elo vem
de fonte emulada (ADR-0002; a Produção também, salvo se todos os eventos vierem de `hardware`).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from time import monotonic
from typing import Any

from asyncua import Client, ua

from nucleo.dados import ORIGENS_MEDIDAS
from nucleo.estado_gemeo import (
    OFFLINE,
    ONLINE,
    PARADA,
    RISCO_FALTA,
    SEM_DADOS,
    LeadTimeCadeia,
    lead_time_cadeia,
)
from nucleo.parametros_cadeia import Cadeia, Elo

log = logging.getLogger(__name__)

T2T_URL_PADRAO = "opc.tcp://localhost:4851"
TIMEOUT_S = 2.0
PAUSA_APOS_FALHA_S = 10.0
PRODUCAO = "Producao"
ESTOQUE = "EstoqueFornecedor"
_falhou_em: dict[str, float] = {}      # url → instante (monotonic) da última falha de conexão

# Nós do nosso elo lidos de EstadoGemeo (contrato §1.1).
NOS_ESTADO = ("RitmoReal", "LeadTimeMedio", "LeadTimeAmostras", "StatusLinha", "MotivoStatus", "UltimaPeca",
              "Origem", "Referencia", "Batimento", "Elo", "Grupo")
NOS_CADEIA = ("LeadTimeCadeia", "ElosNoLeadTime", "ElosForaDoLeadTime", "LeadTimeCompleto", "Decisao")
NOS_ELO_FIXOS = ("Status", "Reconexoes", "Url", "Emulado")
ORDEM_PAPEL = {"fornecedor": 0, "producao": 1, "distribuicao": 2}


@dataclass(frozen=True)
class EstadoElo:
    nome: str
    papel: str
    emulado: bool                       # elo substituto: EMULADO por nós no lugar de um grupo parceiro (P-04)
    url: str
    status: str                         # ONLINE | OFFLINE
    reconexoes: int | None
    ritmo: float | None                 # RitmoReal; None se OFFLINE ou não lido
    unidade_ritmo: str
    lead_time_s: float | None           # LeadTimeMedio LOCAL; None se OFFLINE ou −1
    status_linha: str | None            # StatusLinha do próprio elo; None se OFFLINE
    origem: str                         # de onde vem o número (texto para a página, ADR-0013)
    valores: dict[str, Any] = field(default_factory=dict)   # valores lidos (só se ONLINE)
    dado_emulado: bool | None = None    # dado de fonte emulada (ADR-0002); None = não declarado (parceiro real)
    sintetico: bool = False             # inclui origem fora de config/origens.yaml → medida (roteiro, teste…)

    @property
    def online(self) -> bool:
        return self.status == ONLINE


@dataclass(frozen=True)
class DecisaoVizinho:
    """Cálculo com o dado do vizinho (RF-A3-09): estoque do fornecedor × limite → StatusLinha."""

    fornecedor: str | None              # nome do elo fornecedor (None se a config não tem)
    fornecedor_status: str
    estoque: float | None               # None = fornecedor OFFLINE ou não lido
    limite: float
    abaixo: bool | None                 # estoque < limite; None = sem dado
    status_linha: str | None            # StatusLinha publicado pelo twin (Z)
    decisao_twin: str                   # texto de Cadeia.Decisao
    calculo: str                        # "estoque do Fornecedor X < limite Y → StatusLinha Z"
    coerente: bool | None               # o status publicado bate com a regra aplicada ao estoque lido


@dataclass(frozen=True)
class EstadoCadeia:
    url: str
    disponivel: bool
    erro: str | None
    elos: tuple[EstadoElo, ...]         # na ordem da cadeia: fornecedor → produção → distribuição
    lead_time: LeadTimeCadeia | None    # recalculado aqui com a função do twin
    lead_time_publicado_s: float | None  # Cadeia.LeadTimeCadeia (None = −1 ou não lido)
    decisao: DecisaoVizinho | None
    producao: dict[str, Any] = field(default_factory=dict)  # EstadoGemeo.* lido

    @property
    def sintetico(self) -> bool:
        """Algum número somado inclui dado sintético (roteiro, teste): só demonstração (ADR-0013, ADR-0025)."""
        return any(e.sintetico for e in self.elos)

    def elo(self, nome: str) -> EstadoElo | None:
        return next((e for e in self.elos if e.nome == nome), None)


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _lead(v: Any) -> float | None:
    x = _num(v)
    return None if x is None or x < 0 else x       # −1 = sem dado (nunca 0)


def origem_elo(elo: Elo) -> str:
    if elo.emulado:
        return "elo EMULADO localmente por nós (P-04): parâmetros de emulação, não medição"
    return f"gêmeo de outro grupo ({elo.url}), lido pelo cliente da cadeia"


DESCRICAO_ORIGEM = {
    "emulador:godot": "planta virtual godot (determinística: demonstração, não medição física, ADR-0013)",
    "emulador:operador": "pessoa no botão virtual (emulador)",
    "hardware": "ESP32 físico (hardware)",
}


@dataclass(frozen=True)
class OrigemProducao:
    texto: str                          # "origem do número" na página
    sintetico: bool                     # inclui origem fora de `medida` (config/origens.yaml)
    dado_emulado: bool                  # ADR-0002: só não é emulado se todos os eventos vierem de `hardware`


def classificar_origem(origem_eventos: str, medidas: frozenset[str] | set[str] = ORIGENS_MEDIDAS) -> OrigemProducao:
    """Rótulo da Produção a partir de `EstadoGemeo.Origem` ("emulador:godot,emulador:roteiro") e da lista `medida`
    de config/origens.yaml, com o mesmo critério da página Rastreio (ADR-0013, ADR-0025)."""
    origens = sorted({o.strip() for o in origem_eventos.split(",") if o.strip()})
    if not origens:
        return OrigemProducao("sem eventos de peça (origem não declarada)", False, True)
    fora = [o for o in origens if o not in medidas]
    emulado = set(origens) != {"hardware"}
    if fora:
        return OrigemProducao(
            f"demonstração (inclui dado sintético: {', '.join(fora)}); origens {', '.join(origens)}; sem valor de "
            "medição (config/origens.yaml; ADR-0013, ADR-0025); eventos com ts do gateway", True, emulado)
    partes = "; ".join(DESCRICAO_ORIGEM.get(o, o) for o in origens)
    return OrigemProducao(f"{partes}; origem {', '.join(origens)}; eventos com ts do gateway", False, emulado)


def origem_producao(origem_eventos: str) -> str:
    return classificar_origem(origem_eventos).texto


def caminhos(cadeia: Cadeia) -> list[str]:
    """Nós lidos numa chamada só (sem `ns=2;s=`)."""
    lista = [f"EstadoGemeo.{n}" for n in NOS_ESTADO] + [f"Cadeia.{n}" for n in NOS_CADEIA]
    for elo in cadeia.elos:
        nomes = list(NOS_ELO_FIXOS) + [n.nome for n in elo.nos if n.nome not in NOS_ELO_FIXOS]
        lista += [f"Cadeia.{elo.nome}.{n}" for n in nomes]
    return lista


async def _ler_async(url: str, nos: Sequence[str], timeout: float) -> dict[str, Any]:
    """{caminho: valor}; nó ausente ou com status ruim fica fora (o painel mostra "—")."""
    cliente = Client(url, timeout=timeout)
    cliente.session_timeout = 60_000           # ms; abaixo do máximo do servidor (evita aviso a cada leitura)
    await asyncio.wait_for(cliente.connect(), timeout)
    try:
        nodes = [cliente.get_node(f"ns=2;s={c}") for c in nos]
        dvs = await asyncio.wait_for(cliente.read_attributes(nodes, ua.AttributeIds.Value), timeout)
    finally:
        try:
            await asyncio.wait_for(cliente.disconnect(), timeout)
        except (OSError, TimeoutError, ua.UaError) as erro:   # servidor caiu entre a leitura e a desconexão
            log.debug("desconexão de %s falhou: %s", url, type(erro).__name__)
    return {c: dv.Value.Value for c, dv in zip(nos, dvs, strict=True)
            if dv.StatusCode is None or dv.StatusCode.is_good()}


def ler_valores(url: str, nos: Sequence[str], timeout: float = TIMEOUT_S) -> dict[str, Any]:
    """Leitura síncrona (as páginas do Streamlit não têm laço asyncio). Levanta OSError/TimeoutError se o twin
    não responde."""
    return asyncio.run(_ler_async(url, nos, timeout))


def montar(cadeia: Cadeia, url: str, v: dict[str, Any]) -> EstadoCadeia:
    """EstadoCadeia a partir dos valores lidos (função pura; testada sem rede)."""
    producao = {n: v.get(f"EstadoGemeo.{n}") for n in NOS_ESTADO}
    elos: list[EstadoElo] = []
    for elo in cadeia.elos:
        base = f"Cadeia.{elo.nome}"
        status = v.get(f"{base}.Status") if v.get(f"{base}.Status") in (ONLINE, OFFLINE) else OFFLINE
        on = status == ONLINE
        valores = {n.nome: v.get(f"{base}.{n.nome}") for n in elo.nos} if on else {}
        unidade = next((n.unidade for n in elo.nos if n.nome == "RitmoReal"), "")
        recon = v.get(f"{base}.Reconexoes")
        elos.append(EstadoElo(
            nome=elo.nome, papel=elo.papel, emulado=bool(v.get(f"{base}.Emulado", elo.emulado)),
            url=str(v.get(f"{base}.Url") or elo.url), status=status,
            reconexoes=int(recon) if isinstance(recon, int) else None,
            ritmo=_num(valores.get("RitmoReal")), unidade_ritmo=unidade,
            lead_time_s=_lead(valores.get("LeadTimeMedio")),
            status_linha=(str(valores["StatusLinha"]) if on and valores.get("StatusLinha") else None),
            origem=origem_elo(elo), valores=valores, dado_emulado=True if elo.emulado else None))
    org = classificar_origem(str(producao.get("Origem") or ""))
    nosso = EstadoElo(
        nome=str(producao.get("Elo") or cadeia.elo or PRODUCAO), papel="producao", emulado=False, url=url,
        status=ONLINE, reconexoes=None, ritmo=_num(producao.get("RitmoReal")), unidade_ritmo="peças/h",
        lead_time_s=_lead(producao.get("LeadTimeMedio")), status_linha=producao.get("StatusLinha") or None,
        origem=org.texto, valores=producao, dado_emulado=org.dado_emulado, sintetico=org.sintetico)
    elos.append(nosso)
    elos.sort(key=lambda e: ORDEM_PAPEL.get(e.papel, 9))
    # Mesma regra do twin: o nosso elo entra como ONLINE quando há valor; vizinhos pelo Status espelhado.
    lt = lead_time_cadeia({e.nome: (e.status, e.lead_time_s) for e in elos})
    return EstadoCadeia(url=url, disponivel=True, erro=None, elos=tuple(elos), lead_time=lt,
                        lead_time_publicado_s=_lead(v.get("Cadeia.LeadTimeCadeia")),
                        decisao=decidir(cadeia, elos, producao.get("StatusLinha"),
                                        str(v.get("Cadeia.Decisao") or "")),
                        producao=producao)


def decidir(cadeia: Cadeia, elos: Sequence[EstadoElo], status_publicado: Any, decisao_twin: str) -> DecisaoVizinho:
    """Mostra o cálculo RF-A3-09 com o mesmo limite que o twin usa (`decisao.estoque_minimo`)."""
    limite = cadeia.estoque_minimo
    forn = next((e for e in elos if e.papel == "fornecedor"), None)
    z = str(status_publicado) if status_publicado else None
    if forn is None:
        return DecisaoVizinho(None, OFFLINE, None, limite, None, z, decisao_twin,
                              "sem elo fornecedor em config/cadeia.yaml: nenhuma decisão", None)
    estoque = _num(forn.valores.get(ESTOQUE)) if forn.online else None
    if estoque is None:
        motivo = "OFFLINE" if not forn.online else "estoque não lido"
        return DecisaoVizinho(forn.nome, forn.status, None, limite, None, z, decisao_twin,
                              f"estoque do {forn.nome} — ({motivo}) → sem decisão; o valor antigo não é usado "
                              f"(StatusLinha {z or '—'})", None)
    abaixo = estoque < limite
    sinal = "<" if abaixo else "≥"
    if z in (PARADA, SEM_DADOS):
        efeito = f"StatusLinha {z} (prevalece sobre {RISCO_FALTA})" if abaixo else f"StatusLinha {z}"
        coerente = True
    elif abaixo:
        efeito, coerente = f"StatusLinha {z or '—'}", z == RISCO_FALTA
    else:
        efeito, coerente = f"nenhuma ação (StatusLinha {z or '—'})", z != RISCO_FALTA
    calculo = f"estoque do {forn.nome} {estoque:g} {sinal} limite {limite:g} → {efeito}"
    return DecisaoVizinho(forn.nome, forn.status, estoque, limite, abaixo, z, decisao_twin, calculo, coerente)


def indisponivel(cadeia: Cadeia, url: str, erro: str) -> EstadoCadeia:
    elos = [EstadoElo(e.nome, e.papel, e.emulado, e.url, OFFLINE, None, None, "", None, None, origem_elo(e),
                      dado_emulado=True if e.emulado else None) for e in cadeia.elos]
    elos.append(EstadoElo(cadeia.elo or PRODUCAO, "producao", False, url, OFFLINE, None, None, "peças/h", None,
                          None, "twin-t2t indisponível: origem não lida", dado_emulado=None))
    elos.sort(key=lambda e: ORDEM_PAPEL.get(e.papel, 9))
    return EstadoCadeia(url, False, erro, tuple(elos), None, None, None)


def ler_cadeia(cadeia: Cadeia, url: str = T2T_URL_PADRAO, timeout: float = TIMEOUT_S) -> EstadoCadeia:
    """Estado da cadeia para a página. Nunca levanta por falha do twin: devolve `disponivel=False`."""
    falha = _falhou_em.get(url)
    if falha is not None and (resta := PAUSA_APOS_FALHA_S - (monotonic() - falha)) > 0:
        return indisponivel(cadeia, url, f"twin-t2t não respondeu há pouco; nova tentativa em {resta:.0f} s")
    try:
        valores = ler_valores(url, caminhos(cadeia), timeout)
    except (OSError, TimeoutError, ua.UaError, ConnectionError) as erro:
        _falhou_em[url] = monotonic()
        log.info("twin-t2t indisponível em %s: %s", url, type(erro).__name__)
        return indisponivel(cadeia, url, f"twin-t2t indisponível em {url} ({type(erro).__name__})")
    _falhou_em.pop(url, None)
    if not any(k.startswith("EstadoGemeo.") for k in valores):
        return indisponivel(cadeia, url, f"{url} respondeu sem o address space do twin-t2t (ns=2;s=EstadoGemeo)")
    return montar(cadeia, url, valores)


def parcelas_lead_time(estado: EstadoCadeia) -> str:
    """"Fornecedor 120.0 + Producao 24.2 + Distribuicao 60.0 = 204.2 s" (só os elos somados); "—" sem nenhum."""
    lt = estado.lead_time
    if lt is None or lt.soma_s is None:
        return "—"
    partes = [f"{e.nome} {e.lead_time_s:.1f}" for e in estado.elos if e.nome in lt.incluidos]
    return f"{' + '.join(partes)} = {lt.soma_s:.1f} s"
