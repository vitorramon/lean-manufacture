"""Numeração persistida do aas-sync (revisão de contratos da Fase 2, achado 3; RF-A2-05/09, ADR-0026 item 3).

Sem rede: as notificações são entregues como o cliente OPC UA as entregaria. Eventos sintéticos de teste.
"""

from __future__ import annotations

import asyncio
import json
from datetime import timedelta

import pytest
from aas_sync.__main__ import Sincronizador
from aas_sync.configuracao import Configuracao
from aas_sync.processador import Notificacao
from conftest import CONFIG, T0


def _ev(k: int) -> Notificacao:
    ts = T0 + timedelta(seconds=k)
    corpo = json.dumps({"n": k, "ts": ts.isoformat(), "peca": f"P{k:04d}", "estacao": "Bateria",
                        "evento": "entrada", "valor": None, "dispositivo": "qr-entrada", "qr": f"P{k:04d}"})
    return Notificacao("Rastreio", "UltimoEventoPeca", corpo, "String", ts)


async def _rodar(s: Sincronizador, notifs: list[Notificacao]) -> None:
    escritor = asyncio.create_task(s.escrever_banco())
    for x in notifs:
        s.entregar(x)
    await asyncio.wait_for(s.fila.join(), 5)
    escritor.cancel()
    await asyncio.gather(escritor, return_exceptions=True)
    s.banco.fechar()


@pytest.mark.asyncio
async def test_aas_sync_reiniciado_conta_os_eventos_publicados_enquanto_caido(tmp_path):
    cfg = Configuracao(db_path=str(tmp_path / "dados.db"), dispositivos_path=str(CONFIG), aas_ativo=False)
    inicio = Notificacao("Gateway", "Inicio", T0, "DateTime", T0)
    s1 = Sincronizador(cfg)
    await _rodar(s1, [inicio, *(_ev(k) for k in range(1, 11))])
    arq = tmp_path / "estado" / "aas-sync" / "numeracao-dados.json"
    assert json.loads(arq.read_text()) == {"inicio_gateway": T0.isoformat(), "ultimo_n_evento": 10,
                                           "ultimo_n_rejeicao": None}
    # aas-sync volta; o gateway (mesmo Inicio) publicou n = 11..22 nesse meio-tempo
    s2 = Sincronizador(cfg)
    await _rodar(s2, [inicio, _ev(23)])
    assert s2.processador.eventos_perdidos == 12
    assert s2.totais["eventos_perdidos"] == 12
    assert json.loads(arq.read_text())["ultimo_n_evento"] == 23


@pytest.mark.asyncio
async def test_numeracao_ilegivel_nao_impede_a_partida(tmp_path):
    arq = tmp_path / "estado" / "aas-sync" / "numeracao-dados.json"
    arq.parent.mkdir(parents=True)
    arq.write_text("{meio arquivo")
    s = Sincronizador(Configuracao(db_path=str(tmp_path / "dados.db"), dispositivos_path=str(CONFIG),
                                   aas_ativo=False))
    assert s.processador.ultimo_n_evento is None
    s.banco.fechar()
