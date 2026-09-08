# 2026-09-08 — A `IMAGEM` obrigatória: o `.aq` que abria e não desenhava

**Data:** 2026-09-08 · **Sessão do plano:** — (sessão de defeito, fora do plano) · **Status:** concluída
**Commits:** `85b7ba2`, `2b74e15`, `68d5f1e`

---

## 1. O que era para fazer

O usuário abriu a sessão com o defeito: "os catálogos importados em IFC, Revit ou outros formatos,
quando exportados para `.aq`, não estão mostrando a geometria das peças no AltoQi Builder, apenas as
informações aparecem. Os arquivos exportados têm tamanho em MB suficiente para indicar que a geometria
está lá." Com prints do diálogo Cadastro → Peças. Pronto quando: causa isolada, corrigida no pipeline,
com as bibliotecas já exportadas utilizáveis.

## 2. O que foi feito

- `biblioteca/bim_pipeline/aq/imagem_aq.py` — novo. Rasteriza `SIMBOLOGIA_3D.IMAGEM` (BMP 100×100,
  24 bits, 30.054 bytes) a partir de `malhas`, **o mesmo argumento de `oq3d_writer.escrever`**. numpy
  puro: base de câmera isométrica (azimute 35°, elevação 20°) sobre a geometria Z-up do OQ3D, z-buffer
  por lista de trabalho (cada triângulo entra pelos pixels da sua bbox; a profundidade se resolve
  empacotando `(profundidade, índice)` num int64 e ordenando), sombreamento plano pela normal da face.
- `saida/geo_to_aq.py` e `saida/catalogo_to_aq.py` — passam a gravar `IMAGEM` no insert de
  `SIMBOLOGIA_3D`; as duas listas de "o que fica de fora" foram corrigidas.
- `cli/ferramentas/validar_aq.py` — duas checagens novas (item 7): toda simbologia tem `IMAGEM`; o BMP
  está no formato dos nativos. Helper `bmp_nativo()`.
- `cli/ferramentas/preencher_imagem_aq.py` — novo. Preenche a `IMAGEM` num `.aq` **já exportado**,
  rasterizando o OQ3D que está no próprio arquivo (`--saida` para copiar, `--refazer` para sobrescrever).
- `tests/biblioteca/test_imagem_aq.py` — 6 testes. Coleta total: 201 → 207.
- Documentação: ADR-020; `aq-formato.md` (tabela do experimento + seção "é requisito do Builder");
  `aq-escrita.md` (seção da `IMAGEM`, ferramentas, "o que só o Builder pode dizer" reescrito);
  `diagnostico.md` (sintoma novo, primeira linha da tabela do `.aq`); `aceitacao.md` §4 (dois passos);
  `CONCEPTS.md`; `biblioteca/README.md`; skill `leitor-biblioteca-aq` 2.10.0 → 2.11.0; `CLAUDE.md`.

## 3. O que foi verificado — e como

O diagnóstico foi feito por **experimento subtrativo no Builder**, porque nenhuma leitura do arquivo
distingue "campo diferente da nativa" de "campo que o Builder exige" — sentinela e campo vazio aparecem
em nativas que funcionam. Seis arquivos foram montados a partir de uma nativa que funciona (aquecedores,
schema 582) e de uma nossa (conexões, 607), e o usuário abriu cada um:

| | `IMAGEM` | `WIREFRAME` | entradas | geometria | desenha? |
|---|---|---|---|---|---|
| A | sim | sim | sim | nativa | **sim** (linha de base) |
| B | — | — | — | nativa | não |
| C | sim | sim | — | nativa, no **nosso** cadastro | **sim**, só na peça transplantada |
| D | — | sim | — | nativa, no nosso cadastro | não |
| E | sim | — | — | nativa, no nosso cadastro | **sim** |
| F | gerada por `imagem_aq` | — | — | **nossa** | **sim**, e lança no projeto |

