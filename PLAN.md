# PLAN — Módulo 3

Ordem de execução para cumprir [SPECS.md](SPECS.md) com a arquitetura de [ARCHITECTURE.md](ARCHITECTURE.md).
O andamento fica em [PROGRESS.md](PROGRESS.md). Cada fase termina com algo que roda e com as evidências que a aula
correspondente exige.

Princípios: fatia vertical primeiro (um dado atravessando tudo antes de alargar); contrato antes de código;
evidência coletada no momento em que a funcionalidade passa, não na véspera; bônus por último.

## Antes de começar: pendências do grupo

Não dependem de código e destravam decisões. Detalhes em SPECS §9.

- [x] P-01 Recuperar a entrega do M1 e anotar baseline, metas e Mudas (2026-11-15, SPECS §2.1)
- [ ] P-02 Perguntar ao professor sobre L0 totalmente emulada
- [x] P-03 Extras: material lido; o grupo confirmou que não as fez (2026-11-15) — conteúdo absorvido na Fase 3
- [ ] P-04 Definir grupo parceiro da cadeia (ou assumir elo emulado)
- [ ] P-05 Datas de apresentação e entrega; integrantes e papéis
- [ ] P-06 Criar fork do Virtual-Factory e repositório final no GitHub
- [ ] P-07 Decidir se haverá meta de lead time/espera (o M1 não definiu)

## Fase 0 — Fundação e validação da base

Objetivo: saber se o Virtual-Factory roda neste ambiente (Linux/WSL2 com Docker Desktop) e quanto dele é preciso.

- [ ] 0.1 Iniciar o repositório Git do M3; incluir Virtual-Factory e simulador do M2 com commit fixado (ADR-0001)
      — parcial em 2026-11-15: falta git-lfs permanente no PATH
- [ ] 0.2 Instalar ferramentas: `uv`, Python 3.12, Godot 4.7.2, Git LFS, navegador OPC UA (UaExpert ou equivalente)
      — parcial em 2026-11-15: falta Git LFS instalado; OPC UA só `uals --help`
- [ ] 0.3 Subir o compose do Virtual-Factory e registrar o que sobe, tempo de subida e consumo de memória
      — parcial em 2026-11-15: pilha completa só em cópia temporária; refazer a partir de `base/` com LFS
- [ ] 0.4 Rodar a planta em modo sem janela e observar os eventos `part_released`, `part_inspected`, `part_sorted`
      — parcial em 2026-11-15: os 3 eventos só foram observados na rodada da 0.5
- [x] 0.5 Definir o perfil reduzido de serviços necessário ao M3
- [x] 0.6 Validar o mapeamento planta virtual ↔ linha de celulares (ARCHITECTURE §4) e ajustar o ADR-0009
- [x] 0.7 Rodar o simulador do M2 em Linux, conferir os números de SPECS §2.2 e extrair FPY, RTY e COPQ do painel
- [x] 0.8 Rodar 30 replicações do M2 (sementes distintas) no trecho recortado: média ± desvio da geração "Simulado"

Saída: registro em PROGRESS com medições; ADR-0009 confirmado ou revisado; decisão de continuar com a base.
Ponto de decisão: se a base não subir de forma estável em WSL2, reabrir o ADR-0001 antes de escrever código.

## Fase 1 — Primeiro dispositivo de ponta a ponta (Aula 1)

Objetivo: um evento de ciclo sai de um dispositivo emulado e aparece no dashboard, passando por MQTT, OPC UA, banco
e AAS.

- [ ] 1.1 Escrever o contrato `dev/v1`: esquemas JSON e mensagens de referência (`pipeline/contrato/`)
- [ ] 1.2 Emulador Python do `esp32-bat01` com a fonte `roteiro`
- [ ] 1.3 `device-gateway`: assinatura MQTT, validação, timestamp, servidor OPC UA com um objeto
- [ ] 1.4 `aas-sync`: subscription OPC UA → `leituras` no SQLite e estado do dispositivo no AAS
- [ ] 1.5 `nucleo/dados.py` e página "Visão geral" mínima; Andon cinza por ausência de dado
- [ ] 1.6 Compose adicional e `start.py` com health check
- [ ] 1.7 Firmware ESP32: lógica independente de placa, camada de hardware, publicação MQTT; compilar para ESP32
- [ ] 1.8 Escolher e configurar o emulador de firmware; rodar o firmware nele contra o mesmo broker
- [ ] 1.9 Fontes `godot` e `operador` no emulador
- [ ] 1.10 Teste da troca de L0: mesmo commit de L2–L4 com `roteiro`, `godot`, `operador` e firmware emulado
- [ ] 1.11 Procedimento de calibração (4 testes) e faixas de validação; registro no README
- [ ] 1.12 Coleta de ≥ 30 ciclos com a fonte `operador`; comparação com o simulado (tabela e histogramas)
- [ ] 1.13 Classificação de ≥ 3 outliers (Muda real × falha de medição)

Evidências: print do address space; vídeo do dashboard atualizando; gráfico comparativo; registro de calibração;
tabela de outliers.

## Fase 2 — Vários dispositivos e rastreabilidade (Aula 2)

Objetivo: cada peça tem identidade, trajetória e lead time próprios.

