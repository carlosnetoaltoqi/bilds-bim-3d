# 2026-08-24 — Estudo OQ3D: a geometria sai do .aq (commits 237e247, d32a4ca, c3be58b)

**Data:** 2026-08-24 · Registro **extraído do `CLAUDE.md`** em 2026-09-04 (S7.8, I22) — esta
sessão não tinha arquivo próprio; o texto abaixo é o que havia lá, sem alteração.

---

**A descoberta.** O `.aq` não é só o banco de dados de produto: carrega a malha 3D
completa, com cor e miniatura, no BLOB `SIMBOLOGIA_3D.SIMBOLOGIA_3D`, em formato
binário proprietário (OQ3D). É o mesmo sólido que o AltoQi exporta como IFC.
Consequência: **os IFCs deixaram de ser necessários** no caminho padrão.

**Como foi validado.** Três bibliotecas de naturezas opostas, mais um teste cego:

| Biblioteca | Schema | Peças | Geometrias | IFCs de contraprova |
|---|---|---|---|---|
| Dancor (bombas) | 607 | 13 | 13 | 14, tessellated |
| Amanco (conexões PVC) | 595 | 1.168 | 457 | 502, `IFCADVANCEDBREP` |
| Intelbras (elétrica) | 572 | 32 | 18 | nenhum — teste cego |

Onde o IFC é tessellated, os triângulos batem **exatamente** (37-40 TJM: 44.951 em
ambos). Onde é B-rep, a forma converge a 0,3 mm mas a tesselação é independente —
o IFC guarda o sólido exato e é retessellizado a cada leitura, o `.aq` traz a malha
que o AltoQi fixou. O lote final rodou sobre **9 bibliotecas e seis versões de
schema** (552, 562, 572, 582, 595, 607) sem uma falha.

**Bug do parser linear (achado na Amanco).** Nas bombas, as malhas já vêm em
coordenadas de mundo — dá para ignorar os transforms e ainda renderizar certo. Nas
conexões **não**: cada peça é montada de malhas reaproveitadas e posicionadas por
`TCoordinateTransformation3D`. O primeiro parser produzia joelhos retos. Exigiu
parser de árvore com pilha (`scripts/oq3d.py`).

**Bug colateral no `parse_ifc.py` — ainda aberto.** Ao resolver o Caminho B, o
código procura o face set direto dentro do `IFCREPRESENTATIONMAP`, mas falta um
nível: `IFCMAPPEDITEM → IFCREPRESENTATIONMAP → IFCSHAPEREPRESENTATION →
IFCTRIANGULATEDFACESET`. Na CAM-W21 isso descarta 3.231 triângulos (13,8%) — as
peças instanciadas. Afeta só o modo `--ifc`.

**O `file_map` morreu.** O vínculo `PECA → PECA_SIMBOLOGIA_3D → SIMBOLOGIA_3D` é
chave estrangeira. O matching por tokens do `find_aq_product` é comprovadamente
frágil: ao tentar parear os 502 caminhos de IFC da Amanco com os nomes do banco,
`Junção Simples + Joelho 45/Com luva` casou com `Luva Simples 200MM` — cobertura
100%, peça errada.

**Variantes com e sem luva.** O AltoQi exporta **dois IFCs por peça** (com e sem a
luva de encaixe) e o banco guarda só a canônica — a com luva. Explica os 502 IFCs
para 457 geometrias. Medindo por bounding box: 76% de cobertura nos "com luva",
1,5% nos "sem luva".

**Peças sem forma fixa.** 312 das 1.168 peças da Amanco (27%) não têm geometria, e
é o correto: tubos (cilindro paramétrico por diâmetro × comprimento) e kits de
aparelho sanitário. O build informa quantas pulou.

**Erros cometidos nesta sessão, e o que ensinaram:**

- **Faltou o `dedup()`** no caminho `.aq` — só o caminho IFC aplicava. O preview
  foi para 571 MB; com dedup, 347 MB para 9 catálogos (antes: 155 MB para 2).
- **`output/*.zip` não cobre subpastas.** Como a saída passou a espelhar o input,
  os 9 ZIPs escaparam do gitignore. Corrigido com `output/**/*.zip`.
- **`./data/` quebra com `cleanUrls`.** Mover o `data/` para dentro do catálogo
  (necessário: `50mm.json` colide entre bibliotecas) expôs que a página é servida
  em `/<slug>` sem barra final, e o relativo resolve para a raiz. O sintoma
  enganoso era `Unexpected token 'T'` — a página 404 da Vercel caindo no
  `JSON.parse`. Agora o `fetch` checa `r.ok` antes de parsear.

**Pendência da época (resolvida em 2026-08-30):** parafusos faltando na Dancor —
13 de 18 instâncias não emitiam geometria, e uma peça aparecia solta no ar. Eram
dois bugs distintos: a referência da instância repetida e a rotação column-major.
Ver "Instâncias repetidas — RESOLVIDO" na seção do `oq3d.py`.

**Ponto estável: commit `c3be58b`** — 9 catálogos em produção, geometria servindo
200 em todos. Para retornar: `git checkout c3be58b`.
