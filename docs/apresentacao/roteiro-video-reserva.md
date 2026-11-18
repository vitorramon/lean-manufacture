# Roteiro do vídeo de reserva — 3 min (tarefa 4.8, RF-A4-08)

Grupo 7 · versão de 2026-11-18. **Pendência do grupo:** gravar com o sistema real rodando, publicar e pôr o link no
README (hoje "pendente (grupo)"). O vídeo cobre o bloco da demo da apresentação e a substitui se algo falhar no dia.

## Preparação

- Gravar a tela inteira (1920 × 1080) com o OBS ou equivalente, com narração. Sem música.
- Subir **15 min antes de gravar**, com banco novo, para que a Cadeia já mostre 3 de 3 elos:

  ```bash
  COMPOSE_PROFILES=base-completa DB_PATH=dados/dados.video.db python3 start.py --fonte godot --manter-base
  ```

- Deixar num segundo terminal, já digitado, o comando
  `PROPAGACAO_ESTAVEL_S=5 twin/t2t/.venv/bin/python tests/vivo/f3_propagacao.py 1 /tmp/video.log` (5 s de linha estável antes da parada, no lugar dos 45 s do padrão).
- Legenda fixa no canto, durante todo o vídeo: **"Dispositivos emulados (ADR-0002) · planta godot = demonstração ·
  elos da cadeia EMULADOS (P-04)"**.

## Cenas

| Tempo | Cena (tela) | Narração (resumo) |
|---|---|---|
| 0:00–0:15 | Slide de título e `docs/arquitetura.png` | "Linha de celulares do Grupo 7. Dispositivos emulados publicam por MQTT, um gateway publica em OPC UA, o banco e o AAS guardam, o dashboard decide." |
| 0:15–0:35 | Terminal do `start.py` com `saudável:` e `OK` | "Um comando sobe a base e o M3, espera a saúde de cada serviço e monitora a cada 5 s." |
| 0:35–1:05 | Visão geral: Andon do posto e cartões do M1 | "Ciclo do posto Bateria ao vivo. Os cartões comparam FPY e RTY com baseline e meta do M1; com a planta virtual, é demonstração, não meta atingida." |
| 1:05–1:35 | Rastreio: ficha da última peça | "Cada peça tem QR, trajetória, tempo por estação e lead time individual." |
| 1:35–2:15 | Enter no segundo terminal; dividir a tela entre a saída do script e a Cadeia | "Paramos a fonte da Produção: o twin publica PARADA e a Distribuição emulada reage em cerca de 2 segundos. O script mede no próprio relógio." |
| 2:15–2:35 | Visão geral com o Andon cinza e depois verde | "Sem dado novo, o Andon vai a cinza; a fonte volta e ele volta ao verde." |
| 2:35–2:55 | 3 gerações | "Baseline do M1, 30 replicações do M2 e o M3, com a origem de cada número. Meta atingida só se afirma com dado medido por operador." |
| 2:55–3:00 | Tela final | "Repositório e relatório: link no README." |

## Depois de gravar

1. Conferir a duração (≤ 3:00) e se os tempos que o script imprimiu aparecem legíveis.
2. Publicar (YouTube não listado ou Drive com link aberto) e trocar "pendente (grupo)" pelo link no README.
3. Registrar em `docs/evidencias/f4-4.8-video.md`: data, duração, link e os tempos medidos que aparecem no vídeo. Esse arquivo ainda
   não existe: o vídeo é pendência do grupo (4.8).
4. `python3 start.py --parar`.