- [ ] 2.1 Segundo e terceiro dispositivos por configuração (`qr-entrada`, `qr-saida`); nenhum código de L2–L4 muda
- [ ] 2.2 Leitor de QR: modo emulado e modo câmera; geração das etiquetas
- [ ] 2.3 Tabela `eventos`; deduplicação e expiração de peças no gateway
- [ ] 2.4 Associação ciclo ↔ peça por posto
- [ ] 2.5 Ficha da peça no AAS e ligação com o QR da peça da planta virtual (ADR-0008)
- [ ] 2.6 Página "Rastreio": busca por ID, trajetória, espera, comparação com a média
- [ ] 2.7 Página "Dispositivos": online, última leitura, rejeições, lacunas
- [ ] 2.8 Fluir ≥ 20 peças; fichas de ≥ 3 peças (uma rápida, uma lenta)
- [ ] 2.9 Análise de espera: peça mais lenta, onde esperou, Muda do M1 associada
- [ ] 2.10 Resultado do teste por peça nos eventos; FPY e RTY medidos no trecho

Evidências: print do address space com ≥ 2 objetos; vídeo de uma peça atravessando a linha; três fichas; consulta
mostrando ausência de eventos repetidos.

## Fase 3 — Rede federada (Aula 3)

Objetivo: o estado medido sai do gêmeo, um vizinho reage, e a cadeia tem lead time.

- [ ] 3.0 Modelo simplificado da cadeia (fornecedor → produção → distribuição) em SimPy: lead time simulado da
      cadeia, que substitui o resultado da Extra 2 não realizada
- [ ] 3.1 `twin-t2t`: servidor com `RitmoReal`, `UltimaPeca`, `LeadTimeMedio`, `StatusLinha`
- [ ] 3.2 Cliente com reconexão automática e estado `OFFLINE` por elo
- [ ] 3.3 Elos "Fornecedor" e "Distribuição" emulados localmente; teste em `localhost` antes de qualquer rede
- [ ] 3.3a Usar o dado do vizinho numa decisão nossa (ex.: estoque do fornecedor baixo → `StatusLinha`)
- [ ] 3.3b Contrato de interface da cadeia e cartão de conexão completo (tipos e unidades)
- [ ] 3.4 Página "Cadeia": elos, ritmo, lead time da cadeia (soma dos locais)
- [ ] 3.5 Teste de propagação: interromper a produção e medir o tempo de reação do elo a jusante
- [ ] 3.6 Conexão com grupos parceiros, se houver (P-04), na ordem `localhost` → `ping` → porta → OPC UA
- [ ] 3.7 Tabela das 3 gerações do lead time da cadeia
- [ ] 3.8 Registro de falhas provocadas e da recuperação

Evidências: vídeo da propagação com o tempo medido; painel da cadeia; `docs/cartoes_conexao.md`; registro de falhas.

## Fase 4 — Consolidação e entrega (Aula 4)

Objetivo: um produto único, documentado e reproduzível.

- [ ] 4.1 Página "3 gerações" com a tabela final e as divergências
- [ ] 4.2 Limites do Andon ligados a `regras.py` com baseline e metas do M1 (SPECS §2.1)
- [ ] 4.3 Página "What-if" reaproveitando o simulador do M2
- [ ] 4.4 README final com as 7 seções obrigatórias
- [ ] 4.5 `docs/arquitetura.png`
- [ ] 4.6 Relatório final: 3 gerações, divergências, evidências, limitações (limitação → impacto → proposta)
- [ ] 4.7 Teste do terceiro em máquina limpa; corrigir o README até passar
- [ ] 4.8 Vídeo de reserva de 3 min; link no README
- [ ] 4.9 Slides no roteiro de 15 min; ensaio cronometrado com todos os integrantes
- [ ] 4.10 Checklist de autoavaliação da rubrica; revisão de "frases proibidas"
- [ ] 4.11 Entrega: GitHub + PDF no ambiente da disciplina

## Fase 5 — Bônus e extras (só se sobrar tempo)

- [ ] 5.1 Ishikawa (6M) preenchido com os outliers medidos
- [ ] 5.2 Gêmeo coordenador (Extra 3): ≥ 3 cenários da cadeia com parâmetros medidos, recomendação publicada
- [ ] 5.2a Experimento do efeito chicote (demanda ±20 %)
- [ ] 5.3 Federação ao vivo com outro grupo
- [ ] 5.4 Dispositivo `esp32-forno01` (temperatura) com Andon por faixa
- [ ] 5.5 Adaptação dos dados de produto do AAS para celular; ajustes visuais na planta 3D
- [ ] 5.6 ESP32 físico substituindo um emulador (a demonstração mais forte da costura de hardware)

## Dependências entre fases

```mermaid
flowchart LR
  P[Pendências do grupo] -.-> F4
  F0[Fase 0<br/>base validada] --> F1[Fase 1<br/>1 dispositivo]
  F1 --> F2[Fase 2<br/>rastreabilidade]
  F2 --> F3[Fase 3<br/>federação]
  F2 --> F4[Fase 4<br/>entrega]
  F3 --> F4
  F4 --> F5[Fase 5<br/>bônus]
```

A Fase 4 pode começar em paralelo à Fase 3: README, diagrama e relatório crescem desde a Fase 1.

## Caminho mínimo se o prazo apertar

Na ordem em que se corta: Fase 5 inteira → 3.6 (parceiro real; fica o elo emulado) → 1.8 (firmware em emulador;
fica o firmware compilável) → 4.3 (what-if; fica o painel do M2). Não se corta: contrato e teste da troca de L0,
rastreabilidade com fichas, tabela das 3 gerações, README testado por terceiro e vídeo de reserva.

## Definição de pronto

Uma tarefa só é marcada em PROGRESS quando: roda a partir do `start.py`; tem teste automatizado ou roteiro de
verificação manual escrito; a evidência está em `docs/evidencias/`; e a documentação afetada foi atualizada.
