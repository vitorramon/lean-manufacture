# Autoavaliação contra a rubrica (tarefa 4.10, RF-A4-10)

Data: 2026-11-18. A avaliação é cética: só conta o que tem evidência no repositório. Promessa em documento não vale
ponto. A rubrica é a da aula M3.A4 (SPECS §7), com 40 pontos e mais 4 de bônus.

**Tudo é emulado (ADR-0002).** A nota do critério "Sistema real" depende do aceite do professor (P-02), que ainda
não veio.

## Nota provável por critério

| Critério | Pts | Hoje | Faixa (pessimista–otimista) | Evidência que sustenta | O que falta (tarefa) |
|---|---:|---:|---|---|---|
| Sistema real funcionando, sem intervenção | 10 | 2 | 2–7 | O caminho dispositivo → MQTT → OPC UA → SQLite/AAS → twin → dashboard roda pelo `start.py` com 172 verificações OK em 16,7 min (`evidencias/f4-integracao.md`). O firmware ESP32 compila e roda no QEMU (`f1-1.7-firmware.md`, `f1-1.8-emulador-firmware.md`). 4 fontes rodam com o mesmo L2–L4 (`f1-1.10-troca-l0.md`). As falhas viram pausa e voltam (`f3-3.8-falhas.md`). **Por que 2 e não 4:** tudo é emulado, sem aceite do professor (P-02), sem vídeo e sem print do UaExpert; a nota menor prevalece na dúvida | Aceite da L0 emulada (P-02); vídeo do dashboard (RF-A1-10); prints do UaExpert (RF-A1-03, RF-A2-01); ESP32 físico (5.6); decisão da queda do broker (até 46,2 s) |
| Rastreabilidade + KPIs | 8 | 3 | 3–6 | Fichas de 4 peças no dashboard e no AAS (`f2-pos-revisao.md`, `f2-pos-revisao-rastreio-*.png`); 0 eventos repetidos; lead time por peça; tabela das 3 gerações pelo `nucleo` com origem e divergências (`f4-4.1-tres-geracoes.md`, `f4-paginas-tres-geracoes.png`); lead time da cadeia com 3 de 3 elos (`f3-3.7-tres-geracoes.md`). **Por que 3 e não 5:** nenhum KPI é Medido (só Demonstração da planta `godot`), sem vídeo de uma peça e sem peça lenta de verdade | Geração **Medido**: coleta com OP1 (1.12, 1.13); vídeo de uma peça com QR; peça lenta de verdade; outliers (RF-A1-08) |
| Documentação profissional | 8 | 4 | 4–7 | README com as 7 seções (`README.md`); relatório com tabela das 3 gerações, divergências, falhas e limitações, cada afirmação ligada a um arquivo (`docs/relatorio.pdf`, A4; páginas contadas em `evidencias/f4-revisao.md`); diagrama L0–L4 (`docs/arquitetura.png`); 33 ADRs (24 Propostos); varredura de frases proibidas sem ocorrência no texto do grupo (abaixo). **Por que 4 e não 6:** README sem teste de terceiro, `.env.example` inexistente (escrita negada; pendência do usuário), P-02 sem aceite e a maioria dos ADRs ainda Proposta | README validado por terceiro (4.7); `.env.example` (1.1); link do vídeo (4.8); ADRs Propostos aceitos ou recusados pelo grupo |
| Apresentação + demo | 8 | 0 | 0–7 | Só o roteiro: `docs/apresentacao/roteiro-apresentacao.md` (2-2-5-3-2-1, papéis A–F, demo passo a passo) e `roteiro-video-reserva.md`. Roteiro não pontua sozinho; a demo nunca foi ensaiada inteira | Slides finais, ensaio cronometrado com todos (4.9), vídeo de reserva (4.8), papéis (P-05) |
| Reprodutibilidade | 6 | 1 | 1–3 | Comando único `start.py` com health check, monitor e `--parar` corrigido (`f4-integracao.md`, `f1-1.6-start.md`); submódulos fixados (`f0-0.1-repositorio.md`); testes por componente sem rede externa (contagens em `evidencias/f4-documentos.md` e `f4-revisao.md`). **Por que 1 e não 2:** nenhuma execução fora do computador do grupo; sem `.env.example` e sem `devcontainer up` | Teste do terceiro em máquina limpa com ata (4.7, RF-A4-03); `.env.example` (1.1); `devcontainer up` (1.0) |
| **Total** | **40** | **10** | **10–30** | | |
| Bônus | +4 | 0 | 0–2 | A federação roda ao vivo, mas só com elos EMULADOS na mesma máquina (P-04). O what-if usa o simulador do M2, não a cadeia com parâmetros medidos | Parceiro real (5.3), Ishikawa com outliers medidos (5.1) ou coordenador da cadeia (5.2) |