D contra E isola o campo. C absolve `PECA`/`GRUPO_PECA` (o Builder desenhou dentro da nossa biblioteca)
e mostra que entradas não são necessárias (o transplante não levou nenhuma). F é a prova da correção: o
print do usuário mostra a peça lançada no ambiente 3D com a malha real.

Antes disso, o levantamento que apontou o suspeito: as 16 nativas de
`/mnt/c/Users/carlos.neto/Documents/BIM/` contra as nossas quatro saídas — `IMAGEM` e `WIREFRAME`
preenchidos em praticamente toda simbologia nativa e nulos em 100% das nossas; `ENTRADA_PECA`/`ENTRADA_3D`
presentes nas nativas menos duas.

Suíte: `pytest tests/biblioteca tests/arquitetura -m "not thumbs"` → 139 passaram, 19 pularam (fixtures
locais ausentes). Coleta total 207. As quatro bibliotecas de 2026-09-08 corrigidas com
`preencher_imagem_aq` passam no `validar_aq`, inclusive a de 1.399 simbologias (42 s).

## 4. Decisões tomadas

- **ADR-020**: a `IMAGEM` é obrigatória e sai de um rasterizador em software, não do harness de
  miniaturas (Chromium + Three.js). Motivo: é requisito do formato, tem de sair no mesmo processo que
  escreve o `.aq` e no CI, onde não há navegador; a ~2 s de Chromium por peça um pacote de 1.399
  simbologias não fecha (em numpy são 42 s).
- Consertar as bibliotecas já exportadas com uma ferramenta (`preencher_imagem_aq`) em vez de exigir
  reimportação, que depende de serviços e Atlas de pé.
- `aceitacao.md` §4 passa a exigir a peça lançada num projeto. Abrir a biblioteca não prova nada.

## 5. O que NÃO foi feito, e por quê

- **`WIREFRAME`** (arestas de planta/corte) e **`ENTRADA_PECA`/`ENTRADA_3D`** (bocais): fora de escopo,
  agora com prova de que a peça desenha em 3D sem os três. São os itens 1 e 2 da sessão seguinte, por
  decisão do usuário.
- Caminhos abandonados no diagnóstico, para a próxima sessão não repetir: **versão de schema** (a nossa é
  607 e há nativa 615 que abre); **`TIPO_CONFIGURACAO_GP` com sentinela** `-2147483647` (aparece em
  nativas que funcionam); **`SIMBOLO_SELECIONADO = 1` apontando para `SIMBOLOGIA` vazia** (idem);
  **`PECA.BIBLIOTECA` preenchida** (idem); **o nível `TQi3DObjectGroup`** que as nativas têm no OQ3D e a
  nossa árvore não — falso positivo, o teste F desenhou sem ele.
- Não se investigou a `pecas_akato_construcao_civil_v2.aq`, que é nossa (assinatura: `BIBLIOTECA`
  preenchida, sentinelas do `geo_to_aq`) e tem `IMAGEM` nas 262 simbologias com os blobs OQ3D idênticos
  aos da v1 — provavelmente uma ida e volta pelo "Exportar…" do Cadastro. Ficou como curiosidade.

## 6. Surpresas — onde a documentação estava errada

- `aq-escrita.md` listava `IMAGEM` e `WIREFRAME` juntos, como "o que fica de fora, porque o catálogo não
  tem de onde tirar". Era falso para a `IMAGEM`: ela se gera da própria malha, e sem ela o arquivo é
  inútil. **Corrigido nas duas listas** (`geo_to_aq` e `catalogo_to_aq`) e no docstring dos dois módulos.
- `aq-formato.md` descrevia a `IMAGEM` como "BMP 100×100 24-bit pré-renderizado", sem dizer que é
  requisito. **Corrigido**, com a tabela do experimento.
- A seção "O que só o Builder pode dizer" registrava duas aceitações manuais — e admitia que nenhuma das
  duas olhou a janela 3D nem lançou a peça. Era exatamente a brecha por onde o defeito passou.
  **Reescrita** com a aceitação de 2026-09-08 e o que segue sem prova.

