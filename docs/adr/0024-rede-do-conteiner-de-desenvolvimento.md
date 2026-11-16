# ADR-0024: Rede do contêiner de desenvolvimento

- Estado: Proposto
- Data: 2026-11-15
- Origem: tarefa 1.0 do PLAN; complementa o ADR-0015 (Aceito), que pedia validar a rede na 1.0

## Contexto

O ADR-0015 deixou em aberto como o contêiner de desenvolvimento alcança a base e os serviços do M3 (`--network=host`
ou `host.docker.internal`). Na 1.0 (`docs/evidencias/f1-1.0-devcontainer.md`) os dois modos alcançaram as portas
1883, 9001, 4840, 4841 e 8091 (5 de 5). Com `--network=host`, a planta Godot publicou 0 mensagens: `localhost`
resolvia para `::1`, recusado na rede host do Docker Desktop.

## Decisão

1. O `devcontainer.json` usa `--network=host`, porque a base, a planta e os componentes do M3 têm `localhost` como
   padrão e rodam sem argumentos.
2. A imagem traz `/etc/gai.conf` com `precedence ::ffff:0:0/96 100`, para `localhost` resolver primeiro para
   `127.0.0.1`. A base não é alterada.
3. A alternativa bridge com `host.docker.internal` fica documentada em `.devcontainer/README.md`; os endereços vêm
   sempre de variável de ambiente (`MQTT_HOST`, `OPCUA_URL`, `AAS_URL`…).

## Consequências

- Com o `gai.conf`, a planta publicou 5 414 mensagens em 30 s de dentro do contêiner (dado da planta virtual, não
  medição física).
- No modo host do Docker Desktop, sem a opção "Enable host networking", o contêiner não alcança processos nativos
  do WSL e o WSL não alcança servidores dentro do contêiner (as duas medições deram HTTP 000). Quem usa o contêiner
  roda tudo dentro dele, ou tudo fora.
- O "Reopen in Container" e o `devcontainer up` ainda não foram executados (tarefa 1.0 parcial).

## Alternativas consideradas

- **Bridge com `host.docker.internal`**: alcança a base, mas exige mudar `localhost` em todos os comandos.
- **Corrigir a resolução na base**: proibido pelo ADR-0001.
