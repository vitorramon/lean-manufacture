# ADR-0012: Compose adicional sobre a base e `start.py` como entrada única

- Estado: Proposto
- Data: 2026-11-15
- Origem: aulas M2.A5 e M3.A4; lacuna do M2 (sem orquestrador)

## Contexto

A disciplina exige um orquestrador (`start.py`) que suba os processos na ordem certa, verifique a saúde e reinicie
o que cair, e avalia a reprodutibilidade pelo "teste do terceiro". O M2 tem só scripts de Windows. O Virtual-Factory
sobe por Docker Compose, com dependências e verificações de saúde próprias, e pede a planta Godot rodando no
computador hospedeiro.

## Decisão

1. Os serviços do M3 são descritos num arquivo compose adicional (`infra/docker-compose.lean.yml`), aplicado sobre
   o compose da base, sem editá-lo.
2. A Fase 0 define um **perfil reduzido**: só os serviços da base de que o M3 precisa.
3. `start.py` é a única entrada: confere pré-requisitos, sobe o compose, espera a saúde dos serviços, inicia a
   fonte de estímulo escolhida (`--fonte`), abre o dashboard e passa a monitorar.
4. Monitoramento em três níveis, como na aula: processo vivo, porta respondendo, dado fluindo (contagem crescente
   no banco).
5. A planta Godot é opcional: só a fonte `godot` precisa dela. As demais rodam sem Godot.
6. O caminho padrão do README usa a fonte que exigir menos instalação.

## Consequências

- Um comando para a demo e para o terceiro; o terminal do orquestrador com os registros de saúde é evidência.
- Docker passa a ser pré-requisito obrigatório.
- Atualizações da base podem quebrar o arquivo adicional; o commit fixado (ADR-0001) limita esse risco.
- Em WSL2 com Docker Desktop, portas e acesso a dispositivos USB têm particularidades a verificar na Fase 0.

## Alternativas consideradas

- **`start.py` com subprocessos, sem contêineres**, como no slide: não gerencia a base, que já é em contêineres.
- **Só Docker Compose, sem `start.py`**: contraria a estrutura de repositório pedida e não inicia a fonte de
  estímulo nem o Godot.
- **Copiar e editar o compose da base**: liberdade total, ao custo de divergir da base.
