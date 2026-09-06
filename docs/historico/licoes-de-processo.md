# Lições de processo — o que deu errado e como não repetir

Registro para consulta pontual do operador; não orienta o trabalho corrente. Arquivado em 2026-09-06.

## O storage local foi apagado por `git clean` (S8.4, 2026-09-06)

Durante a reorganização da raiz, `storage/` foi movido de `www/storage` para a raiz antes de o `.gitignore`
cobrir o destino novo; um `git clean -fdq` apagou tudo. A base foi reconstruída reimportando as quatro
bibliotecas pelo criador de catálogos (produtos e miniaturas voltaram); os downloads do plugin web de CAD
(`catallog/<importId>/`) não voltaram, porque refazê-los exigiria baixar de novo do catálogo do fabricante
sem autorização. Detalhe em `sessoes/S8.4-f4-servicos-com-dados-e-web.md` §6.

## Uma suíte "verde" com menos testes do que deveria (S8.5)

Uma exclusão de diretório do coletor (`norecursedirs` com `biblioteca`) casou com `tests/biblioteca/` e 71
testes deixaram de ser coletados; a suíte passava. Só a contagem de coleta denuncia — conferir quantos
testes rodaram depois de mexer na configuração do pytest.

## Histórico git reescrito (S7.5, 2026-09-03)

O histórico do `main` foi reescrito para remover dados de fabricante; um clone anterior a essa data não faz
`pull` — precisa clonar de novo. Mapa antigo → novo em `sessoes/S7.5-push-e-reescrita-do-historico.md`.

## `git clean -fdq` apaga o que ainda não está no `.gitignore`

`git clean -fdq` remove todo arquivo não rastreado que o `.gitignore` **atual** não cobre — se um
diretório de dados foi movido para um novo lugar (por um script de migração, por exemplo) mas o
`.gitignore` ainda aponta para o caminho antigo, o diretório novo fica sem proteção nenhuma e é
apagado junto com o lixo que o comando pretendia limpar. A ordem correta é: mover dados só depois
de o `.gitignore` já cobrir o destino novo, e conferir `git status`/`git clean -ndq` (dry-run)
antes de rodar a versão que de fato apaga.

## `git mv` de diretório para destino existente move para dentro

`git mv origem/ destino/` quando `destino/` **já existe** não funde nem substitui — move `origem/`
para dentro de `destino/`, resultando em `destino/origem/` em vez do `destino/` esperado. Uma
rodada anterior de um script de reorganização que deixou o destino já criado (com `node_modules`
dentro, por exemplo) faz a rodada seguinte empilhar um diretório dentro do outro sem erro nenhum
— o comando "funciona", só que não do jeito pretendido. Limpar (ou renomear) o destino antes de
repetir a operação evita o aninhamento.
