# ADR-0015: Ferramentas do ambiente instaladas em espaço de usuário, com checksum conferido

- Estado: Proposto
- Data: 2026-11-15
- Origem: tarefa 0.2 da Fase 0 (pedido do usuário "instalar true"); regra do trabalho "sem sudo nem apt"

## Contexto

O ambiente (WSL2, Python 3.14 do sistema) não tinha `uv`, Python 3.12, Godot 4.7.2, cliente MQTT, navegador OPC UA
nem git-lfs. O Virtual-Factory pede Python 3.12 e Godot 4.7.2. O assistente não pode usar `sudo` nem `apt`.

## Decisão

1. **uv** 0.13.8 a partir do tarball oficial do release, com sha256 conferido, em `~/.local/bin` (não pelo
   `install.sh`, para poder conferir o checksum).
2. **Python 3.12** via `uv python install 3.12` (CPython 3.12.16); nada no Python do sistema.
3. **Godot 4.7.2 stable** do release oficial, sha512 conferido com `SHA512-SUMS.txt`, em
   `~/.local/opt/godot/Godot_v4.7.2-stable_linux.x86_64`, com link `~/.local/bin/godot`. Uso sem janela
   (`--headless`); opcionalmente `GODOT_PATH` aponta para o binário.
4. **Cliente MQTT**: `uv tool install amqtt` (0.12.2; `amqtt_sub`, `amqtt_pub`) em vez do `mosquitto-clients`.
5. **Navegador OPC UA**: `uvx --python 3.12 --from asyncua uals` (efêmero); UaExpert no Windows é opcional.
6. **git-lfs**: pacote do sistema (`sudo apt install git-lfs`) feito pelo usuário, ou binário oficial com sha256
   conferido em `~/.local/bin`, com autorização. Ainda não instalado de forma permanente.
7. Ferramenta de build do ESP32: decidir em ADR próprio antes da tarefa 1.7.

## Consequências

- Nada exige root; o ambiente pode ser refeito por um script de usuário (útil no teste do terceiro).
- Versões exatas e checksums ficam registrados em `docs/evidencias/f0-0.2-ambiente.md`.
- `~/.local/bin` precisa estar no PATH.
- Enquanto o git-lfs não estiver no PATH, o submódulo `base/` fica frágil (ADR-0014).
- O OPC UA só foi verificado com `uals --help`, sem sessão real contra a 4840.

## Alternativas consideradas

- **apt/sudo para tudo**: mais simples, mas fora do que o assistente pode fazer e sem garantia da versão exata
  pedida pela base (Godot 4.7.2).
- **Flatpak/Snap do Godot**: não avaliado; o binário oficial com checksum atende sem dependências extras.
- **mosquitto-clients**: exige apt; o amqtt cobre a assinatura de teste.
