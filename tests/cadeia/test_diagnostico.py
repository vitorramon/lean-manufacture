"""Roteiro de conexão localhost → ping → porta → OPC UA (tarefa 3.6, P-04). Só 127.0.0.1 e portas livres, sem rede
externa. O servidor de teste publica o contrato de interface (ns=2;s=EstadoGemeo.*) num processo à parte (thread com
laço próprio), porque o diagnóstico usa `asyncio.run` como a linha de comando."""

from __future__ import annotations

import asyncio
import threading
from typing import Self

import pytest
from asyncua import Server, ua
from cadeia import diagnostico as dg
from conftest import porta_livre

VT = ua.VariantType


class ServidorFicticio:
    """Elo mínimo no formato do contrato. `vivo=False` deixa o Batimento parado (gêmeo congelado)."""

    def __init__(self, nos: dict[str, tuple[VT, object]] | None = None, vivo: bool = True):
        self.porta = porta_livre()
        self.nos = nos or {"RitmoReal": (VT.Double, 240.0), "LeadTimeMedio": (VT.Double, 60.1),
                           "StatusLinha": (VT.String, "DESPACHANDO"), "Batimento": (VT.UInt32, 0)}
        self.vivo = vivo
        self.pronto = threading.Event()
        self.laco = asyncio.new_event_loop()
        self.fim: asyncio.Event | None = None
        self.thread = threading.Thread(target=self.laco.run_until_complete, args=(self._rodar(),), daemon=True)

    async def _rodar(self) -> None:
        self.fim = asyncio.Event()
        s = Server()
        await s.init()
        s.set_endpoint(f"opc.tcp://127.0.0.1:{self.porta}")
        s.set_security_policy([ua.SecurityPolicyType.NoSecurity])
        ns = await s.register_namespace("urn:teste:elo")
        obj = await s.nodes.objects.add_object(ua.NodeId("EstadoGemeo", ns), ua.QualifiedName("EstadoGemeo", ns))
        vars_ = {n: await obj.add_variable(ua.NodeId(f"EstadoGemeo.{n}", ns), ua.QualifiedName(n, ns),
                                           ua.Variant(v, vt)) for n, (vt, v) in self.nos.items()}
        async with s:
            self.pronto.set()
            b = 0
            while not self.fim.is_set():
                if self.vivo and "Batimento" in vars_:
                    b += 1
                    await vars_["Batimento"].write_value(ua.Variant(b, VT.UInt32))
                try:
                    await asyncio.wait_for(self.fim.wait(), 0.2)
                except TimeoutError:
                    pass

    def __enter__(self) -> Self:
        self.thread.start()
        assert self.pronto.wait(10), "servidor de teste não subiu"
        return self

    def __exit__(self, *_: object) -> None:
        self.laco.call_soon_threadsafe(self.fim.set)
        self.thread.join(10)


def status(r: dg.Resultado) -> list[str]:
    return [p.status for p in r.passos]


def test_elo_no_ar_todos_os_passos_ok():
    with ServidorFicticio() as s:
        r = dg.diagnosticar("127.0.0.1", s.porta, local_porta=s.porta, timeout=2, intervalo_s=0.6)
    assert [p.nome for p in r.passos] == ["localhost", "ping", "porta", "opcua"]
    assert status(r) == ["OK", "OK", "OK", "OK"], [p.detalhe for p in r.passos]
    assert r.pronto
    op = r.passos[-1]
    assert op.dados["valores"]["LeadTimeMedio"] == pytest.approx(60.1)
    assert op.dados["batimento"]["mudou"] is True
    assert "urn:teste:elo" in op.detalhe


def test_lado_local_fora_para_antes_da_rede():
    fechada = porta_livre()
    with ServidorFicticio() as s:
        r = dg.diagnosticar("127.0.0.1", s.porta, local_porta=fechada, timeout=1, intervalo_s=0.3)
    assert status(r) == ["FALHOU", "PULADO", "PULADO", "PULADO"]
    assert "corrija antes da rede" in r.passos[0].detalhe
    assert not r.pronto


def test_porta_fechada_falha_na_porta_e_pula_opcua():
    r = dg.diagnosticar("127.0.0.1", porta_livre(), local_porta=None, timeout=1)
    assert status(r) == ["PULADO", "OK", "FALHOU", "PULADO"]
    assert "ninguém escutando" in r.passos[2].detalhe
    assert not r.pronto


def test_batimento_parado_vira_aviso_e_nao_pronto():
    with ServidorFicticio(vivo=False) as s:
        r = dg.diagnosticar("127.0.0.1", s.porta, local_porta=None, timeout=2, intervalo_s=0.5)
    assert status(r)[-1] == "AVISO"
    assert "congelado" in r.passos[-1].detalhe
    assert not r.pronto     # último passo precisa ser OK


def test_no_do_contrato_ausente_falha_com_o_nome():
    nos = {"RitmoReal": (VT.Double, 1.0), "Batimento": (VT.UInt32, 0)}
    with ServidorFicticio(nos=nos) as s:
        r = dg.diagnosticar("127.0.0.1", s.porta, local_porta=None, timeout=2, intervalo_s=0.3)
    assert status(r)[-1] == "FALHOU"
    assert "LeadTimeMedio" in r.passos[-1].detalhe and "StatusLinha" in r.passos[-1].detalhe


def test_elo_usa_nodeids_de_config_cadeia():
    nos = dg.nos_do_contrato("Distribuicao")
    assert nos["FilaDistribuicao"] == "ns=2;s=EstadoGemeo.FilaDistribuicao"
    assert set(dg.COMUNS) <= set(nos)
    assert "EstoqueFornecedor" in dg.nos_do_contrato("fornecedor")
    with pytest.raises(SystemExit):
        dg.nos_do_contrato("Inexistente")


def test_linha_de_comando_codigo_de_saida(capsys):
    with ServidorFicticio() as s:
        assert dg.main(["--host", "127.0.0.1", "--porta", str(s.porta), "--sem-local", "--intervalo", "0.4"]) == 0
    assert "conexão PRONTA" in capsys.readouterr().out
    assert dg.main(["--host", "127.0.0.1", "--porta", str(porta_livre()), "--sem-local", "--timeout", "1",
                    "--json"]) == 1
    assert '"pronto": false' in capsys.readouterr().out


def test_url_com_caminho():
    assert dg.url_opcua("10.0.0.5", 4840, "freeopcua/server/") == "opc.tcp://10.0.0.5:4840/freeopcua/server/"
    assert dg.url_opcua("h", 4852) == "opc.tcp://h:4852"