## 7. Onde a próxima sessão começa

Itens 1 e 2, nesta ordem de risco (decisão do usuário ao encerrar):

1. **`WIREFRAME`** — o que o CAD desenha em planta e corte. O formato não está revertido. O que se sabe:
   é um blob próprio, distinto do OQ3D, cujo primeiro nome de classe é `T3DWireframeGenerator::TEdge`
   (prefixo de tamanho `u32` antes do nome, como no OQ3D — a mesma serialização Delphi que o
   `oq3d_writer.py` já emite); ~70% do arquivo numa nativa; ~641 KB para uma simbologia cuja malha tem
   507 KB. Ferramenta para dissecar: `ferramentas.oq3d_anatomy` serve de modelo, mas é preciso um
   equivalente para o wireframe. **Antes de reverter, medir se vale**: conferir no Builder se uma peça
   nossa (já com `IMAGEM`) aparece ou não em planta e corte — talvez o Builder derive as arestas da malha
   e o `WIREFRAME` seja só cache. Esse teste custa minutos e pode dispensar o item inteiro.
2. **`ENTRADA_PECA` / `ENTRADA_3D`** — bocais e conectividade. Sem elas o Cadastro mostra "Pontos de
   ligação 3D: Não" e a peça não encaixa numa tubulação. `ENTRADA_PECA(LIGACAO_EP, DIAMETRO_EP, SECAO_EP,
   COMPRIMENTO_EP, ANGULO_EP, BASE_EP, ALTURA_EP, ID_PECA)` e `ENTRADA_3D(POSICAO_X/Y/Z,
   ID_SIMBOLOGIA_3D)`, com `DIAMETRO` só no schema 607; numa nativa de aquecedores são 2 entradas por
   peça (`LIGACAO_EP` 0 e 1, `ANGULO_EP` 0 e 360). O difícil não é o schema: é **de onde tiram as
   posições** — um IFC/STEP não marca bocal. Candidatos: os `MEPConnector` das famílias Revit (verificar
   se o PartAtom ou o IFC traduzido os traz), a heurística de tampas de cilindro na malha, ou entrada
   manual no editor de peças.

Antes de começar: nada precisa estar de pé para o item 1 (é leitura de `.aq` e teste no Builder). Para o
item 2, se o caminho for Revit, as fixtures `rfa_familias`/`rvt_projeto` de `tests/fixtures.local.json`
precisam existir em `input/`.

Armadilhas encontradas nesta sessão e que a próxima vai encontrar: `sqlite3` do Python decodifica TEXT
como UTF-8 e **estoura** em nome acentuado de nativa (`text_factory = bytes` e `CAST(? AS TEXT)` com
bytes cp1252 na volta — a armadilha documentada mordeu de novo, no meu script de etiquetagem); e a regra
ADR-016 vale para docstring de código também (o `test_sem_empresas` pegou um nome de fabricante que eu
tinha escrito no docstring do `imagem_aq.py`).

## 8. Estado verificável ao encerrar

| O quê | Estado | Como conferir |
|---|---|---|
| `main` local | 3 commits à frente do `origin/main` | `git rev-list --count origin/main..HEAD` → 3 |
| árvore | limpa | `git status --short` |
| suíte | 207 na coleta; 139 passam, 19 pulam | `python3 -m pytest tests/biblioteca tests/arquitetura -m "not thumbs" -q` |
| `IMAGEM` na escrita | ligada nos dois caminhos | `grep -n IMAGEM biblioteca/bim_pipeline/saida/*.py` |
| bibliotecas do usuário | 4 corrigidas, todas passando | `Downloads/teste-geometria-aq/CORRIGIDO_*.aq` + `ferramentas.validar_aq` |
| arquivos do experimento | A–F preservados | `Downloads/teste-geometria-aq/` |
