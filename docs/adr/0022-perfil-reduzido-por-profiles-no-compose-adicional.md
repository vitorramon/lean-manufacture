# ADR-0022: Perfil reduzido da base por `profiles` no compose adicional

- Estado: Proposto
- Data: 2026-11-15
- Origem: tarefa 1.6 do PLAN; complementa o item 2 do ADR-0016 (Aceito), que segue valendo nos itens 1 e 3

## Contexto

O ADR-0016 fixou o perfil A (8 serviços da base) e, no item 2, a forma "lista explícita de serviços no
`docker compose up`", reproduzida pelo `start.py`. A alternativa `profiles` num override ficou "não testada;
reavaliar na tarefa 1.6". Na 1.6 o compose adicional `infra/docker-compose.lean.yml` passou a existir (ADR-0012),
com `device-gateway` e `aas-sync`; com a lista explícita, cada comando precisaria repetir os 8 nomes mais os 2 do M3.

## Decisão

1. O compose adicional põe os 19 serviços da base fora do perfil A no profile `base-completa`. Sem `--profile`,
   `docker compose -f base/infra/docker-compose.yml -f infra/docker-compose.lean.yml up` sobe só os 8 do perfil A e
   os 2 do M3. A pilha completa volta com `--profile base-completa`.
2. Os 19 entram juntos: o Compose recusa um serviço sem profile que dependa de um com profile (`resolver` depende de
   `dpp-api`).
3. A lista explícita do ADR-0016 continua documentada para subir só a base (`infra/README.md`).
4. O compose da base não é editado (ADR-0001): os profiles vêm só do override.

## Consequências

- Testado na 1.6 (`docs/evidencias/f1-1.6-start.md`): `config --services` lista exatamente os 8 + 2; `up` a frio em
  52,0 s e 34,0 s; com a base no ar, 30,5 s.
- O `start.py` usa um único comando de `up` e de `down`.
- Se a base acrescentar um serviço novo, ele sobe por padrão até ganhar o profile no override: atualizar o
  submódulo exige conferir `config --services` (registrar em PROGRESS, ADR-0014).
- Cada `up` reexecuta `basyx-config` e `provisioner` (serviços de execução única da base).

## Alternativas consideradas

- **Lista explícita (forma do ADR-0016, item 2)**: funciona, mas cada comando repete 10 nomes; fica só para a base
  sozinha.
- **Profile só em `dpp-api` e serviços isolados**: falha pela dependência `resolver` → `dpp-api`.
- **Editar o compose da base**: proibido pelo ADR-0001.
