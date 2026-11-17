"""Elo Distribuição EMULADO (tarefa 3.3, RF-A3-02): `python -m cadeia.distribuicao`.

Servidor `opc.tcp://0.0.0.0:4853`, namespace 2 = `urn:lean-manufacture:grupo7:emulado:distribuicao`,
`ns=2;s=EstadoGemeo.FilaDistribuicao` etc. (contrato de interface, docs/convencoes-fase-3.md §2). Consome
`RitmoProducao`, `StatusLinha` e `UltimaPeca` do nosso twin-t2t (:4851) e reage: Produção OFFLINE/PARADA/SEM_DADOS ou
ritmo < `ritmo_minimo_producao` → `AGUARDANDO_PRODUCAO`, com linha "REAÇÃO" no log. Parâmetros em
`config/cadeia.yaml` → `emulados.Distribuicao` (emulação, não medição).
"""

from __future__ import annotations

from asyncua import ua

from cadeia.execucao import argumentos, principal
from cadeia.modelos import ModeloDistribuicao

NOME = "Distribuicao"
NAMESPACE_URI = "urn:lean-manufacture:grupo7:emulado:distribuicao"
VT = ua.VariantType
PROPRIAS = {
    "FilaDistribuicao": (VT.Double, 0.0, "unidades", "Peças recebidas e ainda não despachadas"),
    "PecasRecebidas": (VT.UInt32, 0, "peças", "Peças recebidas da Produção desde o início"),
    "Reacoes": (VT.UInt32, 0, "-", "Vezes que entrou em AGUARDANDO_PRODUCAO (RF-A3-02)"),
}


def construir(cadeia, p, args) -> ModeloDistribuicao:
    return ModeloDistribuicao(p, janela_s=cadeia.t2t.janela_ritmo_s)


def main() -> None:
    principal(NOME, construir, PROPRIAS, NAMESPACE_URI, argumentos(__doc__.splitlines()[0]))


if __name__ == "__main__":
    main()
