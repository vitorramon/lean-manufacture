# Linha de Celulares 4.0 — Módulo 3 (Grupo 7, Cenário 08)

Projeto final da disciplina PGENE586 — Lean Manufacturing e Qualidade Aplicadas à Indústria 4.0 (PPGEE/UFAM).

> **Estado em 2026-11-15: fase de projeto.** Este repositório contém a especificação, a arquitetura, o plano e as
> decisões. Ainda não há código do M3 e nada aqui roda. As seções marcadas "a preencher" serão completadas à medida
> que as fases de [PLAN.md](PLAN.md) forem concluídas; o andamento está em [PROGRESS.md](PROGRESS.md).

## 1. Cenário

Linha de montagem de celulares no Polo Industrial de Manaus (Cenário 08): SMT (impressora de pasta, SPI, cinco
Pick & Place, forno de refusão, AOI) seguida de 12 estações de montagem manual, teste funcional e embalagem. O
diagnóstico do M1 apontou dois problemas ligados: defeitos de solda em 2 % das placas, detectados só no teste final
depois de consumir componentes caros, e 12 operadoras montando sem método padronizado. A meta era zerar o avanço de
placas defeituosas para o acabamento e padronizar as 12 estações em 90 dias. O M2 simulou a linha com a proposta
(SPI e AOI na origem, trabalho padronizado) e mostrou o gargalo no posto Bateria (27 s contra um takt de 20 s).

O M3 tira a simulação da camada física: dispositivos passam a medir o tempo de ciclo do gargalo e a seguir cada
peça por QR Code. Neste projeto os dispositivos são **emulados**, com a mesma interface que um ESP32 real usaria,
para que a troca por hardware seja só configuração.

## 2. Arquitetura

