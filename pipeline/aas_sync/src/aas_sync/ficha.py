"""Ficha da peça no AAS (tarefa 2.5; RF-A2-07, ADR-0008 item 6, ADR-0020; convenções da Fase 2 §6). Lógica pura.

Entrada: as linhas de `eventos(ts, peca, estacao, evento, valor)` de uma peça, em ordem de `ts`, lidas do SQLite
que o próprio aas-sync escreve; a ficha é uma projeção da tabela, refeita a cada evento novo (sobrevive ao reinício
do aas-sync). Saída: um shell e um submodelo `Rastreabilidade` por peça.

Definições iguais às de `app/nucleo/pecas.py` (tarefa 2.6), para a ficha do AAS e a página Rastreio darem o mesmo
número (o app não importa este pacote, nem o contrário: são camadas diferentes). A repetição é exceção registrada
no ADR-0027 e vigiada por `tests/aas_sync/test_ficha_cruzada.py`, que roda as duas sobre os mesmos eventos:

- Situação: `expirada` se tem o evento `expirada`; `concluida` com início e fim do trecho; `aberta` só com o
  início; `incompleta` sem o início. Início e fim do trecho vêm de `config/rastreio.yaml` (`trecho`).
- Lead time = `fim_trecho.ts − inicio_trecho.ts` (primeira leitura de cada), só para peça concluída.
- Processamento = soma dos `fim.valor` (`dur_s`). Espera = lead time − processamento.
- Tempo por estação: cada ciclo associado (`inicio` → próximo `fim` da mesma estação) é um segmento da estação do
  botão com processamento = `dur_s`, mesmo com outros eventos dentro dele; os demais intervalos entre eventos
  consecutivos vão para a estação do evento de chegada. Recorte na janela [entrada, saída] da peça concluída. Soma
  das esperas por estação = espera da peça.
- Resultado do teste = primeiro evento com valor 0/1 que não seja `inicio`, `fim` nem `expirada` (ADR-0026).

Ligação com a planta virtual: só para peça cujo id casa com `planta.padrao_peca` de `config/rastreio.yaml`. Ela
recebe como `globalAssetId` o GS1 Digital Link canônico `<dominio>/01/<gtin>/21/<peca>`, o mesmo do AAS `WP_` que o
`mes` da base cria, e a propriedade `AasDaPlanta` com o id desse AAS. É só referência: a base não é tocada
(ADR-0001), e no perfil reduzido (sem `mes`, ADR-0016) o AAS `WP_` não existe.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from aas_sync.aas import PREFIXO, _propriedade

IDSHORT_FICHA = "Rastreabilidade"
SEMANTIC_FICHA = f"{PREFIXO}smt:{IDSHORT_FICHA}:1:0"
INICIO_CICLO, FIM_CICLO, EXPIRADA = "inicio", "fim", "expirada"

Linha = tuple[str, str, str, str, float | None]   # (ts, peca, estacao, evento, valor)
CASAS = 6               # o ts do gateway tem resolução de µs: arredonda o ruído de ponto flutuante das subtrações


def _r(x: float | None) -> float | None:
    return None if x is None else round(x, CASAS)


def id_shell_peca(peca: str) -> str:
    return f"{PREFIXO}aas:peca:{peca}"


def id_submodelo_peca(peca: str) -> str:
    return f"{PREFIXO}sm:peca:{peca}:{IDSHORT_FICHA}:1"


def id_short(texto: str) -> str:
    """idShort do AAS v3 (`^[a-zA-Z][a-zA-Z0-9_]*$`): troca o resto por `_`."""
    limpo = re.sub(r"[^A-Za-z0-9_]", "_", texto)
    return limpo if limpo[:1].isalpha() else f"X_{limpo}"


def da_planta(peca: str, planta: dict[str, Any] | None) -> bool:
    padrao = (planta or {}).get("padrao_peca")
    return bool(padrao) and re.fullmatch(padrao, peca) is not None


def digital_link(peca: str, planta: dict[str, Any]) -> str:
    return f"{planta['dominio_digital_link'].rstrip('/')}/01/{planta['gtin']}/21/{peca}"


def aas_da_planta(peca: str, planta: dict[str, Any]) -> str:
    return f"{planta['prefixo_aas']}{peca.replace('-', '_')}"


def global_asset_id(peca: str, planta: dict[str, Any] | None) -> str:
    return digital_link(peca, planta) if da_planta(peca, planta) else f"{PREFIXO}asset:peca:{peca}"


def _dt(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def _resultado(evento: str, valor: float | None) -> int | None:
    if evento in (INICIO_CICLO, FIM_CICLO, EXPIRADA) or valor is None or valor not in (0, 1):
        return None
    return int(valor)


def _ciclos(linhas: list[Linha]) -> list[tuple[int, int]]:
    """(inicio, fim) de cada ciclo associado: o `inicio` fecha no próximo `fim` da mesma estação; sobreposto fica fora."""
    abertos: dict[str, int] = {}
    pares: list[tuple[int, int]] = []
    for k, (_, _, est, ev, _) in enumerate(linhas):
        if ev == INICIO_CICLO:
            abertos[est] = k
        elif ev == FIM_CICLO and est in abertos:
            i = abertos.pop(est)
            if not pares or i >= pares[-1][1]:
                pares.append((i, k))
    return pares


def segmentos(linhas: list[Linha], inicio: datetime | None = None,
              fim: datetime | None = None) -> list[tuple[str, float, float]]:
    """(estação, duração, processamento) de cada segmento da trajetória, como `nucleo.pecas.segmentos`."""
    if len(linhas) < 2:
        return []
    ts = [_dt(x[0]) for x in linhas]
    ini_j, fim_j = inicio or ts[0], fim or ts[-1]
    dentro = {k: (i, j) for i, j in _ciclos(linhas) for k in range(i, j)}
    saida: list[tuple[str, float, float]] = []
    k = 0
    while k < len(linhas) - 1:
        if k in dentro:
            a, b = dentro[k]
            estacao = linhas[a][2]
            k = b
        else:
            a, b = k, k + 1
            estacao = linhas[b][2]
            k += 1
        proc = float(linhas[b][4] or 0.0) if linhas[b][3] == FIM_CICLO else 0.0
        dur = max(0.0, (min(ts[b], fim_j) - max(ts[a], ini_j)).total_seconds())
        if dur == 0.0 and proc == 0.0 and (ts[b] <= ini_j or ts[a] >= fim_j) and ts[a] != ts[b]:
            continue
        saida.append((estacao, dur, proc))
    return saida


def resumir(linhas: list[Linha], trecho: dict[str, Any]) -> dict[str, Any]:
    """Resumo da peça. `linhas` em ordem de ts (como `Banco.eventos_da_peca` devolve)."""
    if not linhas:
        raise ValueError("peça sem eventos")
    eventos = {ev for _, _, _, ev, _ in linhas}
    entrada = next((ts for ts, _, _, ev, _ in linhas if ev == trecho["inicio_trecho"]), None)
    saida = next((ts for ts, _, _, ev, _ in linhas if ev == trecho["fim_trecho"]), None)
    if EXPIRADA in eventos:
        situacao = "expirada"
    elif entrada and saida:
        situacao = "concluida"
    elif entrada:
        situacao = "aberta"
    else:
        situacao = "incompleta"
    lead = (_dt(saida) - _dt(entrada)).total_seconds() if situacao == "concluida" else None
    proc = float(sum(v for _, _, _, ev, v in linhas if ev == FIM_CICLO and v is not None))
    resultado = next((r for _, _, _, ev, v in linhas if (r := _resultado(ev, v)) is not None), None)
    tempos: dict[str, list[float]] = {}
    janela = (_dt(entrada), _dt(saida)) if situacao == "concluida" else (None, None)
    for estacao, dur, p in segmentos(linhas, *janela):
        t = tempos.setdefault(estacao, [0.0, 0.0])
        t[0] += dur
        t[1] += p
    return {
        "peca": linhas[0][1], "situacao": situacao, "entrada": entrada, "saida": saida, "lead_time_s": _r(lead),
        "processamento_s": _r(proc), "espera_s": _r(lead - proc) if lead is not None else None,
        "resultado_teste": resultado, "estacao_atual": linhas[-1][2], "n_eventos": len(linhas),
        "por_estacao": {e: {"tempo_s": _r(t), "processamento_s": _r(p), "espera_s": _r(t - p)}
                        for e, (t, p) in tempos.items()},
    }


def _colecao(id_short_: str | None, elementos: list[dict[str, Any]], descricao: str | None = None) -> dict[str, Any]:
    c: dict[str, Any] = {"modelType": "SubmodelElementCollection", "value": elementos}
    if id_short_ is not None:   # elementos de uma SubmodelElementList não têm idShort (AASd-120)
        c["idShort"] = id_short_
    if descricao:
        c["description"] = [{"language": "pt", "text": descricao}]
    return c


def montar_shell_peca(peca: str, planta: dict[str, Any] | None) -> dict[str, Any]:
    texto = (f"Peça {peca} do trecho montagem -> teste -> embalagem (ADR-0009). Dado emulado (ADR-0002). "
             "Escrito só pelo aas-sync a partir da tabela eventos (ADR-0007).")
    info: dict[str, Any] = {"assetKind": "Instance", "globalAssetId": global_asset_id(peca, planta)}
    if da_planta(peca, planta):
        texto += f" Peça da planta virtual: AAS da base {aas_da_planta(peca, planta)} (só referência)."
        info["specificAssetIds"] = [{"name": "serialNumber", "value": peca}]
    return {
        "modelType": "AssetAdministrationShell", "id": id_shell_peca(peca), "idShort": id_short(f"Peca_{peca}"),
        "description": [{"language": "pt", "text": texto}], "assetInformation": info,
        "submodels": [{"type": "ModelReference", "keys": [{"type": "Submodel", "value": id_submodelo_peca(peca)}]}],
    }


def montar_submodelo_peca(linhas: list[Linha], trecho: dict[str, Any], planta: dict[str, Any] | None,
                          qr: str | None) -> dict[str, Any]:
    r = resumir(linhas, trecho)
    peca = r["peca"]
    trajetoria = [
        _colecao(None, [
            _propriedade("Estacao", "xs:string", est, "estação (config/dispositivos.yaml)"),
            _propriedade("Evento", "xs:string", ev, "entrada, inicio, fim, teste, saida ou expirada"),
            _propriedade("Ts", "xs:dateTime", ts, "instante UTC carimbado pelo gateway"),
            _propriedade("Valor", "xs:double", val, "fim: dur_s [s]; teste: 1/0; expirada: idade [s]"),
        ])
        for ts, _, est, ev, val in linhas
    ]
    estacoes = [
        _colecao(id_short(est), [
            _propriedade("Estacao", "xs:string", est, "estação"),
            _propriedade("Tempo_s", "xs:double", t["tempo_s"], "intervalos que terminam nesta estação [s]"),
            _propriedade("Processamento_s", "xs:double", t["processamento_s"], "soma dos dur_s [s]"),
            _propriedade("Espera_s", "xs:double", t["espera_s"], "tempo − processamento [s]"),
        ])
        for est, t in r["por_estacao"].items()
    ]
    elementos = [
        _propriedade("Peca", "xs:string", peca, "identificador da peça (ADR-0008)"),
        _propriedade("QrBruto", "xs:string", qr, "primeiro QR lido (sem valor se o aas-sync não o viu)"),
        _propriedade("Situacao", "xs:string", r["situacao"], "aberta, concluida, expirada ou incompleta"),
        _propriedade("Entrada", "xs:dateTime", r["entrada"], f"primeiro '{trecho['inicio_trecho']}' (UTC)"),
        _propriedade("Saida", "xs:dateTime", r["saida"], f"primeiro '{trecho['fim_trecho']}' (UTC)"),
        _propriedade("LeadTime_s", "xs:double", r["lead_time_s"], "saída − entrada [s]; só peça concluída"),
        _propriedade("Processamento_s", "xs:double", r["processamento_s"], "soma dos dur_s dos ciclos [s]"),
        _propriedade("Espera_s", "xs:double", r["espera_s"], "lead time − processamento [s]"),
        _propriedade("ResultadoTeste", "xs:int", r["resultado_teste"], "1 aprovada, 0 reprovada (ADR-0026)"),
        _propriedade("EstacaoAtual", "xs:string", r["estacao_atual"], "estação do último evento"),
        _propriedade("NumeroEventos", "xs:int", r["n_eventos"], "linhas da peça em eventos"),
        _colecao("TemposPorEstacao", estacoes, "tempo, processamento e espera por estação, na ordem da passagem"),
        {"modelType": "SubmodelElementList", "idShort": "Trajetoria", "orderRelevant": True,
         "typeValueListElement": "SubmodelElementCollection", "value": trajetoria,
         "description": [{"language": "pt", "text": "eventos da peça em ordem de ts (tabela eventos)"}]},
    ]
    if da_planta(peca, planta):
        elementos.append(_propriedade("AasDaPlanta", "xs:anyURI", aas_da_planta(peca, planta),
                                      "AAS da peça criado pelo mes da base (só no perfil base-completa)"))
        elementos.append(_propriedade("DigitalLink", "xs:anyURI", digital_link(peca, planta),
                                      "GS1 Digital Link da peça (= globalAssetId das duas fichas)"))
    return {
        "modelType": "Submodel", "id": id_submodelo_peca(peca), "idShort": IDSHORT_FICHA, "kind": "Instance",
        "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": SEMANTIC_FICHA}]},
        "description": [{"language": "pt", "text": "Ficha de rastreabilidade da peça: projeção da tabela eventos "
                                                   "(dado emulado, ADR-0002)."}],
        "submodelElements": elementos,
    }


def qr_do_submodelo(submodelo: dict[str, Any] | None) -> str | None:
    """QR bruto já gravado numa ficha existente (para não apagá-lo depois de um reinício do aas-sync)."""
    for e in (submodelo or {}).get("submodelElements", []):
        if e.get("idShort") == "QrBruto":
            return e.get("value") or None
    return None
