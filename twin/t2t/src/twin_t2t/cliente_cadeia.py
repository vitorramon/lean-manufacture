"""Cliente da cadeia (tarefa 3.2, RF-A3-05; ADR-0011 item 2, ADR-0028; docs/convencoes-fase-3.md §4).

Lê os vizinhos declarados em `config/cadeia.yaml` → `elos` (uma tarefa asyncio por elo) e espelha cada um em
`Cadeia.<Elo>.*` pelo `ServidorT2T.publicar_elo`. Nada vai para o SQLite nem para o AAS.

- **Reconexão automática:** conexão ou leitura falhou (erro ou acima de `cliente.timeout_s`) → elo `OFFLINE`, espera
  `reconexao_inicial_s`, dobrando a cada falha seguida até `reconexao_max_s`; volta a tentar para sempre.
- **Prazo do batimento:** conectado, mas `Batimento` do vizinho sem mudar por `batimento_parado_s` (medidos no
  relógio DESTE processo, nunca comparando com o relógio do vizinho) → `OFFLINE` ("congelado"); voltou a mudar →
  `ONLINE`. Vizinho sem nó `Batimento` declarado fica só com o critério de conexão/leitura. `Batimento` declarado
  mas ilegível (status ruim) conta como parado: o prazo continua correndo desde a última mudança (ou desde a
  conexão) e, vencido, o elo vai a `OFFLINE`.
- **Nunca derruba nada:** toda exceção da leitura de um elo fica contida na tarefa dele; o servidor e os outros elos
  seguem. Cada falha e cada mudança de estado vão para o log (registro de falhas, RF-A3-07).

A lógica de estado (`MonitorElo`) é pura, com relógio injetado, e é testada sem rede. `vigiar` é o laço asyncua
genérico, reaproveitado pelos elos emulados (`twin/cadeia`, tarefa 3.3) para ler a Produção.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from asyncua import Client, ua
from nucleo.estado_gemeo import OFFLINE, ONLINE
from nucleo.parametros_cadeia import Cadeia

log = logging.getLogger(__name__)
BATIMENTO = "Batimento"
Relogio = Callable[[], float]


@dataclass(frozen=True)
class ParametrosCliente:
    """`config/cadeia.yaml` → `cliente` (segundos)."""

    periodo_leitura_s: float = 1.0
    timeout_s: float = 3.0
    reconexao_inicial_s: float = 1.0
    reconexao_max_s: float = 10.0
    batimento_parado_s: float = 10.0

    @classmethod
    def de(cls, secao: Mapping[str, Any] | None) -> ParametrosCliente:
        secao = dict(secao or {})
        valores = {}
        for nome in cls.__dataclass_fields__:
            if nome in secao:
                v = secao[nome]
                if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0:
                    raise ValueError(f"cliente.{nome} precisa ser número > 0: {v!r}")
                valores[nome] = float(v)
        p = cls(**valores)
        if p.reconexao_max_s < p.reconexao_inicial_s:
            raise ValueError("cliente.reconexao_max_s < cliente.reconexao_inicial_s")
        return p


@dataclass
class Leitura:
    """Estado de um vizinho como o cliente o vê: o que vai para `Cadeia.<Elo>.*`."""

    status: str = OFFLINE
    valores: dict[str, Any] = field(default_factory=dict)
    reconexoes: int = 0
    motivo: str = "ainda não conectado"


class MonitorElo:
    """Máquina de estado de um elo (pura; relógio injetado).

    `conectou()` → `leitura(valores)` repetidas → `falhou(motivo)` devolve a espera até a próxima tentativa.
    `reconexoes` conta as conexões bem-sucedidas depois da primeira (a primeira não é REconexão).
    """

    def __init__(self, params: ParametrosCliente, relogio: Relogio = time.monotonic,
                 batimento_declarado: bool = False):
        self.p = params
        self.relogio = relogio
        self.batimento_declarado = batimento_declarado
        self.estado = Leitura()
        self.falhas_seguidas = 0
        self._ja_conectou = False
        self._batimento: Any = None
        self._batimento_mudou_em = 0.0

    def conectou(self) -> None:
        if self._ja_conectou:
            self.estado.reconexoes += 1
        self._ja_conectou = True
        self.falhas_seguidas = 0
        self._batimento = None          # nova sessão: o prazo do batimento recomeça
        self._batimento_mudou_em = self.relogio()

    def leitura(self, valores: Mapping[str, Any]) -> str:
        agora = self.relogio()
        self.estado.valores = {**self.estado.valores, **valores}
        bat = valores.get(BATIMENTO)
        if bat is None and not self.batimento_declarado:
            self._ok("lido (sem Batimento no contrato do elo)")
        elif bat is None:
            parado = agora - self._batimento_mudou_em
            if parado >= self.p.batimento_parado_s:
                self.estado.status = OFFLINE
                self.estado.motivo = (f"Batimento declarado e ilegível; sem mudança há {parado:.1f} s "
                                      f"(prazo {self.p.batimento_parado_s:g} s)")
            else:
                self._ok(f"lido (Batimento ilegível nesta leitura; prazo correndo há {parado:.1f} s)")
        elif self._batimento is None or bat != self._batimento:
            self._batimento, self._batimento_mudou_em = bat, agora
            self._ok("lido")
        elif agora - self._batimento_mudou_em >= self.p.batimento_parado_s:
            self.estado.status = OFFLINE
            self.estado.motivo = (f"congelado: Batimento={bat} parado há {agora - self._batimento_mudou_em:.1f} s "
                                  f"(prazo {self.p.batimento_parado_s:g} s)")
        return self.estado.status

    def _ok(self, motivo: str) -> None:
        self.estado.status = ONLINE
        self.estado.motivo = motivo

    def espera(self) -> float:
        """Espera antes da próxima tentativa: inicial × 2^(falhas−1), limitada a `reconexao_max_s`."""
        if self.falhas_seguidas <= 0:
            return 0.0
        return min(self.p.reconexao_inicial_s * 2 ** (self.falhas_seguidas - 1), self.p.reconexao_max_s)

    def falhou(self, motivo: str) -> float:
        self.falhas_seguidas += 1
        self.estado.status = OFFLINE
        self.estado.motivo = motivo
        return self.espera()


def _motivo(erro: BaseException) -> str:
    texto = str(erro).strip() or erro.__class__.__name__
    return f"{erro.__class__.__name__}: {texto}"[:200]


async def _dormir(parar: asyncio.Event, segundos: float) -> None:
    try:
        await asyncio.wait_for(parar.wait(), timeout=segundos)
    except TimeoutError:
        return          # fim normal da espera; `parar` não foi sinalizado


async def _desconectar(cliente: Client) -> None:
    try:
        await asyncio.wait_for(cliente.disconnect(), timeout=2)
    except Exception as erro:  # noqa: BLE001 — vizinho já caiu; só liberar o socket
        log.debug("desconexão sem resposta do vizinho (%s); fechando o socket", _motivo(erro))
        try:
            cliente.disconnect_socket()
        except Exception as erro2:  # noqa: BLE001
            log.debug("socket já fechado: %s", _motivo(erro2))


class LeituraIncompleta(RuntimeError):
    """Nenhum nó do vizinho voltou com status Good."""


async def vigiar(nome: str, url: str, nos: Mapping[str, str], params: ParametrosCliente,
                 publicar: Callable[[Leitura], Awaitable[None]], parar: asyncio.Event,
                 relogio: Relogio = time.monotonic, monitor: MonitorElo | None = None) -> None:
    """Lê `nos` ({variável: NodeId}) de `url` a cada `periodo_leitura_s` até `parar`, reconectando sempre.

    Chama `publicar(Leitura)` a cada leitura e a cada falha. Nó com status ruim fica fora daquela leitura (mantém o
    último valor); se nenhum voltar Good, conta como falha. Nunca levanta exceção para quem chamou.
    """
    m = monitor or MonitorElo(params, relogio)
    m.batimento_declarado = BATIMENTO in nos
    anterior = None
    while not parar.is_set():
        cliente = Client(url, timeout=params.timeout_s)
        conectado = False
        try:
            await asyncio.wait_for(cliente.connect(), timeout=params.timeout_s)
            conectado = True
            m.conectou()
            log.info("elo %s: conectado em %s (reconexões=%d)", nome, url, m.estado.reconexoes)
            nodes = [(var, cliente.get_node(nid)) for var, nid in nos.items()]
            while not parar.is_set():
                dvs = await asyncio.wait_for(
                    cliente.read_attributes([n for _, n in nodes], ua.AttributeIds.Value), timeout=params.timeout_s)
                valores = {var: dv.Value.Value for (var, _), dv in zip(nodes, dvs, strict=True)
                           if dv.StatusCode is not None and dv.StatusCode.is_good() and dv.Value is not None}
                if not valores:
                    raise LeituraIncompleta("nenhum nó do contrato com status Good")
                m.leitura(valores)
                anterior = _registrar(nome, m.estado, anterior)
                await publicar(_copia(m.estado))
                await _dormir(parar, params.periodo_leitura_s)
        except asyncio.CancelledError:
            raise
        except Exception as erro:  # noqa: BLE001 — qualquer falha do vizinho vira OFFLINE, nunca derruba o twin
            espera = m.falhou(_motivo(erro))
            anterior = _registrar(nome, m.estado, anterior)
            log.info("elo %s: falha (%s seguida[s]): %s; nova tentativa em %.1f s",
                     nome, m.falhas_seguidas, m.estado.motivo, espera)
            try:
                await publicar(_copia(m.estado))
            except Exception:
                log.exception("elo %s: falha ao publicar o estado OFFLINE", nome)
            if conectado:
                await _desconectar(cliente)
            await _dormir(parar, espera)
            continue
        if conectado:
            await _desconectar(cliente)


def _copia(e: Leitura) -> Leitura:
    return Leitura(e.status, dict(e.valores), e.reconexoes, e.motivo)


def _registrar(nome: str, e: Leitura, anterior: str | None) -> str:
    if e.status != anterior:
        nivel = logging.WARNING if e.status == OFFLINE else logging.INFO
        log.log(nivel, "elo %s: %s -> %s (%s; reconexões=%d)", nome, anterior or "início", e.status, e.motivo,
                e.reconexoes)
    return e.status


class ClienteCadeia:
    """Uma tarefa `vigiar` por elo de `config/cadeia.yaml`, publicando no `ServidorT2T` (Cadeia.<Elo>.*)."""

    def __init__(self, servidor, cadeia: Cadeia, params: ParametrosCliente | None = None,
                 relogio: Relogio = time.monotonic):
        self.servidor = servidor
        self.cadeia = cadeia
        self.params = params or ParametrosCliente.de(cadeia.cliente)
        self.relogio = relogio
        self.monitores = {e.nome: MonitorElo(self.params, relogio) for e in cadeia.elos}

    async def rodar(self, parar: asyncio.Event) -> None:
        from twin_t2t.servidor import LeituraElo  # import tardio: evita ciclo servidor ↔ cliente

        async def um(elo) -> None:
            async def publicar(leitura: Leitura) -> None:
                await self.servidor.publicar_elo(elo.nome, LeituraElo(leitura.status, leitura.valores,
                                                                      leitura.reconexoes))
            await vigiar(elo.nome, elo.url, {n.nome: n.node_id for n in elo.nos}, self.params, publicar, parar,
                         self.relogio, self.monitores[elo.nome])

        await asyncio.gather(*(um(e) for e in self.cadeia.elos))
