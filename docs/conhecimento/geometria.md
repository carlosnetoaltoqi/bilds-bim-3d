# Geometria — o contrato `{pos, col, idx}`

O contrato que todo conversor da biblioteca produz e todo viewer consome. Schema em
`biblioteca/bim_pipeline/contratos/geometria.schema.json`.

## O contrato

```json
{
  "pos": [x0, y0, z0, x1, y1, z1, ...],
  "col": [r0, g0, b0, r1, g1, b1, ...],
  "idx": [0, 1, 2, 0, 2, 3, ...]
}
```

| Campo | Conteúdo |
|---|---|
| `pos` | posições de vértice, array flat, **3 floats por vértice**, em **metros, Y-up** |
| `col` | cor por vértice, array flat, RGB normalizado em `[0, 1]`, **ou vazio** (`[]` = sem cor — viewer usa cinza padrão) |
| `idx` | índices de triângulo, array flat, 3 por triângulo |

`pos.length` é sempre múltiplo de 3. Quando `col` está presente, `col.length == pos.length`
(uma cor por vértice, não por face). O schema aceita ainda metadados opcionais que os
conversores anexam — ver final deste documento.

**Y-up, metros** é a convenção do Three.js e a única que o viewer entende. Toda fonte é
Z-up e numa unidade diferente: a conversão de eixos é obrigatória, nunca opcional.

## Conversões de eixos e unidades

Regra geral (`biblioteca/bim_pipeline/geometria/eixos.py`): a permutação de eixos é
sempre a mesma — só a escala muda por formato de origem.

| Origem | Unidade/orientação nativa | Para o viewer (metros, Y-up) |
|---|---|---|
| OQ3D (`.aq`) | centímetros, Z-up | `(x, z, −y) · 0,01` |
| STEP / IGES (via OpenCASCADE) | milímetros, Z-up | `(x, z, −y) · 0,001` |
| IFC | metros, Z-up | `(x, z, −y)` |

E de volta, escrevendo OQ3D a partir do viewer:

```
oq3d_x =  three_x · 100
oq3d_y = −three_z · 100
oq3d_z =  three_y · 100
```

Regra única, em ambos os sentidos:

```
Z-up  → viewer   (x, y, z) → (x,  z, −y) · escala
viewer → Z-up    (x, y, z) → (x, −z,  y) · escala
```

Todas as funções vivem em `eixos.py` em três formas (escalar, lista plana, numpy) para que
nenhum leitor (`oq3d`, `step_iges`, `parse_ifc`) nem escritor (`geo_to_aq`,
`catalogo_to_aq`) repita a permutação do seu próprio jeito.

**O fator de escala é o erro mais fácil de cometer.** OQ3D grava em centímetros — ao
contrário do IFC, que já vem em metros na maioria dos exportadores. Esquecer o `× 0.01`
(ou aplicá-lo a uma fonte que já está em metros) produz um modelo 100× do tamanho
correto. Alguns exportadores IFC (CATIA) declaram `MILLIMETRE` no `IFCSIUNIT` mas gravam
em metros de fato — confira a magnitude antes de confiar na unidade declarada:
equipamento industrial plausível em metros fica na faixa 0,01–5,0.

## Dedup — por que e como

O OQ3D indexa dentro de cada malha, mas malhas de uma mesma peça repetem vértices entre
si; geometria expandida (cor por face, sem `idx`) tem ainda mais repetição. Deduplicar
reduz **~80%** dos vértices — um conjunto de catálogos foi de 148 MB para 571 MB de JSON
sem essa etapa.

**A chave é a posição quantizada em float32 (a precisão do `Float32BufferAttribute` do
Three.js) MAIS a cor**, nunca só a posição:

```python
key = (q(px), q(py), q(pz), q(cr), q(cg), q(cb))   # correto
key = (q(px), q(py), q(pz))                        # perde cor em fronteiras de material
```

Sem a cor na chave, dois vértices na mesma posição com cores diferentes — a fronteira
entre o corpo vermelho e o logo branco de uma bomba, por exemplo — seriam fundidos e uma
das cores desapareceria.

**Efeito colateral deliberado:** como a cor entra na chave, triângulos de cores
diferentes **nunca compartilham vértice**. É isso que permite ao editor re-segmentar uma
malha em Partes por componente conexo — sem essa separação de cor, peças de cores
diferentes coladas na mesma posição virariam um componente só.

O dedup **não solda costuras de malha de fabricante**: vértices a µm de distância
continuam distintos (só a quantização por float32 os aproxima, não uma tolerância
geométrica deliberada). E `-0.0` e `0.0` são chaves distintas — bits diferentes em
float32, comparados como bytes, não como valor — então não colapsam por acidente. Ordem
de saída: a da primeira ocorrência (estável).

