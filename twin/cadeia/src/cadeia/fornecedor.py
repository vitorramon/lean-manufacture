"""Elo Fornecedor EMULADO (tarefa 3.3): `python -m cadeia.fornecedor [--estoque N] [--estoque-forcado N]`.

Servidor `opc.tcp://0.0.0.0:4852`, namespace 2 = `urn:lean-manufacture:grupo7:emulado:fornecedor`,
`ns=2;s=EstadoGemeo.EstoqueFornecedor` etc. (contrato de interface, docs/convencoes-fase-3.md §2). Comportamento em
`cadeia.modelos.ModeloFornecedor`; parâmetros em `config/cadeia.yaml` → `emulados.Fornecedor` (emulação, não
medição). SIGUSR2 força o estoque para `--estoque-forcado` (exercita RISCO_FALTA na Produção, RF-A3-09).
"""

from __future__ import annotations

from asyncua import ua

from cadeia.execucao import argumentos, log, principal
from cadeia.modelos import ModeloFornecedor

NOME = "Fornecedor"
NAMESPACE_URI = "urn:lean-manufacture:grupo7:emulado:fornecedor"
VT = ua.VariantType
PROPRIAS = {
    "EstoqueFornecedor": (VT.Double, 0.0, "unidades", "Kits de componentes disponíveis para a Produção"),
    "PedidoEmAberto": (VT.Boolean, False, "-", "Reposição pedida e ainda não entregue"),
    "PecasConsumidas": (VT.UInt32, 0, "peças", "Peças da Produção que consumiram estoque desde o início"),
}


def construir(cadeia, p, args) -> ModeloFornecedor:
    if args.estoque is not None:
        p = {**p, "estoque_inicial": args.estoque}
    return ModeloFornecedor(p, janela_s=cadeia.t2t.janela_ritmo_s)


def comando(modelo: ModeloFornecedor, cmd: str, args) -> None:
    if cmd == "SIGUSR2":
        log.warning("modo de falha: estoque forçado para %g", args.estoque_forcado)
        modelo.forcar_estoque(args.estoque_forcado)


def main() -> None:
    ap = argumentos(__doc__.splitlines()[0])
    ap.add_argument("--estoque", type=float, help="estoque inicial (sobrepõe emulados.Fornecedor.estoque_inicial)")
    ap.add_argument("--estoque-forcado", type=float, default=5.0, help="valor aplicado no SIGUSR2 (padrão 5)")
    principal(NOME, construir, PROPRIAS, NAMESPACE_URI, ap, comando)


if __name__ == "__main__":
    main()
