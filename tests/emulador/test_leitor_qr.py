"""Leitor de QR na L0 (tarefa 2.2; RF-A2-04, RF-A2-05; ADR-0008, ADR-0026): scan com QR bruto, fonte godot com o
GS1 Digital Link da plaqueta e o resultado do teste, roteiro com vários dispositivos, modo câmera por arquivo e
etiquetas. Sem rede: o publicador é em memória. Dados de TESTE, nunca medição (ADR-0013).

A deduplicação NÃO é do leitor (é do gateway, tarefa 2.3): aqui se verifica que as repetições SAEM.
"""

from __future__ import annotations

import json
import re
import threading
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
import pytest
import yaml
from conftest import CONFIG_TESTE, RAIZ, PublicadorMemoria
from contrato import carregar_dispositivos, validar
from emulador.dispositivo import Dispositivo, ErroContrato
from emulador.etiquetas import MINIMO_QR_CM, etiqueta, gerar, id_peca
from emulador.fontes.camera import (
    CameraIndisponivel,
    decodificar,
    executar_arquivos,
    executar_camera,
    ponto_do_leitor,
)
from emulador.fontes.godot import Acionamento, aplicar, qr_da_peca, traduzir
from emulador.fontes.roteiro import RoteiroInvalido, carregar_roteiro, executar_roteiro
from emulador.relogio import RelogioReal, RelogioVirtual

PREFIXO = "vf/plant01/final-assembly/line01"
ROTEIRO_TRECHO = RAIZ / "hardware" / "emulador" / "roteiros" / "trecho-qr-demo.yaml"
RASTREIO = RAIZ / "config" / "rastreio.yaml"
SERIAL = "PC3280-2026-000004"
DL = f"https://virtual-factory.example/01/04099999032808/21/{SERIAL}"


@pytest.fixture(scope="module")
def cfgs() -> dict:
    return carregar_dispositivos(RAIZ / "config" / "dispositivos.yaml")


@pytest.fixture(scope="module")
def cfg_teste_emu() -> dict:
    return carregar_dispositivos(CONFIG_TESTE)["teste-emu01"]


def _disp(cfg: dict, pub: PublicadorMemoria, relogio=None, origem: str = "emulador:teste") -> Dispositivo:
    return Dispositivo(cfg, 1, relogio or RelogioVirtual(velocidade=1e9), pub, origem)


def _scans(pub: PublicadorMemoria) -> list[tuple[str, dict]]:
    return [(t, json.loads(p)) for t, p, _, _ in pub.msgs if t.endswith("/evt/scan")]


def _regras_normalizacao() -> list[re.Pattern]:
    return [re.compile(r["padrao"]) for r in yaml.safe_load(RASTREIO.read_text(encoding="utf-8"))["normalizacao"]]


def _peca(qr: str) -> str | None:
    """Mesma ordem de regras que o gateway usará (config/rastreio.yaml). Só para conferir o formato aqui."""
    for r in _regras_normalizacao():
        if m := r.match(qr):
            return m.group("peca")
    return None


# --- scan no dispositivo -------------------------------------------------------------------------------------
def test_scan_do_leitor_real_valido_qos1_nao_retido(cfgs):
    pub = PublicadorMemoria()
    d = _disp(cfgs["qr-entrada"], pub)
    d.scan("P0042", "entrada")
    d.scan(DL, "entrada")
    assert [(t, q, r) for t, _, q, r in pub.msgs] == [("dev/v1/qr-entrada/evt/scan", 1, False)] * 2
    assert all(validar(t, p) for t, p, _, _ in pub.msgs)
    assert [json.loads(p)["seq"] for _, p, _, _ in pub.msgs] == [0, 1]
    with pytest.raises(ValueError, match="não declarado"):
        d.scan("P0042", "saida")  # qr-entrada só declara o ponto entrada