Esta tabela é a mesma do [PROGRESS](../PROGRESS.md) (seção "Rubrica"), unificada na revisão da Fase 4
(`evidencias/f4-revisao.md`): na dúvida, vale a nota menor. A versão anterior deste arquivo dava 17/40; a diferença
estava em Sistema real (4), Rastreabilidade (5), Documentação (6) e Reprodutibilidade (2), notas que não se
sustentavam sem P-02, sem KPI Medido, sem teste do terceiro e sem `.env.example`.

O otimista de 30 supõe que o grupo cumpra tudo que é só dele: P-02 aceita, vídeos, ensaio, teste do terceiro e coleta
com operador. Não há evidência para estimar uma faixa intermediária: sem nenhuma dessas ações, vale o "Hoje" (10).

## As 5 ações de maior ganho por esforço

1. **Ensaio e vídeo de reserva (4.8, 4.9).** Podem render até 7 pontos em "Apresentação + demo". O roteiro está
   pronto, então o custo é de horas.
2. **Teste do terceiro (4.7).** Estimativa: até 2 pontos em "Reprodutibilidade" (faixa 1–3) e protege "Documentação". Um colega
   clona e segue só o README.
3. **Coleta com operador, ≥ 30 ciclos (1.12).** Destrava a geração Medido, a comparação real × simulado, os outliers e
   "Atingiu a meta?". Rende 1–2 pontos em KPIs e abre o bônus do Ishikawa (5.1).
4. **Perguntar ao professor sobre a L0 emulada (P-02).** Decide 3–5 pontos de "Sistema real". O argumento é a
   costura de hardware: firmware real no QEMU e a troca de L0 com o mesmo hash.
5. **Vídeos curtos e prints do UaExpert (1.5, 2.8, 3.5, 1.3, 3.1).** São evidências exigidas pelas aulas A1–A3 que
   hoje só existem como log.

## Riscos que podem zerar um critério no dia

| Risco | Efeito | Mitigação |
|---|---|---|
| A pilha não sobe no computador do dia (Docker, LFS, portas) | Demo ao vivo perdida | Subir 15 min antes; vídeo de reserva; prints `f4-paginas-*.png` |
| Cadeia com "1 de 3" na hora da demo | Lead time da cadeia incompleto ao vivo | Subir ≥ 15 min antes, ou mostrar `f4-paginas-cadeia-completa.png` |
| Banca entende a planta `godot` como "dado inventado" | Critério de KPIs cai | Dizer "demonstração" sempre e mostrar a regra de origem (ADR-0013) e o "não se afirma" |
| Uma pessoa só falando | Penalidade explícita da aula | Papéis A–F com blocos fixos no roteiro |

## Checklist da aula M3.A4

- [ ] `git clone` + README = sistema rodando em máquina limpa (4.7). **Pendente (grupo)**
- [x] Tabela das 3 gerações com análise das divergências: README §5, relatório §6, página "3 gerações"
- [x] Cada afirmação com evidência: relatório com caminho por afirmação, mais a varredura abaixo
- [x] Limitações com impacto e proposta: README §7, relatório §10
- [ ] Demo ensaiada no computador do dia, com `start.py`, falhas provocadas e recuperação. **Pendente (grupo)**; roteiro pronto
- [ ] Todos sabem sua parte; tempo cronometrado ≤ 15 min. **Pendente (grupo)**
- [ ] Vídeo de reserva pronto. **Pendente (grupo)**; roteiro pronto

## Varredura de frases proibidas

Comando e resultado completos em [`evidencias/f4-documentos.md`](evidencias/f4-documentos.md). A busca, sem
diferenciar maiúsculas, cobriu os seguintes arquivos:

- `README.md`, `SPECS.md` e `ARCHITECTURE.md`;
- `docs/*.md`, `docs/apresentacao/*.md`, `docs/evidencias/*.md` e `docs/adr/*.md`.

Ficaram de fora este arquivo e o `f4-documentos.md`, porque citam o próprio padrão.

O padrão procurou estas expressões:

- "foi/foram desenvolvido(a)" e "resolve o problema";
- "módulo/sistema que resolve" e "resolve(m) todos";
- "funciona perfeitamente", "100 % funcional", "totalmente funcional" e "sem nenhuma falha";
- "garante que", "comprovadamente", "medição real" e "dados reais de produção".

Resultado final: **2 ocorrências, nenhuma sobre o trabalho do grupo** (as duas falam do Virtual-Factory; detalhe abaixo). Antes da correção eram 3:

- `ARCHITECTURE.md` §11: "É o que garante que emulador e ESP32 são intercambiáveis". Foi reescrita com a evidência e
  a ressalva de que a placa física não foi testada.
- `SPECS.md` R-03 e ADR-0001: "foi desenvolvido(a) em macOS". As duas falam do Virtual-Factory, de terceiros, e não
  afirmam nada sobre o nosso trabalho. Ficaram como estão: o ADR-0001 é aceito e não se reescreve.
