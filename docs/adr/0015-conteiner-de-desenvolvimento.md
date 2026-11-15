# ADR-0015: Ferramentas de desenvolvimento num contêiner de desenvolvimento

- Estado: Aceito (grupo, 2026-11-15)
- Data: 2026-11-15
- Origem: tarefa 0.2 da Fase 0; escolha do grupo entre "espaço de usuário", "apt" e "contêiner de desenvolvimento"

## Contexto

O projeto depende de versões exatas: Python 3.12 (o sistema tem 3.14), Godot 4.7.2 (a base pede essa versão),
git-lfs, cliente MQTT, navegador OPC UA e, a partir da tarefa 1.7, a ferramenta de build do ESP32 (ADR-0018). Na
Fase 0 tudo foi instalado no computador do autor, em `~/.local` com checksum conferido (git-lfs via apt), e
funcionou. O critério de reprodutibilidade (6 pts) exige que um colega de outro grupo rode o sistema só com o
README, em outro computador.

## Decisão

1. As ferramentas de desenvolvimento ficam num **contêiner de desenvolvimento** versionado em `.devcontainer/`
   (`devcontainer.json` + `Dockerfile`), utilizável pelo VS Code ("Reopen in Container") ou pela CLI
   `devcontainer`, com:
   - Python 3.12 e `uv` (versões fixadas);
   - Godot 4.7.2 stable para Linux, baixado do release oficial com sha512 conferido no build, usado sem janela
     (`--headless`);
   - git e git-lfs; `amqtt` (cliente MQTT); `asyncua` (`uals`, navegador OPC UA);
   - PlatformIO (ADR-0018), com o cache da toolchain num volume nomeado;
   - Node.js (testes do `metrics.js` do M2).
2. Docker de dentro do contêiner usa o daemon do hospedeiro (*docker-outside-of-docker*, socket montado): a base e
   os serviços do M3 continuam subindo no Docker do hospedeiro, como na Fase 0.
3. Pré-requisitos do hospedeiro para o terceiro: Docker (Docker Desktop no Windows/WSL2) e git; o resto vem do
   contêiner.
4. As instalações em `~/.local` feitas na Fase 0 (uv 0.13.8, CPython 3.12.16, Godot 4.7.2, amqtt) continuam válidas
   como caminho alternativo sem contêiner e ficam registradas em `docs/evidencias/f0-0.2-ambiente.md`.
5. Implementação e validação: tarefa 1.0 do PLAN.

## Consequências

- Reprodutibilidade: o ambiente de quem desenvolve e o do terceiro passam a ser o mesmo arquivo versionado.
- A planta Godot roda sem janela dentro do contêiner; a visualização 3D com janela fica no hospedeiro, se alguém
  quiser.
- A rede precisa ser validada na 1.0: de dentro do contêiner os serviços publicados pelo hospedeiro (1883, 4840,
  4850, 8091…) são alcançados por `host.docker.internal` ou com `--network=host`; os scripts devem aceitar o
  endereço do broker e do OPC UA por variável de ambiente, não fixar `localhost`.
- Gravação no ESP32 físico por USB a partir do contêiner, no WSL2, exige `usbipd`; não é necessária enquanto a L0
  for emulada (ADR-0002).
- Imagem de desenvolvimento de alguns GB (Godot + toolchain do ESP32); construída uma vez.

## Alternativas consideradas

- **Espaço de usuário (`~/.local`) com checksum**: usado e validado na Fase 0; mantido como alternativa, mas depende
  de cada computador repetir as instalações.
- **apt/sudo para tudo**: mais simples, sem garantia das versões exatas (Godot 4.7.2, Python 3.12).
- **Flatpak/Snap do Godot**: não avaliado.
