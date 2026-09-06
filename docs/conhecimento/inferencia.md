# Inferência de fabricante, título, slug e layout

O que um catálogo publicado mostra no cabeçalho — fabricante e título — e como se organiza — layout —
não é perguntado a ninguém: sai do próprio `.aq` e do caminho do arquivo. É a cascata de
`biblioteca/bim_pipeline/catalogo/inferencia.py`, usada pelo criador de catálogos em todo upload e
pelo modo lote da CLI de ZIP. Para quem precisa entender por que um catálogo saiu com um nome e não
outro, ou ajustar a cascata.

## A regra que manda em tudo

**Fabricante e título nunca podem sair vazios nem em forma de slug.** São o cabeçalho da página
publicada. Cada degrau da cascata só é tentado quando o anterior não produz algo legível, e o último
degrau sempre produz.

## Fabricante — em ordem de confiança

1. Prefixo de `CLASSE_SIMBOLOGIA_3D.NOME_CLASSE`, no padrão `"FABRICANTE - Linha de Produto"`. É a
   fonte mais confiável: o Builder grava o fabricante em caixa alta antes do ` - ` e a biblioteca o
   recapitaliza (`FABRICANTE` → `Fabricante`, preservando palavras que já vêm com caixa mista).
2. `PECA.BIBLIOTECA` — era a fonte primária antiga e está **vazia em toda biblioteca real
   examinada**. Fica como degrau, não como aposta.
3. Pasta avó do arquivo, quando é descritiva (não é `input`, `bibliotecas`, `downloads`, `tmp`… — a
   lista de nomes genéricos está em `_GENERIC_DIRS`).
4. Pasta mãe, quando coincide com o primeiro token do nome do arquivo.
5. Primeiro token significativo do nome do arquivo.

## Título — em ordem

1. Pasta mãe, quando descritiva e diferente do fabricante (`<fabricante>/<linha>/pecas.aq`).
2. Tokens do nome do arquivo menos o fabricante e menos o ruído (`pecas`, `biblioteca`, `bim`,
   `catalogo`…), com o case original preservado — siglas continuam em caixa alta, CamelCase é
   separado em palavras. Exceção: se o único token restante é um bloco todo-minúsculo com mais de
   10 caracteres (palavra composta sem separador), o degrau é pulado — viraria um título ilegível.
3. Prefixo comum dos nomes de grupo do banco (`infer_titulo`): `['Bombas X CAM-1', 'Bombas X CAM-2']`
   → `'Bombas X'`. Catálogo heterogêneo dá prefixo curto → vazio → próximo degrau.
4. Último recurso: o próprio fabricante.

Um upload chega com nome temporário (`bim-<uuid>.aq`); por isso a cascata recebe `nome_original`,
o nome que o usuário deu ao arquivo, e usa esse — nunca o temporário.

## Slug e layout

- **Slug** = `slugify(titulo)`: NFD, remove acentos, minúsculas, tudo que não é `[a-z0-9]` vira `-`.
  É o mesmo `slugify` de toda a biblioteca (um só, em `catalogo/catalogo.py`) — é dele que saem os
  nomes dos arquivos de geometria também, então mudar a função muda chaves de storage.
- **Layout**: `series-rows` quando a biblioteca tem curvas Q-H (famílias com variantes — bombas);
  senão `catalog-grid` acima de 6 peças (muitos itens heterogêneos com filtros — conexões); senão
  `series-rows`. Só o operador do lote pode forçar (`--layout`).

## Descrição e geometria

Descrição não tem fonte automática (fica vazia; a API de catálogo permite editar). Geometria nunca é
inferida: vem por chave estrangeira (`PECA_SIMBOLOGIA_3D`) — ver `aq-formato.md`.

## Armadilhas

- Uma pasta chamada `saida/`, `output/`, `dist/`, `uploads/` já foi tomada como título de catálogo:
  qualquer pasta genérica nova precisa entrar em `_GENERIC_DIRS`.
- O modo lote infere o slug **da pasta**, não do nome do arquivo, quando a pasta mãe é descritiva —
  um teste que espera o slug "do arquivo" quebra.

## Onde está no código

`biblioteca/bim_pipeline/catalogo/inferencia.py` (`peek_aq`, `auto_config`, `infer_titulo`,
`layout_para`, `find_aq_paths`); `catalogo/catalogo.py` (`slugify`, `tokenize`);
`aq/read_aq.py` (`peek_metadata`, que só devolve as classes crus). Testes em
`tests/biblioteca/test_catalogo.py` (fixture `aq_pequena`).

## Ver também

`aq-formato.md` (onde o fabricante mora no banco), `catalogo-modelo.md` (o que o criador faz com o
resultado), `zip-bilds-formato.md` (onde título e fabricante aparecem no pacote).