def test_resultado_so_no_ponto_teste(cfg_teste_emu):
    pub = PublicadorMemoria()
    d = _disp(cfg_teste_emu, pub)
    assert d.scan("P0001", "teste", 1)["resultado"] == 1
    assert d.scan("P0002", "teste", 0)["resultado"] == 0
    assert "resultado" not in d.scan("P0003", "teste")
    with pytest.raises(ErroContrato):
        d.scan("P0004", "entrada", 1)  # o contrato (ADR-0026) recusa resultado fora do teste


# --- fonte godot: QR da plaqueta e resultado -----------------------------------------------------------------
def test_qr_da_peca_e_o_digital_link_da_base():
    assert qr_da_peca(SERIAL) == DL
    assert qr_da_peca(SERIAL, "http://outro.dominio/", "00000000000017") == (
        f"http://outro.dominio/01/00000000000017/21/{SERIAL}")
    assert _peca(DL) == SERIAL  # a regra gs1-digital-link do gateway recupera o serial


@pytest.mark.parametrize("result, esperado", [(1, 1), (2, 0), (3, None), (None, None), (True, None), ("1", None)])
def test_resultado_da_inspecao(cfg_teste_emu, result, esperado):
    p = {"serial": SERIAL} | ({} if result is None else {"result": result})
    acoes = traduzir(f"{PREFIXO}/plc01/event/part_inspected", p, cfg_teste_emu, PREFIXO)
    assert acoes == [Acionamento("scan", DL, "teste", esperado)]
    pub = PublicadorMemoria()
    aplicar(acoes, _disp(cfg_teste_emu, pub))
    (t, dados), = _scans(pub)
    assert validar(t, json.dumps(dados))
    assert dados.get("resultado") == esperado


def test_godot_nos_leitores_reais(cfgs):
    """qr-entrada lê na liberação da AC01, qr-saida na separação; nenhum dos dois marca ciclo."""
    p = {"serial": SERIAL, "result": 1}
    ev = {n: f"{PREFIXO}/{c}/event/{n}" for c, n in
          [("ac01", "part_released"), ("plc01", "part_inspected"), ("plc01", "part_sorted")]}
    ent, sai, bat = cfgs["qr-entrada"], cfgs["qr-saida"], cfgs["esp32-bat01"]
    assert traduzir(ev["part_released"], p, ent, PREFIXO) == [Acionamento("scan", DL, "entrada")]
    assert traduzir(ev["part_inspected"], p, ent, PREFIXO) == []
    assert traduzir(ev["part_sorted"], p, ent, PREFIXO) == []
    assert traduzir(ev["part_sorted"], p, sai, PREFIXO) == [Acionamento("scan", DL, "saida")]
    assert traduzir(ev["part_released"], p, sai, PREFIXO) == []
    assert traduzir(ev["part_released"], p, bat, PREFIXO) == [Acionamento("ciclo")]


def test_amostra_real_da_planta_vira_scans_validos(cfgs):
    """Eventos gravados da planta virtual na Fase 0 (f0-0.4-eventos-planta-lfs.jsonl: 14/13/12) -> scans dos dois leitores."""
    amostra = RAIZ / "dados" / "amostras" / "f0-0.4-eventos-planta-lfs.jsonl"
    linhas = [json.loads(x) for x in amostra.read_text(encoding="utf-8").splitlines() if x.strip()]
    eventos = [x for x in linhas if "/event/" in x.get("topic", "")]
    pubs = {i: PublicadorMemoria() for i in ("qr-entrada", "qr-saida")}
    for i, pub in pubs.items():
        d = _disp(cfgs[i], pub, origem="emulador:godot")
        for ev in eventos:
            aplicar(traduzir(ev["topic"], ev["payload"], cfgs[i], PREFIXO), d)
    liberadas = [e["payload"]["serial"] for e in eventos if e["topic"].endswith("part_released")]
    separadas = [e["payload"]["serial"] for e in eventos if e["topic"].endswith("part_sorted")]
    ent, sai = _scans(pubs["qr-entrada"]), _scans(pubs["qr-saida"])
    assert [_peca(d["qr"]) for _, d in ent] == liberadas
    assert [_peca(d["qr"]) for _, d in sai] == separadas
    assert all(validar(t, json.dumps(d)) for t, d in ent + sai)


