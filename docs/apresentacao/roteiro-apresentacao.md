# Roteiro da apresentação final — 15 min (tarefa 4.9, RF-A4-07)

Grupo 7 · Cenário 08 · versão de 2026-11-18. **Este é o roteiro, não a apresentação.** Ficam com o grupo:

- montar os slides finais a partir do conteúdo abaixo;
- distribuir os papéis (P-05);
- fazer o ensaio cronometrado com todos;
- gravar o vídeo de reserva ([roteiro-video-reserva.md](roteiro-video-reserva.md)).

Os papéis aparecem como **Integrante A–F**. O grupo decide quem é quem e anota fora do repositório ou no slide de
abertura. Pela aula M3.A4, **todos falam**. Os três pecados são:

- digitar código ao vivo;
- mostrar slide no lugar do sistema;
- uma pessoa falar sozinha.

Regra de honestidade da fala: dizer **"emulado"** sempre que aparecer um dispositivo e **"demonstração"** sempre que
aparecer um número da planta `godot`. A frase-modelo é "o módulo X resolve Y, comprovado por Z".

## Estrutura 2-2-5-3-2-1

| Tempo | Bloco | Quem fala | O que aparece na tela |
|---|---|---|---|
| 0:00–2:00 | Problema | Integrante A | Slides 1–2 |
| 2:00–4:00 | Arquitetura | Integrante B | Slides 3–4 (`docs/arquitetura.png`) |
| 4:00–9:00 | Demo ao vivo | Integrante C (narra) + Integrante D (opera) | **Sistema**, não slide: navegador em http://localhost:8501 e um terminal preparado |
| 9:00–12:00 | Resultados | Integrante E | Página "3 gerações" ao vivo + slide 5 (divergências) |
| 12:00–14:00 | Rede federada | Integrante D | Página "Cadeia" ao vivo + slide 6 |
| 14:00–15:00 | Fechamento | Integrante F | Slide 7 |

Na demo, D opera e C narra. Assim duas pessoas falam no bloco mais longo, e quem opera não precisa narrar.

## Preparação (T − 20 min, no computador do dia)

1. Docker Desktop no ar e nada nas portas 1883, 4850–4853, 8091 e 8501:
   `ss -ltn | grep -E ':(1883|485[0-3]|8091|8501) '` não pode mostrar nada.
2. Subir **com banco novo** e **pelo menos 15 min antes**. O lead time da cadeia só fica completo (3 de 3) depois da
   primeira reposição do Fornecedor emulado, cerca de 15 min depois da subida (`f4-integracao.md`).

   ```bash
   COMPOSE_PROFILES=base-completa DB_PATH=dados/dados.apresentacao.db python3 start.py --fonte godot --manter-base
   ```

3. Esperar o log mostrar `dashboard respondendo` (≈ 85 s) e o monitor imprimir `OK` em sequência.
4. Abrir no navegador, em abas: Visão geral, Rastreio, Cadeia, 3 gerações, What-if. Zoom de 125 % para o projetor.
5. Deixar num segundo terminal, **já digitado e sem Enter**, o comando do passo 4 da demo. Abrir o log do `start.py`
   para achar o pid do Fornecedor (linha `iniciado fornecedor (pid N)`).
6. Plano B aberto numa aba: o vídeo de reserva (link no README, quando existir) e os prints `docs/evidencias/f4-paginas-*.png`.

## Slides (conteúdo)

**Slide 1 — Título.** "Linha de Celulares 4.0: do simulado ao medido". Grupo 7, Cenário 08, PGENE586. Os 6
integrantes. Uma frase: "Tudo o que vão ver roda em dispositivos **emulados**, com a mesma interface de um ESP32."

**Slide 2 — Problema e hipótese (A).**
- M1: 2 % de defeito de solda achado só no teste final; 12 operadoras sem método. Causa-raiz "Medida": sem coleta de
  dados em tempo real nas estações manuais.
- Meta do M1: FPY 78 → 92 %, RTY 82 → 90 %, OEE 68 → 80 %, 1 − COPQ 95 → 98 %.
- M2: gargalo na Bateria, 27 s contra takt de 20 s.
- Hipótese do M3: medir ciclo e seguir cada peça por QR transforma KPI estimado em KPI calculado por peça.
- Recorte: Bateria → Teste → Embalagem (ADR-0009).

**Slide 3 — Arquitetura (B).** `docs/arquitetura.png`. Fala em 4 frases:
1. "Só a L0 troca": emulador, firmware no QEMU ou ESP32 publicam o mesmo `dev/v1`.
2. O timestamp nasce no gateway, nunca no dispositivo.
3. O `aas-sync` é o único escritor; as páginas leem pelo `nucleo`.
4. A base Virtual-Factory é intocada; o M3 é um compose adicional e um `start.py`.

**Slide 4 — Costura de hardware (B).**
- Tabela do README §4: ESP32 DevKit, botão no GPIO 5, DHT22 no GPIO 4, R$ 90–160 (estimativa).
- O firmware real compila (Flash 58,1 %, 29 testes) e roda no QEMU (16/16 mensagens válidas).
- 4 fontes rodaram com o mesmo hash de L2–L4 (`f1-1.10-troca-l0.md`).
- Dizer: "nenhuma placa foi comprada; a calibração é de procedimento".

**Slide 5 — Divergências (E)**, para mostrar ao lado da página 3 gerações:
- FPY M2 94 % × M1 78 %: o M2 só sorteia 3 defeitos de 2 % (0,98³).
- RTY do M1 > FPY do M1: definição diferente.
- FPY M3 91,5 %: sorteio da planta, demonstração, não melhoria.
- OEE e COPQ: o M2 bate com o M1; o M3 não calcula.
- Lead time: recortes diferentes (fila do M2 × planta balanceada).

