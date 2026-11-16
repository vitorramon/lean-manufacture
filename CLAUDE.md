# Módulo 3 — notas para o Claude

Projeto final do Grupo 7 (Cenário 08, linha de celulares) da disciplina PGENE586. Esta pasta é a raiz do
repositório `vitorramon/lean-manufacture` (remoto `origin`; push só a pedido).

## Leia antes de agir

1. [PROGRESS.md](PROGRESS.md): estado real, bloqueios, o que já tem evidência
2. [PLAN.md](PLAN.md): a próxima tarefa
3. [SPECS.md](SPECS.md): requisito e evidência de aceite da tarefa
4. [ARCHITECTURE.md](ARCHITECTURE.md) e [docs/adr/](docs/adr/README.md): como e por quê

Em 2026-11-15 a Fase 1 existe em código (contrato, emulador, firmware, gateway, aas-sync, app, `start.py`), com
várias tarefas parciais: confira o PROGRESS antes de presumir que algo está pronto.

## Regras do projeto

- **Só a L0 troca.** Nada acima do broker pode saber se o dado veio de emulador, firmware emulado ou ESP32. Se uma
  mudança em L2–L4 for necessária para uma fonte específica, o contrato está errado: corrija o contrato.
- **Contratos são lei** (SPECS §6): tópicos `dev/v1`, address space OPC UA, tabelas `leituras` e `eventos`, nós
  T2T. Alterar um contrato exige ADR novo e atualização dos testes de contrato.
- **Timestamp só no gateway.** Dispositivo e firmware nunca enviam data/hora.
- **Dado inválido não entra** no banco nem no AAS; vai para contagem e log de rejeitados.
- **Leitura de dados só por `app/nucleo/dados.py`.** Nenhuma página faz SQL direto.
- **`aas-sync` é o único que escreve** no SQLite e no AAS.
- **Virtual-Factory é intocado.** Nada de editar `Base/Virtual-Factory` (ou `base/`); o M3 entra por arquivo
  compose adicional, serviços e dados próprios. Mudança inevitável na base exige ADR.
- **A geração "Medido (M3)" dos KPIs nunca vem da fonte `roteiro`** (ADR-0013).
- **Portas:** 4850 (OPC UA dos dispositivos), 4851 (T2T), 8501 (dashboard). 4840 e 4841 são do Virtual-Factory.
- **Idioma:** documentação, interface e mensagens em português; identificadores de padrões em inglês.

## Honestidade técnica (a disciplina avalia isto)

- Toda afirmação em README e relatório precisa de evidência em `docs/evidencias/` (print, gráfico, vídeo, número).
  Proibido "foi desenvolvido um módulo que resolve": escreva "o módulo X resolve Y, comprovado por Z".
- Diga sempre que os dispositivos são emulados. Nunca descreva dado emulado como medição física.
- Limitações no formato limitação → impacto → proposta.
- Baseline e metas do M1 estão em SPECS §2.1 (FPY, RTY, OEE, 1 − COPQ). O M1 não tem baseline de lead time:
  não invente; use "sem baseline no M1".
- Resultado surpreendente ou meta não atingida é documentado, não ajustado.

## Ao concluir uma tarefa

Use a skill `concluir-tarefa` (e `novo-adr` se houve decisão); antes do commit, o agente `revisor-contratos`.
Commits sem linha de coautoria (`.claude/rules/git.md`). Marque em PROGRESS com data e evidência; atualize README, SPECS ou ARCHITECTURE se o comportamento mudou; registre
ADR se houve decisão. Uma tarefa só está pronta quando roda pelo `start.py`, tem teste ou roteiro de verificação e
tem evidência (PLAN, "Definição de pronto").

## Ambiente

- Linux em WSL2 com Docker Desktop. Caminhos com espaço (`MOD 3`): use aspas.
- Instalados na Fase 0: `uv`, Python 3.12 (via uv), Godot 4.7.2 e amqtt em `~/.local`; git-lfs via apt. PlatformIO 6.1.18
  via `uv tool` e QEMU da Espressif em `~/.local/opt` (`emular.sh --instalar`). Python do sistema é 3.14; o Virtual-Factory pede 3.12 (use `uv`).
- Não há `pdftotext`: os PDFs das aulas não abrem com a ferramenta de leitura. O texto das aulas relevantes já está
  resumido em SPECS.
- O `CLAUDE.md` do Virtual-Factory foi escrito para macOS (`/Applications/Godot.app`); adapte os comandos.
- Os contêineres `rebac-*` citados lá pertencem a outro projeto: não mexa.

## Comandos

```bash
python3 start.py --fonte roteiro --velocidade 4 [--manter-base]   # ou godot | operador --operador OP1 | firmware
python3 start.py --parar [--manter-base]                           # compose down sem -v
uv run --project pipeline/contrato pytest tests/contrato           # idem: hardware/emulador tests/emulador,
uv run --project pipeline/device_gateway pytest tests/device_gateway  # pipeline/aas_sync tests/aas_sync, app tests/app
(cd hardware/firmware && pio test -e native && pio run -e esp32)   # ./emular.sh roda no QEMU
```

Cada componente tem `pyproject.toml` e `uv.lock` próprios; detalhes em `infra/README.md` e no README de cada pasta.

## Fontes

- Aulas: `../../Teoria/MOD 1`, `MOD 2`, `MOD 3`, `EXTRAS` (PDF; em EXTRAS há também um zip com esqueleto de código)
- Entrega do M1: `../MOD 1/PPGEE_Grupo_7_Cen_8.pptx` (um `.pptx` é um zip: o texto está em `ppt/slides/*.xml`)
- Entrega do M2: `../MOD 2/GemeoDigitalCelulares`
- Base: `../../../Base/Virtual-Factory` (documentação em `docs/`, 31 ADRs próprios)