# --- fonte roteiro com vários dispositivos ---------------------------------------------------------------------
def test_roteiro_do_trecho_com_tres_dispositivos(cfgs):
    ids = ["qr-entrada", "esp32-bat01", "qr-saida"]
    roteiro = carregar_roteiro(ROTEIRO_TRECHO, ids)
    rel = RelogioVirtual(velocidade=1e9)
    pubs = {i: PublicadorMemoria() for i in ids}
    disps = [Dispositivo(cfgs[i], 1, rel, pubs[i], "emulador:roteiro") for i in ids]
    assert executar_roteiro(roteiro, disps, rel, threading.Event())
    for i, pub in pubs.items():
        assert all(validar(t, p) for t, p, _, _ in pub.msgs), i
        seqs = [json.loads(p)["seq"] for _, p, _, _ in pub.msgs]
        assert seqs == list(range(len(seqs))), i  # seq próprio por dispositivo
        assert all(t.startswith(f"dev/v1/{i}/") for t, *_ in pub.msgs)
    ent = Counter(d["qr"] for _, d in _scans(pubs["qr-entrada"]))
    sai = Counter(d["qr"] for _, d in _scans(pubs["qr-saida"]))
    # O leitor publica TODAS as leituras, inclusive as repetidas (deduplicação é do gateway).
    assert sum(ent.values()) == 12 and ent["P0002"] == 3
    assert sum(sai.values()) == 11 and sai["P0005"] == 2 and sai["P0008"] == 2
    assert set(ent) - set(sai) == {"P0007"}  # peça esquecida: entra e nunca sai
    assert set(ent) == {id_peca(n) for n in range(1, 11)}
    ciclos = [json.loads(p) for t, p, _, _ in pubs["esp32-bat01"].msgs if t.endswith("/evt/ciclo")]
    assert [c["dur_s"] for c in ciclos if c["fase"] == "fim"] == [
        27.4, 26.8, 27.9, 26.5, 28.3, 27.1, 26.9, 27.6, 27.2, 26.7]
    assert not [t for t, *_ in pubs["qr-entrada"].msgs if "/tel/" in t]  # telemetria só em quem declara o canal
    assert [t for t, *_ in pubs["esp32-bat01"].msgs if "/tel/" in t]


def test_roteiro_do_trecho_com_posto_teste(cfgs):
    """Tarefas 2.8/2.10: o roteiro padrão do start.py tem o qr-teste com `resultado` e a mesma linha do tempo."""
    ids = ["qr-entrada", "esp32-bat01", "qr-teste", "qr-saida"]
    roteiro = carregar_roteiro(ROTEIRO_TRECHO.with_name("trecho-qr-teste-demo.yaml"), ids)
    assert roteiro.fim_ms == carregar_roteiro(ROTEIRO_TRECHO, ["qr-entrada", "esp32-bat01", "qr-saida"]).fim_ms
    rel = RelogioVirtual(velocidade=1e9)
    pubs = {i: PublicadorMemoria() for i in ids}
    disps = [Dispositivo(cfgs[i], 1, rel, pubs[i], "emulador:roteiro") for i in ids]
    assert executar_roteiro(roteiro, disps, rel, threading.Event())
    assert all(validar(t, p) for pub in pubs.values() for t, p, _, _ in pub.msgs)
    teste = [d for _, d in _scans(pubs["qr-teste"])]
    assert all(d["ponto"] == "teste" for d in teste) and len(teste) == 10   # P0006 lida 2 vezes
    primeiro = {}
    for d in teste:
        primeiro.setdefault(d["qr"], d["resultado"])
    assert len(primeiro) == 9 and "P0007" not in primeiro
    assert [p for p, r in primeiro.items() if r == 0] == ["P0004"]   # 8 aprovadas, 1 reprovada


