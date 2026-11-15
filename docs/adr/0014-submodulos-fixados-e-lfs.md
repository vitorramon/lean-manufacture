# ADR-0014: Base e simulador como submódulos em commit fixado, por https, com LFS local

- Estado: Proposto
- Data: 2026-11-15
- Origem: tarefas 0.1 e 0.5 da Fase 0; detalha o item 3 do ADR-0001

## Contexto

O ADR-0001 manda incluir o Virtual-Factory e o simulador do M2 como submódulos em commit fixado, a partir de um fork
do grupo (P-06). O fork ainda não existe. O Virtual-Factory guarda 184 arquivos em Git LFS (60 MB: modelos 3D,
PNG, PDF, fontes); sem eles o `provisioner` falha (`PIL.UnidentifiedImageError`, tarefa 0.3) e a peça não percorre
a planta (tarefa 0.4). O git-lfs não está instalado no sistema.

## Decisão

1. `base/` → `https://github.com/aaronzi/Virtual-Factory.git` em `c558b9e98bdf71101e7a572f0fd921d9b9388adf`;
   `simulador/` → `https://github.com/vitorramon/GemeoDigitalCelulares.git` em
   `1e4b27d83524d02125b56ac7f909a5f2c4f65550`. URLs https (não ssh), para que um terceiro clone sem chave.
2. Enquanto o fork do grupo não existir, `base/` aponta para o repositório de origem. Ao criar o fork (P-06), trocar
   a URL em `.gitmodules` e registrar em PROGRESS.
3. LFS habilitado só no submódulo (`git -C base lfs install --local`), sem mexer no `~/.gitconfig` global; os
   objetos são baixados com `git -C base lfs pull`.
4. Atualizar o commit fixado é decisão registrada em PROGRESS (`.claude/rules/git.md`).

## Consequências

- Reprodutível: os dois commits estão nos remotos públicos (`git ls-remote`, tarefa 0.1).
- O README precisará pedir `git clone --recurse-submodules` e `git lfs pull` em `base/`; o git-lfs passa a ser
  pré-requisito do teste do terceiro.
- O `lfs install --local` grava `filter.lfs.*` e ganchos em `.git/modules/base`: sem git-lfs no PATH, tocar um
  arquivo LFS do submódulo quebra `git status`. Hoje o git-lfs usado foi um binário de usuário temporário; falta a
  instalação permanente (pendência do usuário).
- Apontar para o repositório de origem depende de ele continuar público.

## Alternativas consideradas

- **Cópia dos arquivos da base no repositório**: dispensa submódulo e LFS, mas incha o repositório e perde o vínculo
  com a origem. Fica como reserva se o repositório de origem sair do ar (ADR-0001).
- **URLs ssh**: exigem chave do terceiro; descartado.
- **`git lfs install` global**: altera a configuração do usuário fora do projeto; descartado.
