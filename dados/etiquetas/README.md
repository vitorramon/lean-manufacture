# Etiquetas de peça (RF-A2-04, ADR-0008 item 7)

Geradas pelo script versionado `hardware/emulador/src/emulador/etiquetas.py` (tarefa 2.2, 2026-11-16):

```bash
uv run --project hardware/emulador python -m emulador.etiquetas            # P0001..P0030 aqui
uv run --project hardware/emulador python -m emulador.etiquetas --de 31 --ate 60
```

| Arquivo | Conteúdo |
| --- | --- |
| `P0001.png` … `P0030.png` | Uma etiqueta por peça, 300 dpi: QR com o ID curto (só `P0001`, nada mais) e o ID legível embaixo |
| `etiquetas-P0001-P0030.pdf` | Folha A4 com as 30 etiquetas em tamanho real e linhas de corte |
| `manifesto.csv` | ID, conteúdo do QR, arquivo, lado do símbolo QR (2,31 cm), lado com zona de silêncio (3,19 cm) e se a leitura de volta conferiu |

- **Tamanho:** símbolo QR de 2,31 cm (mínimo da aula: 2×2 cm), mais a zona de silêncio branca exigida pela norma.
  Imprima em **100 % / tamanho real**, sem "ajustar à página".
- **Correção de erro** nível Q (até ~25 % do símbolo danificado).
- **Conteúdo** = ID curto `P` + 4 dígitos: é a regra `id-curto` de `config/rastreio.yaml`. O gateway normaliza o QR
  bruto para o ID da peça (tarefa 2.3); o leitor só publica o que leu.
- **Conferência:** o script decodifica cada PNG com o mesmo decodificador do modo câmera
  (`emulador.fontes.camera.decodificar`) e falha se alguma etiqueta não devolver o próprio ID. Nas 30: 30 conferidas.
- **Uso físico** (aula M3.A2): material resistente (papel adesivo plastificado ou etiqueta de poliéster), sempre na
  mesma posição da peça, voltada para a câmera. Nada disso foi testado com câmera real: ver
  `hardware/emulador/README.md`, Limitações.
