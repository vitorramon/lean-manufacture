# ADR-0010: Dashboard em Streamlit com Andon de 4 níveis

- Estado: Proposto
- Data: 2026-11-15
- Origem: aulas M2.A5 e M3.A2; lacunas do M2

## Contexto

A disciplina prescreve Streamlit multipágina, com a lógica em `nucleo/` e os limites do M1 em `regras.py`, e um
Andon com quatro níveis, sendo o cinza (dado velho) "o mais esquecido e o mais importante". O M2 entregou Streamlit
com um painel HTML, sem Andon. O Virtual-Factory traz Grafana, a interface web do AAS e painéis dentro da planta 3D.

## Decisão

1. A L4 do M3 é um aplicativo Streamlit multipágina: Visão geral, Andon, Rastreio, 3 gerações, Dispositivos,
   What-if e Cadeia.
2. Toda leitura passa por `app/nucleo/dados.py`; limites e metas ficam em `app/nucleo/regras.py`.
3. Andon: verde (dentro dos limites), amarelo (tendência), vermelho (limite violado) e **cinza** (sem dado novo
   além do prazo, ou dispositivo offline pelo Last Will).
4. Os cálculos de indicadores do M2 são reaproveitados onde se aplicam.
5. Grafana, a interface web do AAS e a planta 3D permanecem como visão de engenharia e não substituem o dashboard.
6. Os limites do Andon vêm do M1: vermelho abaixo do baseline (FPY 78 %, RTY 82 %, OEE 68 %), amarelo entre
   baseline e meta, verde a partir da meta (92 %, 90 %, 80 %). Lead time e espera, sem referência no M1, usam
   limites de configuração marcados "provisório" (P-07).

## Consequências

- Continuidade com o M2 e aderência direta ao que a rubrica descreve.
- O Andon cinza sai quase de graça do contrato de dispositivo (status e `UltimaLeitura`).
- Há sobreposição com o Grafana da base; aceita.
- O laço de atualização do Streamlit é simples, mas não escala para muitos usuários; irrelevante para a demo.

## Alternativas consideradas

- **Só Grafana**: já existe na base, mas não tem what-if nem a busca de ficha no formato pedido, e afasta o projeto
  do padrão da disciplina.
- **FastAPI + React**: o "caminho avançado" das aulas; custo alto sem ganho na rubrica do M3.
- **Painéis dentro da planta 3D**: vistosos, exigem alterar a base.
