# Lições de processo — o que deu errado e como não repetir

Registro para consulta pontual do operador; não orienta o trabalho corrente. Arquivado em 2026-09-06.

## O storage local foi apagado por `git clean` (S8.4, 2026-09-06)

Durante a reorganização da raiz, `storage/` foi movido de `www/storage` para a raiz antes de o `.gitignore`
cobrir o destino novo; um `git clean -fdq` apagou tudo. A base foi reconstruída reimportando as quatro
bibliotecas pelo criador de catálogos (produtos e miniaturas voltaram); os downloads do plugin web de CAD
(`catallog/<importId>/`) não voltaram, porque refazê-los exigiria baixar de novo do catálogo do fabricante
sem autorização. Detalhe em `sessoes/S8.4-f4-servicos-com-dados-e-web.md` §6.

## Aceitação que só abre a biblioteca não prova nada (2026-09-08)

Duas aceitações manuais de `.aq` foram registradas como boas por **abrir** no AltoQi Builder: a árvore de
classes/grupos/peças correta, propriedades visíveis, acentos íntegros. Nenhuma das duas olhou a janela 3D
nem lançou a peça num projeto — e a `SIMBOLOGIA_3D.IMAGEM` faltando em todas as bibliotecas exportadas
passou meses sem ser vista, porque a peça sem `IMAGEM` mostra **todos os dados** e não desenha nada. O
sintoma só aparece no passo que ninguém dava. `docs/aceitacao.md` §4 agora exige os dois passos, e o
`validar_aq` acusa o campo. Lição geral: quando o critério de aceitação é "abriu", o que se prova é o
parser da outra ponta, não o produto — o critério tem de ser o uso final (aqui: a peça lançada no
projeto). Detalhe em `sessoes/2026-09-08-imagem-obrigatoria-o-aq-que-abria-e-nao-desenhava.md`.

## Teorizar sobre um formato binário sem experimento subtrativo (2026-09-08)

No mesmo defeito, o diff entre as nossas saídas e 16 bibliotecas nativas apontou cinco suspeitos, e
quatro eram falsos positivos — sentinela em `TIPO_CONFIGURACAO_GP`, `SIMBOLO_SELECIONADO` apontando para
tabela vazia, `PECA.BIBLIOTECA` preenchida, um nível a menos na árvore do OQ3D: tudo isso aparece em
nativas que funcionam. "Difere da nativa" não é prova de nada num formato proprietário. O que fechou em
uma rodada foi montar cópias de uma nativa que funciona apagando **um** campo por arquivo e pedir ao
usuário para abrir cada uma — mais um transplante de geometria nativa para o nosso cadastro, que separou
defeito de geometria de defeito de cadastro.

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

## "Difere da nativa" não é prova — e a lição reincide (2026-09-08 e 2026-09-09)

Comparar um arquivo nosso com um de fabricante produz uma lista de diferenças, e a maior parte
delas é irrelevante: sentinela, campo vazio e enum de valor incomum aparecem em nativa que
funciona. Em 2026-09-08 isso custou quatro falsos positivos; em 2026-09-09, outros quatro
(`SIMBOLO_SELECIONADO`, `INDICE_SIMBOLO3D_SELECIONADO`, dimensões na sentinela,
`POSICIONAR_SIMBOLOGIA_3D`) — todos descartados ao medir a **distribuição** do campo nas 15
nativas, e todos presentes em pelo menos uma que funciona. O que fecha o caso é experimento no
alvo (abrir no Builder um arquivo por hipótese) ou informação de quem opera a ferramenta. Medir a
distribuição antes de teorizar custa minutos; teorizar em cima de uma diferença custa a sessão.

## Um experimento natural vale mais que um arquivo fabricado

Antes de montar arquivo de teste para isolar um campo, vale procurar o par que **já existe** nos
dados: em 2026-09-09 a pergunta "o que desenha a planta" foi decidida por três nativas de
fabricante que já vinham em arranjos diferentes (uma só com wireframe, uma só com simbologia 2D),
sem fabricar nada. E a evidência tem de ser boa: uma das bibliotecas usadas como referência tinha
sido gerada a partir de PDF, o que o usuário sabia e o arquivo não dizia — sempre confirmar a
procedência de uma "verdade de campo" antes de construir argumento sobre ela.

## Otimizar sem oráculo quebra em silêncio

Trocar o agrupamento exato de triângulos coplanares por baldes quantizados (2026-09-09) deixou o
código igualmente rápido e **errado** — grupo que cruza a fronteira do balde sai partido — e
nenhum dos testes sintéticos acusou; o que acusou foi o placar contra as bibliotecas nativas, que
caiu de 10/16 para 7/16 numa delas. Antes de otimizar heurística geométrica, tenha uma medição de
qualidade rodando, não só testes de exemplo.
