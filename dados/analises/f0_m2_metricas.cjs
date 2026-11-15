// Auxiliar da tarefa 0.7: calcula os KPIs com o PRÓPRIO metrics.js do simulador do M2.
// Não reimplementa fórmula nenhuma: chama buildMetrics(events, stations, costs, lineIdealCycle).at(end),
// do mesmo jeito que painel.html e comparacao.html fazem.
// Uso: node f0_m2_metricas.cjs <caminho/metrics.js> < entrada.json > saida.json
// Entrada: {"cenarios":[{"nome","events":[{t,p,s,e,r}],"stations":[...],"costs":{...},"line_ideal_cycle":20,"end":28800}]}
const fs = require('node:fs');
const path = require('node:path');
const metricsPath = path.resolve(process.argv[2] || 'metrics.js');
const { buildMetrics } = require(metricsPath);
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const out = input.cenarios.map(c => {
  const engine = buildMetrics(c.events, c.stations, c.costs, c.line_ideal_cycle);
  const m = engine.at(c.end);
  return {
    nome: c.nome, end: c.end,
    iniciadas: m.total, concluidas: m.p, retidas_reprovadas: m.bad, wip: m.w,
    fpy: m.q, rty: m.r, oee: m.oee, oee_disponibilidade: m.oeeAvailability,
    oee_desempenho: m.oeePerformance, oee_qualidade: m.oeeQuality,
    um_menos_copq: m.costScore, custo_nao_qualidade: m.c,
    teste_total: m.testTotal, teste_aprovadas: m.testGood, teste_reprovadas: m.testRejected,
    lead_time_min_metricsjs: m.p ? m.lead / 60 : null,
    fila_media: m.queueMean, fila_maxima: m.queueMax, rejeicoes: m.rejects
  };
});
process.stdout.write(JSON.stringify({ metrics_js: metricsPath, cenarios: out }, null, 2));
