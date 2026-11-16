"""Gera o cabeçalho com as mensagens de referência do contrato dev/v1 para os testes nativos.

Script `pre:` do PlatformIO (ambiente `native`). Lê pipeline/contrato/exemplos/validos/*.json e escreve
`<build>/gerado/referencias_contrato.h` com o tópico e o payload em JSON compacto (separadores sem espaço,
ordem das chaves preservada), que é a forma que o firmware publica. Assim os testes da lógica usam os mesmos
arquivos que validam o emulador Python e o gateway, sem cópia à mão.
"""

import json
import os
from pathlib import Path

Import("env")  # noqa: F821  (injetado pelo SCons do PlatformIO)

projeto = Path(env.subst("$PROJECT_DIR"))  # noqa: F821
exemplos = (projeto / ".." / ".." / "pipeline" / "contrato" / "exemplos" / "validos").resolve()
destino_dir = Path(env.subst("$PROJECT_BUILD_DIR")) / "gerado"  # noqa: F821
destino = destino_dir / "referencias_contrato.h"

if not exemplos.is_dir():
    raise SystemExit(f"mensagens de referência não encontradas em {exemplos}")

linhas = [
    "// GERADO por scripts/gerar_referencias.py a partir de pipeline/contrato/exemplos/validos. Não editar.",
    "#pragma once",
    "",
    "struct ReferenciaContrato {",
    "    const char* nome;",
    "    const char* topico;",
    "    const char* payload;  // JSON compacto, ordem das chaves do arquivo",
    "};",
    "",
    "static const ReferenciaContrato REFERENCIAS[] = {",
]
total = 0
for arquivo in sorted(exemplos.glob("*.json")):
    dados = json.loads(arquivo.read_text(encoding="utf-8"))
    if "payload" not in dados:
        continue
    compacto = json.dumps(dados["payload"], separators=(",", ":"), ensure_ascii=False)
    linhas.append(f'    {{"{arquivo.stem}", "{dados["topico"]}", R"json({compacto})json"}},')
    total += 1
linhas += [
    "};",
    "",
    f"static const unsigned N_REFERENCIAS = {total};",
    "",
]

destino_dir.mkdir(parents=True, exist_ok=True)
conteudo = "\n".join(linhas)
if not destino.exists() or destino.read_text(encoding="utf-8") != conteudo:
    destino.write_text(conteudo, encoding="utf-8")
print(f"gerar_referencias: {total} mensagens de referência de {os.path.relpath(exemplos, projeto)}")

env.Append(CPPPATH=[str(destino_dir)])  # noqa: F821
