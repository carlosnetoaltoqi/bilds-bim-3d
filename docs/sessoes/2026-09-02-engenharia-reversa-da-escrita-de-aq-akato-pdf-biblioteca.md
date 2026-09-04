# 2026-09-02 — Engenharia reversa da ESCRITA de `.aq` (Akato, PDF → biblioteca)

**Data:** 2026-09-02 · Registro **extraído do `CLAUDE.md`** em 2026-09-04 (S7.8, I22) — esta
sessão não tinha arquivo próprio; o texto abaixo é o que havia lá, sem alteração.

---

Terceira linha de trabalho, e a primeira que **escreve** `.aq` em vez de ler. Tudo em
`eng-reversa/`, que não altera o pipeline existente. Corpo completo em
`eng-reversa/README.md` e nos seis documentos de `eng-reversa/estudo/`.

**O que foi entregue.** PDF comercial da Akato (24 páginas) → `.aq` → catálogo
publicável com viewer 3D, atravessando o `build.py` do próprio projeto. 87 famílias,
**269 produtos**, 0 códigos repetidos, 0 linhas incompletas. Três variantes de `.aq`:
sem geometria (a fiel, 848 KB), com os 12 tubos (944 KB) e com forma paramétrica para
as 262 peças (6,8 MB). As três passam nas 20 checagens do `validar_aq.py`, que usa o
`read_aq.py` e o `oq3d.py` deste projeto sem modificação.

**Os quatro achados que mudaram este arquivo:**

1. **`PECA.DIAMETRO_PECA` é um CÓDIGO, não centímetro.** A skill 2.2.0 estava errada.
   `50 mm` → 9, `100 mm` → 12; e em 963 das 1.168 peças da Amanco o valor é a
   sentinela `-DBL_MAX`, com nenhuma das 700 conexões trazendo código. Corrigido aqui e
   na skill (2.3.0).
2. **O `.aq` declara UTF-8 e guarda cp1252** — o mecanismo por trás da armadilha de
   encoding já conhecida. Duas consequências novas: gravar exige
   `CAST(? AS TEXT)` com bytes cp1252, e **comparar literal acentuado dentro do SQL
   exige o mesmo**, senão a query volta vazia sem erro.
3. **O cabeçalho OQ3D tem, no offset 29, o número de objetos-raiz** — nunca
   documentado. Serve de verificação de parse, e revelou um defeito real: medido em
   todas as 783 geometrias de fabricante, o `oq3d.py` conta raízes a mais em **54
   (6,9%), em 6 das 12 bibliotecas** — Maxbar com 31 de 135. A diferença vai de +2 a
   +10 e não é sempre par.
4. **`saida` e `output` faltam em `_GENERIC_DIRS`** (`build.py:922`), então um `.aq`
   numa pasta chamada `saida/` publica com o título "Saida" — e a validação não acusa,
   porque "Saida" de fato é diferente do fabricante.

**Sobre validar geometria inventada.** O escritor OQ3D fecha round-trip contra o
`oq3d.py`, inclusive reescrevendo uma geometria real da Amanco vértice a vértice. Mas
round-trip, bounding box e contagem de triângulos **não pegam** duas classes de erro que
apareceram: perfil de revolução não soldado (`2 × lados` arestas de borda, 15 das 21
formas) e malhas corretas em posição relativa errada (colar de joelho solto, sifão
desmontado, 56 + 8 peças). A primeira se pega contando arestas; a segunda só abrindo o
preview e olhando — daí `eng-reversa/tools/olhar_preview.mjs`.

**ZIP.** `output/akato-construcao-civil-202609021348.zip`, 2.775 KB, conforme em 17 de
17 itens de `docs/bilds-bim-3d-zip-spec.md`, com 262 miniaturas WebP.

**Correções que este estudo levou ao código, no mesmo dia:**

- `read_aq.build_product_map()` — `diametro_cm` → `diametro_codigo`, e as quatro chaves
  numéricas passam por `_sem_sentinela()`: antes o mapa entregava `-1.8e308` como medida;
- `oq3d.parse()` — `n_raizes_declarado()` lê o campo do offset 29 e o parse avisa com
  `OQ3DAvisoParse` na divergência;
- `build._GENERIC_DIRS` — `saida`, `output`, `out`, `dist`, `build`.

**O que segue em aberto:** a simbologia 2D (`CONTEUDO_SIMBOLOGIA`) e o `WIREFRAME`
**não foram decifrados** — um `.aq` gerado não tem representação em planta —, e a causa
das 54 divergências de contagem de raízes do OQ3D é conhecida por sintoma, não por
mecanismo. **Fechado depois (registrado na S7.5):** o `.aq` da Akato **abriu no AltoQi
Builder** em 2026-09-02, com propriedades personalizadas e acentos corretos — ver
"Escrever um `.aq`" acima.