A alternativa ao índice é expandir os vértices e **omitir `idx`** — obrigatório quando a
cor é por face e não por malha (o caso do `IFCINDEXEDCOLOURMAP` do caminho IFC, onde um
vértice compartilhado entre duas faces de cores diferentes é genuinamente ambíguo).
Geometria expandida custa ~5× mais bytes; prefira indexada sempre que a cor for uniforme
por malha — é o caso do OQ3D.

Referência: `biblioteca/bim_pipeline/geometria/dedup.py` (`dedup_arrays`, `dedup`).

## Malhas por cor — o caminho inverso, para escrever OQ3D

O OQ3D só tem **cor por malha**; o viewer tem cor por vértice. A regra usada pelos dois
escritores de `.aq` (peça avulsa e catálogo inteiro): a cor de um triângulo é a do seu
**primeiro vértice**, arredondada a 4 casas; triângulos da mesma cor viram uma malha, com
os vértices reindexados; tudo convertido para centímetros Z-up antes de gravar.
Referência: `biblioteca/bim_pipeline/geometria/malhas.py` (`malhas_por_cor`,
`malhas_de_partes`).

## Parte e Bake

**Parte** é a unidade de edição no editor 3D: `{pos, col, idx, matrix, visible, marker}`,
nascida da re-segmentação da malha em componentes conexos — funciona porque o dedup
separa vértices por cor. Parte oculta não é salva.

**Bake** é aplicar as matrizes das partes visíveis, concatenar tudo, arredondar a 1 µm e
deduplicar com a mesma quantização do import (posição + cor). É o que salvar, exportar
IFC e exportar `.aq` fazem antes de escrever — a mesma operação de dedup usada na
importação, reaplicada na saída.

## Bocais

Marcador de ponto de conexão do AltoQi dentro da geometria OQ3D (cores fixas verde e
azuis — ver `oq3d.md`). Não é produto: fica fora do bbox da peça e vira `marker` no
editor, nunca uma Parte editável.

## Arestas de borda — métrica só em malha gerada

Uma aresta de borda é uma aresta compartilhada por **um só** triângulo (normal seria
exatamente dois — a malha é "fechada" ali). Em **malha de fabricante** (OQ3D ou STEP
tesselado por terceiros) ter arestas de borda é normal: 25–32% é a faixa observada, e não
indica defeito — a tesselação de fabricante não é estanque. Esse critério só vale como
alarme em **sólidos gerados ou costurados** por este projeto (uma forma representativa
paramétrica, uma malha costurada de IGES): aí o número esperado é **zero**, e qualquer
aresta de borda sinaliza um perfil que fecha em si mesmo sem soldar o último anel no
primeiro — um sólido que parece fechado e mostra o interior pela costura.

## Metadados opcionais dos conversores

O schema aceita campos além de `pos`/`col`/`idx`, que os conversores anexam conforme a
origem: `partes` (nome, cor, contagem de triângulos — quando a fonte já vem segmentada),
`unidade`, `bbox_mm`, `fonte`, `deflexão_mm` e `escala_aplicada` (STEP/IGES), `cor_por_face`
(IFC), `formato` (`step` | `iges` | `ifc`), `caminho`, `tamanho_mb`, `aviso`, e para
sólidos gerados/costurados `volume_cm3`, `costurado`, `arestas_livres` (a contagem que
deve dar zero, acima).

## Onde está no código

- `biblioteca/bim_pipeline/contratos/geometria.schema.json` — o contrato.
- `biblioteca/bim_pipeline/geometria/eixos.py` — conversões de eixos e unidades
  (`zup_para_viewer`, `viewer_para_zup`, variantes numpy e lista plana,
  `viewer_para_oq3d`).
- `biblioteca/bim_pipeline/geometria/dedup.py` — `dedup_arrays`, `dedup`.
- `biblioteca/bim_pipeline/geometria/malhas.py` — `malhas_por_cor`, `malhas_de_partes`.
- `biblioteca/bim_pipeline/cli/dedup.py` — CLI do dedup.

## Ver também

- `docs/conhecimento/oq3d.md` — o formato binário que produz a maior parte da geometria
  do projeto; unidades e eixos do lado da leitura/escrita do `.aq`.
- `docs/conhecimento/ifc.md` — o caminho de geometria a partir de IFC puro,
  incluindo `IFCINDEXEDCOLOURMAP` (cor por face) e os outliers de placement.
- `docs/bilds-bim-3d-zip-spec.md` §4 — o contrato de geometria do lado do consumidor
  (o ZIP publicado para a bilds.com), com a mesma tabela de eixos.
- `CONCEPTS.md` — verbetes "`{pos, col, idx}`", "Dedup", "Bocal", "Parte", "Bake",
  "Arestas de borda", "Forma representativa".
