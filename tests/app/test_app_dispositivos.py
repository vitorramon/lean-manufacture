"""Página "Dispositivos" (tarefa 2.7): online, última atividade, rejeições por categoria, duplicatas e lacunas.

Lacunas vêm do AAS (submodelo DadosOperacionais escrito pelo aas-sync); aqui um servidor HTTP local de teste faz o
papel do BaSyx (sem rede externa).
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from conftest import s
from nucleo.aas_leitura import _b64url, contadores_gateway, id_submodelo
from nucleo.configuracao import Configuracao
from nucleo.dados import Dados
from nucleo.painel import estado_dispositivo, estado_posto
from nucleo.regras import Nivel

SUBMODELO = {"submodelElements": [{"idShort": "Lacunas", "value": "3"}, {"idShort": "Duplicatas", "value": "1"},
                                  {"idShort": "Rejeitados"}]}


@pytest.fixture
def aas():
    caminho = f"/submodels/{_b64url(id_submodelo('esp32-bat01'))}"

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            ok = self.path == caminho
            corpo = json.dumps(SUBMODELO if ok else {"erro": "não achado"}).encode()
            self.send_response(200 if ok else 404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(corpo)

        def log_message(self, *_):
            return None

    srv = HTTPServer(("127.0.0.1", 0), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_contadores_do_aas(aas):
    assert contadores_gateway(aas, "esp32-bat01") == {"Lacunas": 3, "Duplicatas": 1, "Rejeitados": None}
    assert contadores_gateway(aas, "qr-entrada") is None        # submodelo inexistente (404)
    assert contadores_gateway("http://127.0.0.1:9", "esp32-bat01", timeout=0.5) is None   # AAS fora do ar


def test_estado_dispositivo(banco, dispositivos, aas):
    caminho, esc = banco
    esc.sessao("emulador:godot", 0, disp="esp32-bat01")
    esc.sessao("emulador:godot", 0, disp="qr-entrada")
    esc.leitura(5, "LinhaCelulares.Bateria_01.Temperatura", 24.0)
    esc.evento(8, "P0001", "Bateria", "entrada")
    esc.rejeitado(6, 1, categoria="faixa")
    esc.rejeitado(7, 2, categoria="sequencia")
    esc.rejeitado(9, 3, categoria="sequencia")
    with Dados(caminho, dispositivos, aas_url=aas) as d:
        e = estado_dispositivo(d, "esp32-bat01", agora=s(10))
        assert (e.online, e.origem, e.ultima_atividade, e.idade_s) == (True, "emulador:godot", s(5), 5.0)
        assert e.rejeicoes == {"faixa": 1, "sequencia": 2} and e.rejeitados == 3 and e.duplicatas == 2
        assert e.lacunas == 3
        assert [r.ts for r in e.ultimas_rejeicoes] == [s(9), s(7), s(6)]
        q = estado_dispositivo(d, "qr-entrada", agora=s(10))
        assert (q.ultima_atividade, q.ultimo_evento, q.ultimas) == (s(8), s(8), {})
        assert q.contadores is None and q.lacunas is None          # AAS sem o submodelo: "sem dado", não zero
        saida = estado_dispositivo(d, "qr-saida", agora=s(10))
        assert (saida.online, saida.ultima_atividade) == (False, None)
    with Dados(caminho, dispositivos) as d:                         # sem AAS_URL
        assert d.lacunas("esp32-bat01") is None


def test_leitor_de_qr_nao_fica_sempre_cinza_na_visao_geral(banco, dispositivos):
    caminho, esc = banco
    esc.sessao("emulador:godot", 0, disp="qr-entrada")
    esc.evento(8, "P0001", "Bateria", "entrada")
    conf = Configuracao(caminho, None, 3.0, 60.0, 2.0)
    with Dados(caminho, dispositivos) as d:
        assert estado_posto(d, "qr-entrada", conf, agora=s(10)).andon.nivel is Nivel.VERDE
        assert estado_posto(d, "qr-entrada", conf, agora=s(100)).andon.nivel is Nivel.CINZA   # prazo 60 s


def test_aas_fora_do_ar_nao_bloqueia_cada_atualizacao(monkeypatch, aas):
    """Achado 9 da revisão (RNF-02): depois de uma falha de conexão, as consultas ao mesmo AAS são puladas por
    PAUSA_APOS_FALHA_S, sem esperar o timeout de novo para cada dispositivo."""
    import time
    import urllib.request

    from nucleo import aas_leitura

    monkeypatch.setattr(aas_leitura, "_falhou_em", {})
    chamadas = {"n": 0}
    original = urllib.request.urlopen

    def contar(*a, **kw):
        chamadas["n"] += 1
        return original(*a, **kw)

    monkeypatch.setattr(aas_leitura.urllib.request, "urlopen", contar)
    fora = "http://127.0.0.1:9"
    assert contadores_gateway(fora, "esp32-bat01", timeout=0.5) is None
    t0 = time.monotonic()
    assert all(contadores_gateway(fora, d, timeout=0.5) is None
               for d in ("esp32-bat01", "qr-entrada", "qr-teste", "qr-saida"))
    assert chamadas["n"] == 1 and time.monotonic() - t0 < 0.05
    # 404 é resposta do AAS, não falha de conexão: não pausa as consultas seguintes
    assert contadores_gateway(aas, "qr-entrada") is None
    assert contadores_gateway(aas, "esp32-bat01")["Lacunas"] == 3
    # passada a pausa, tenta de novo
    monkeypatch.setattr(aas_leitura, "PAUSA_APOS_FALHA_S", 0.0)
    assert contadores_gateway(fora, "esp32-bat01", timeout=0.5) is None
    assert chamadas["n"] == 4