**Slide 6 — Rede federada (D).**
- Cadeia Fornecedor → Produção → Distribuição.
- Elos **EMULADOS** pelo grupo (P-04).
- Propagação em 2,42 s (máx. 3,02 s, n = 6).
- Tabela curta das falhas da 3.8.
- Achado: queda do broker até 45 s, acima do limite de 30 s.

**Slide 7 — Fechamento (F).**
- 3 limitações no formato limitação → impacto → proposta: L0 emulada, sem coleta com operador, elos emulados.
- Trabalhos futuros: ESP32 físico, coleta OP1, parceiro real.
- Aprendizado em uma frase por integrante, opcional e só se couber no minuto.

## Demo ao vivo, passo a passo (4:00–9:00)

| Tempo | D faz | C diz | Deve aparecer |
|---|---|---|---|
| 4:00 | Mostra o terminal do `start.py` rolando `OK` | "Um comando subiu 26 contêineres e o monitor confere processo, porta e dado a cada 5 s." | Linhas `OK \| processos [...] \| banco {...}` com contagens subindo |
| 4:30 | Aba **Visão geral** | "Cada ciclo do posto Bateria chega do dispositivo emulado; o Andon de cima usa baseline e meta do M1." | Andon do posto VERDE; cartões FPY AMARELO, RTY VERDE com a ressalva "demonstração", OEE e COPQ CINZA |
| 5:15 | Aba **Rastreio**, busca a última peça (copiar de "Última peça") | "Cada peça tem trajetória, tempo por estação e lead time individual, lidos do banco e do AAS." | Ficha com entrada → teste → saída e comparação com a média |
| 6:15 | No segundo terminal, Enter em `PROPAGACAO_ESTAVEL_S=5 twin/t2t/.venv/bin/python tests/vivo/f3_propagacao.py 1 /tmp/demo.log` (o padrão espera 45 s de linha estável antes de parar; com 5 s a parada vem logo) | "Agora derrubamos a fonte da Produção, como se a linha parasse." | Em ~1 s, `PARADA` no twin; em ~2,5 s, a Distribuição reage; o script imprime os tempos |
| 6:45 | Volta à **Visão geral** | "O Andon do posto não fica verde por inércia: sem dado novo em 15 s, vai a cinza." | Andon do posto CINZA (offline); depois o script religa a fonte e volta ao VERDE |
| 7:30 | Aba **Cadeia** | "O vizinho vê a nossa parada e reage. O lead time da cadeia é a soma dos locais, nunca de relógios diferentes." | `StatusLinha` voltando a PRODUZINDO; soma 3 de 3, se já tiver passado 15 min |
| 8:15 | Aba **What-if**: defeito 5 %, Simular | "O simulador do M2 roda aqui dentro, sem cópia: defeito de 5 %, −8,5 p.p. de FPY (3 replicações, demonstração; Simulado, não medição)." | Resposta em ~6 s, origem Simulado (M2/SimPy) |
| 9:00 | — | Passa para E | — |

Esta sequência foi montada com peças verificadas separadamente, mas **nunca foi ensaiada inteira**:

- a subida e as páginas em `f4-integracao.md`;
- a parada e a religação da fonte em `f3-3.5-propagacao.md`;
- o Andon cinza com dispositivo offline em `f1-1.5-dashboard.md`.

O script religa a fonte poucos segundos depois da reação. Por isso a janela do Andon cinza pode ser curta: no ensaio,
confira se dá tempo de trocar de aba ou mostre o cinza antes da Cadeia.

Se algo falhar, C diz o que era esperado, D abre o print correspondente (`f4-paginas-*.png`) e a fala segue. Se a
pilha não subir, roda o vídeo de reserva.

## Resultados (9:00–12:00, E)

Página **3 gerações** ao vivo, de cima para baixo:

1. Ler a tabela: Baseline M1 → Simulado M2 (n = 30) → M3 → Meta M1.
2. Mostrar a coluna de origem: "Medido só vem de operador ou hardware; a planta é demonstração; roteiro nunca entra."
3. "Atingiu a meta?" = "não se afirma". Dizer por quê: falta a coleta com operador (1.12).
4. Slide 5 com as divergências. Insistir que **não foram ajustadas**.

## Rede federada (12:00–14:00, D)

1. Página **Cadeia**: 3 elos, ritmo, soma dos locais, `Cadeia.Decisao`.
2. Opcional, se o tempo permitir: SIGUSR2 no Fornecedor emulado com o pid do log (`kill -USR2 <pid>`, comando já
   digitado no segundo terminal). O resultado esperado é `RISCO_FALTA` em ~3 s, porque o estoque do vizinho entra na
   nossa decisão (RF-A3-09).
3. Slide 6: tabela de falhas e o achado da queda do broker.

## Checklist do ensaio (pendência do grupo)

- [ ] Papéis A–F definidos (P-05)
- [ ] Ensaio cronometrado ≤ 15:00, com a hora de cada bloco anotada
- [ ] Demo ensaiada no computador do dia, com banco novo e subida 15 min antes
- [ ] Segundo terminal com os comandos já digitados (nada é digitado ao vivo)
- [ ] Plano B testado: vídeo de reserva e prints abrem sem rede
- [ ] Todos dizem "emulado" e "demonstração" nos lugares certos
- [ ] `python3 start.py --parar` no fim, com as portas livres
