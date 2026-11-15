# ADR-0014: Base e simulador como submódulos em commit fixado, por https, com LFS local

- Estado: Aceito (grupo, 2026-11-15)
- Data: 2026-11-15
- Origem: tarefas 0.1 e 0.5 da Fase 0; detalha o item 3 do ADR-0001; pendência P-06 (fork)

## Contexto

O ADR-0001 manda incluir o Virtual-Factory e o simulador do M2 como submódulos em commit fixado, a partir de um fork
do grupo. O Virtual-Factory guarda 184 arquivos em Git LFS (60 MB: modelos 3D, PNG, PDF, fontes); sem eles o
`provisioner` falha (`PIL.UnidentifiedImageError`, tarefa 0.3) e a peça não percorre a planta (tarefa 0.4). Na
Fase 0 o submódulo apontou para o repositório de origem (`aaronzi/Virtual-Factory`); o grupo criou o fork
`vitorramon/Virtual-Factory` em 2026-11-15.

## Decisão

1. `base/` → fork do grupo, `https://github.com/vitorramon/Virtual-Factory.git`, em
   `c558b9e98bdf71101e7a572f0fd921d9b9388adf` (o mesmo commit da origem; conferido com `git ls-remote`).
   `simulador/` → `https://github.com/vitorramon/GemeoDigitalCelulares.git` em
   `1e4b27d83524d02125b56ac7f909a5f2c4f65550`.
2. URLs https em `.gitmodules` (não ssh), para que um terceiro clone sem chave. Quem tiver permissão de escrita no
   fork pode usar ssh localmente (`git config submodule.base.url git@github.com:…` ou `pushurl`) sem mudar o
   `.gitmodules`.
3. O fork existe para garantir disponibilidade, não para modificar a base: o commit fixado continua sendo o da
   origem e o ADR-0001 (base intocada) vale igualmente para o fork.
4. LFS habilitado só no submódulo (`git -C base lfs install --local`), sem mexer no `~/.gitconfig` global; objetos
   baixados com `git -C base lfs pull`. git-lfs 3.7.1 do sistema (apt), instalado pelo usuário.
5. Atualizar o commit fixado é decisão registrada em PROGRESS (`.claude/rules/git.md`).

## Consequências

- O projeto deixa de depender de o repositório de origem continuar público.
- O README precisa pedir `git clone --recurse-submodules` e `git -C base lfs pull`; o git-lfs é pré-requisito do
  teste do terceiro.
- Os objetos LFS precisam estar disponíveis pelo fork (no GitHub, forks compartilham o armazenamento LFS da rede da
  origem); conferir na troca da URL e no teste do terceiro.
- `filter.lfs.*` e ganchos ficam em `.git/modules/base`: o git-lfs tem de estar no PATH (resolvido em 2026-11-15).

## Alternativas consideradas

- **Submódulo no repositório de origem**: usado na Fase 0; trocado pelo fork para não depender de terceiros.
- **Cópia dos arquivos da base no repositório**: dispensa submódulo e LFS, mas incha o repositório e perde o vínculo
  com a origem. Reserva se o fork e a origem saírem do ar.
- **URLs ssh no `.gitmodules`**: exigem chave do terceiro; descartado.
- **`git lfs install` global**: altera a configuração do usuário fora do projeto; descartado.