@pytest.mark.parametrize(
    "conteudo, ids, trecho",
    [
        ("dispositivos: [a, b]\npassos: [{apos_s: 1, scan: P0001, ponto: entrada}]", ["a", "b"], "'dispositivo'"),
        ("dispositivos: [a, b]\npassos: []", ["a"], "passe todos"),
        ("passos: [{dispositivo: c, scan: P0001, ponto: entrada}]", ["a", "b"], "'dispositivo'"),
        ("dispositivo: a\npassos: []", ["a", "b"], "não de"),
        ("passos: [{scan: P0001, ponto: teste, resultado: 2}]", ["a"], "resultado"),
        ("passos: [{scan: P0001, ponto: teste, resultado: true}]", ["a"], "resultado"),
    ],
)
def test_roteiro_multi_invalido(tmp_path, conteudo, ids, trecho):
    arq = tmp_path / "r.yaml"
    arq.write_text(conteudo, encoding="utf-8")
    with pytest.raises(RoteiroInvalido, match=trecho):
        carregar_roteiro(arq, ids)


# --- fonte camera (modo arquivo) -----------------------------------------------------------------------------
@pytest.fixture(scope="module")
def pasta_etiquetas(tmp_path_factory) -> Path:
    pasta = tmp_path_factory.mktemp("etiquetas")
    gerar(pasta, 1, 3)
    return pasta


def _png(caminho: Path, img) -> Path:
    cv2.imwrite(str(caminho), np.array(img))
    return caminho


def test_modo_arquivo_publica_cada_quadro_sem_deduplicar(cfgs, pasta_etiquetas):
    pub = PublicadorMemoria()
    d = _disp(cfgs["qr-entrada"], pub, RelogioReal())
    c = executar_arquivos(d, None, [pasta_etiquetas], threading.Event(), leituras_por_imagem=3, intervalo_ms=0)
    assert c["scans"] == 9 and c["sem_qr"] == 0 and c["fora_do_contrato"] == 0
    assert [dados["qr"] for _, dados in _scans(pub)] == ["P0001"] * 3 + ["P0002"] * 3 + ["P0003"] * 3
    assert {dados["ponto"] for _, dados in _scans(pub)} == {"entrada"}
    assert all(validar(t, p) for t, p, _, _ in pub.msgs)


def test_modo_arquivo_quadro_sem_qr_com_dois_qr_e_qr_fora_do_contrato(cfgs, pasta_etiquetas, tmp_path):
    branco = _png(tmp_path / "a-branco.png", np.full((300, 300), 255, np.uint8))
    e1 = cv2.imread(str(pasta_etiquetas / "P0001.png"), cv2.IMREAD_GRAYSCALE)
    e2 = cv2.imread(str(pasta_etiquetas / "P0002.png"), cv2.IMREAD_GRAYSCALE)
    duas = _png(tmp_path / "b-duas.png", np.hstack([e1, np.full((e1.shape[0], 80), 255, np.uint8), e2]))
    import qrcode

    estranho = _png(tmp_path / "c-estranho.png", qrcode.make(" P0001 ").get_image().convert("L"))
    pub = PublicadorMemoria()
    d = _disp(cfgs["qr-saida"], pub, RelogioReal())
    c = executar_arquivos(d, "saida", [branco, duas, estranho], threading.Event(), intervalo_ms=0)
    assert c == {"quadros": 3, "scans": 2, "sem_qr": 1, "fora_do_contrato": 1, "ilegiveis": 0}
    assert sorted(dados["qr"] for _, dados in _scans(pub)) == ["P0001", "P0002"]


def test_ponto_do_leitor(cfgs, cfg_teste_emu):
    pub = PublicadorMemoria()
    assert ponto_do_leitor(_disp(cfgs["qr-saida"], pub), None) == "saida"
    with pytest.raises(ValueError, match="--ponto"):
        ponto_do_leitor(_disp(cfg_teste_emu, pub), None)  # três pontos: precisa escolher
    with pytest.raises(ValueError, match="não declarado"):
        ponto_do_leitor(_disp(cfgs["qr-saida"], pub), "entrada")
    with pytest.raises(ValueError, match="não declara"):
        ponto_do_leitor(_disp(cfgs["esp32-bat01"], pub), None)