Dispositivo → MQTT → gateway → OPC UA → AAS e banco de eventos → gêmeo, dashboard e rede federada. A base é o
[Virtual-Factory](https://github.com/aaronzi/Virtual-Factory) (planta 3D em Godot, AAS em Eclipse BaSyx, MQTT),
mantido intocado; o M3 é uma camada por cima.

Detalhes e diagramas: [ARCHITECTURE.md](ARCHITECTURE.md). Diagrama final: `docs/arquitetura.png` (a preencher).

| Camada | Tecnologia |
|---|---|
| L4 — Decisão | Streamlit (visão geral, Andon, rastreio, 3 gerações, what-if, cadeia) |
| L3 — Serviço | KPIs e fichas em Python; planta 3D; servidor T2T em OPC UA |
| L2 — Integração | Mosquitto (MQTT), `device-gateway` (MQTT → OPC UA), `aas-sync` |
| L1 — Dados | SQLite em modo WAL (`leituras`, `eventos`) e Eclipse BaSyx (AAS) |
| L0 — Física | Emulador de dispositivos, firmware ESP32 em emulador, ou ESP32 real |

## 3. Como rodar

A preencher na Fase 1, depois de testado em máquina limpa. Forma prevista:

```bash
git clone --recurse-submodules <repositório do grupo>
cd projeto-final-grupo7
python start.py --fonte roteiro      # ou: godot | operador | replay | hardware
```

Pré-requisitos previstos: Docker, Python 3.12, `uv`; Godot 4.7.2 apenas para a fonte `godot`.

## 4. Hardware

Nenhum hardware físico é usado nesta entrega. O firmware e a lista abaixo descrevem o que seria montado.

| Dispositivo | Componentes | Pinagem | Mede | Custo estimado |
|---|---|---|---|---|
| `esp32-bat01` | ESP32 DevKit, botão | Botão no GPIO 5 (pull-up interno), GND | Início e fim de ciclo no posto Bateria | R$ 45 |
| `qr-entrada`, `qr-saida` | Webcam do notebook ou USB, etiquetas QR | USB | Entrada e saída de cada peça | R$ 0 |
| `esp32-forno01` (opcional) | ESP32 DevKit, DHT22 | Dados no GPIO 4, 3V3, GND | Temperatura | R$ 70 |

Custos são as faixas citadas na aula 1 do M3, não cotações. Alimentação sempre pela USB do computador. Registro de
calibração: a preencher na Fase 1.

## 5. KPIs — três gerações

| KPI | Baseline (M1) | Simulado (M2), média ± desvio, n = 30 | Medido (M3) | Meta (M1) |
|---|---|---|---|---|
| FPY (teste funcional) | 78 % | 94,18 ± 0,77 % (atual) → 99,80 ± 0,13 % (Lean local) → 99,78 ± 0,12 % (Lean ampliado) | a medir | 92 % |
| RTY | 82 % | 94,18 ± 0,77 % (atual) → 94,03 ± 0,53 % (Lean local) → 94,01 ± 0,52 % (Lean ampliado) | a medir | 90 % |
| OEE da linha (ciclo 20 s) | 68 % | 68,61 ± 0,56 % (atual) → 75,47 ± 0,10 % (Lean local) → 92,44 ± 0,54 % (Lean ampliado) | a medir | 80 % |
| 1 − COPQ (scrap) | 95 % | 95,75 ± 0,56 % (atual) → 98,76 ± 0,14 % (Lean local) → 98,71 ± 0,15 % (Lean ampliado) | a medir | 98 % |
| Lead time do trecho Bateria → Embalagem (min) — complementar | sem baseline no M1 | 64,22 ± 0,22 → 46,55 ± 1,60 → 2,87 ± 0,00 | a medir | a definir |
| Espera na fila da Bateria (min) — complementar | sem baseline no M1 | 61,54 ± 0,00 → 0,00 → 0,00 | a medir | a definir |

Fonte da coluna "Simulado (M2)": simulador do M2 (`simulador/`, commit `1e4b27d`), sem alteração, 30 replicações de
8 h por cenário (sementes 1–30), KPIs calculados pelo `metrics.js` do próprio painel; tarefa 0.8, evidência
[`docs/evidencias/f0-0.8-replicacoes.md`](docs/evidencias/f0-0.8-replicacoes.md) e tabela completa com IC 95 % em
[`dados/analises/f0_replicacoes.md`](dados/analises/f0_replicacoes.md). O cenário SPI/AOI sem Lean está lá também.

Baseline e meta vêm da entrega do M1 (projeção em 90 dias). O M1 não definiu baseline nem meta de lead time.
Limitações desta coluna:

- Os desvios são pequenos porque o modelo do M2 tem tempos determinísticos e sorteia só os defeitos: medem a
  sensibilidade à semente, não a variabilidade real do processo. Para comparar com o medido (tarefa 1.12) usa-se a
  distribuição por peça (no atual, de 184 s a 7 520 s no trecho).
- O FPY simulado (94 %) diverge do M1 (78 %): o M2 só gera três defeitos de solda de 2 % cada (SPECS §2.2).
- No cenário atual a fila da Bateria cresce o turno todo; o lead time do trecho depende do horizonte de 8 h e é
  limite inferior (só peças concluídas).

## 6. Cartão de conexão

| Item | Valor previsto |
|---|---|
| Servidor OPC UA dos dispositivos | `opc.tcp://<IP>:4850/lean/dispositivos` |
| Servidor T2T do gêmeo | `opc.tcp://<IP>:4851` |
| Namespace T2T | 2 (`TwinLinhaCelulares`) |
| `EstadoGemeo.RitmoReal` / `.RitmoProducao` | float, peças/h — peças concluídas nos últimos 10 min × 6 |
| `EstadoGemeo.UltimaPeca` | string — identificador da última peça concluída |
| `EstadoGemeo.LeadTimeMedio` | float, min — lead time médio local |
| `EstadoGemeo.StatusLinha` | string — Normal, Atenção, Parada ou Sem dados |
| Broker MQTT | `<IP>:1883` |

As portas 4840 e 4841, usuais na disciplina, já são ocupadas pelo CLP virtual do Virtual-Factory.

## 7. Limitações

| Limitação | Impacto no resultado | Proposta |
|---|---|---|
| Dispositivos emulados | Ruído elétrico, alimentação e cabeamento reais não são exercitados | Rodar o firmware em emulador de ESP32; substituir um emulador por placa física |
| Planta 3D de outro produto (cilindro pneumático) | Tempos da planta virtual não representam a linha de celulares | Mapeamento documentado; tempos humanos pela fonte `operador` |
| Trecho de 3 pontos de medição em 22 estações | Lead time medido é parcial | Comparar com o mesmo trecho do simulado; ampliar pontos |
| Uma semente no M2 | Coluna "Simulado" sem intervalo de confiança | 30 replicações (Fase 0) |

## Equipe

Grupo 7: Dawesley Mota, Guilherme Barros, Janderson Chaves, Jose Rudiney, Ramon Viana, Raphael Santos.

## Documentos

- [SPECS.md](SPECS.md) — o que as aulas exigem, o que já foi entregue e o que falta
- [ARCHITECTURE.md](ARCHITECTURE.md) — camadas, contratos, serviços e implantação
- [PLAN.md](PLAN.md) — fases e tarefas
- [PROGRESS.md](PROGRESS.md) — andamento, bloqueios e evidências
- [docs/adr/](docs/adr/README.md) — decisões de arquitetura
- [CLAUDE.md](CLAUDE.md) — instruções para o assistente de código

## Licenças e créditos

O Virtual-Factory é de terceiros e está sob Apache-2.0; os avisos de `LICENSE` e `NOTICE` devem acompanhar qualquer
cópia. Licença do código do grupo: a definir.