def test_camera_inexistente_falha_com_mensagem(cfgs):
    d = _disp(cfgs["qr-entrada"], PublicadorMemoria(), RelogioReal())
    with pytest.raises(CameraIndisponivel, match="--imagens"):
        executar_camera(d, None, 97, threading.Event())


# --- etiquetas -----------------------------------------------------------------------------------------------
def test_etiquetas_legiveis_no_tamanho_minimo_e_no_formato_do_gateway(pasta_etiquetas):
    linhas = (pasta_etiquetas / "manifesto.csv").read_text(encoding="utf-8").splitlines()
    assert len(linhas) == 4  # cabeçalho + P0001..P0003
    for n in (1, 2, 3):
        peca = id_peca(n)
        img = cv2.imread(str(pasta_etiquetas / f"{peca}.png"), cv2.IMREAD_GRAYSCALE)
        assert decodificar(img) == [peca]
        assert _peca(peca) == peca  # regra id-curto de config/rastreio.yaml
    from PIL import Image

    im = Image.open(pasta_etiquetas / "P0001.png")
    assert round(im.info["dpi"][0]) == 300
    simbolo_cm = float(linhas[1].split(",")[3])
    assert simbolo_cm >= MINIMO_QR_CM
    pdf = (pasta_etiquetas / "etiquetas-P0001-P0003.pdf").read_bytes()
    assert re.search(rb"MediaBox \[ 0 0 595\.\d+ 841\.\d+ \]", pdf)  # A4 em tamanho real (pt)


def test_etiqueta_recusa_tamanho_ou_id_fora_da_regra():
    with pytest.raises(ValueError, match="mínimo"):
        etiqueta("P0001", 1.5)
    with pytest.raises(ValueError, match="padrão"):
        etiqueta("X0001", 2.2)
    for n in (0, 10000):
        with pytest.raises(ValueError):
            id_peca(n)


def test_quadro_degradado_como_de_camera(pasta_etiquetas):
    """Quadro sintético que imita a câmera: etiqueta a 35 % do tamanho, girada 12°, desfocada, com menos contraste e
    ruído. Não substitui o teste com webcam (não há câmera no WSL2), só mostra folga do decodificador."""
    rng = np.random.default_rng(42)
    for n in (1, 2, 3):
        e = cv2.imread(str(pasta_etiquetas / f"{id_peca(n)}.png"), cv2.IMREAD_GRAYSCALE)
        grande = cv2.copyMakeBorder(e, 150, 150, 150, 150, cv2.BORDER_CONSTANT, value=255)
        h, w = grande.shape
        q = cv2.warpAffine(grande, cv2.getRotationMatrix2D((w / 2, h / 2), 12, 0.35), (w, h), borderValue=255)
        q = cv2.GaussianBlur(q, (3, 3), 0)
        q = np.clip(q.astype(float) * 0.8 + 30 + rng.normal(0, 8, q.shape), 0, 255).astype(np.uint8)
        assert decodificar(q) == [id_peca(n)]


def test_resultado_da_amostra_real_da_planta(cfg_teste_emu):
    """part_inspected gravados da planta (f0-0.4): result 1/2 vira resultado 1/0 no scan teste, um a um."""
    amostra = RAIZ / "dados" / "amostras" / "f0-0.4-eventos-planta-lfs.jsonl"
    linhas = [json.loads(x) for x in amostra.read_text(encoding="utf-8").splitlines() if x.strip()]
    insp = [x for x in linhas if x.get("topic", "").endswith("plc01/event/part_inspected")]
    pub = PublicadorMemoria()
    d = _disp(cfg_teste_emu, pub, origem="emulador:godot")
    for ev in insp:
        aplicar(traduzir(ev["topic"], ev["payload"], cfg_teste_emu, PREFIXO), d)
    scans = _scans(pub)
    assert len(scans) == len(insp) == 13
    assert [s["resultado"] for _, s in scans] == [{1: 1, 2: 0}[e["payload"]["result"]] for e in insp]
    assert [_peca(s["qr"]) for _, s in scans] == [e["payload"]["serial"] for e in insp]
