# eng-reversa — escrever um `.aq` a partir de um catálogo em PDF

Estudo de engenharia reversa do formato de biblioteca BIM do AltoQi Builder
(`.aq`) **no sentido da escrita**, e a sua materialização: uma biblioteca
`.aq` gerada a partir do `input/Akato/AKATO-CATALOGO-CONSTRUCAO-CIVIL.pdf`.

O projeto bilds-bim-3d sabe **ler** `.aq` — o `scripts/read_aq.py` e o
`scripts/oq3d.py` estão validados em 12 bibliotecas de fabricante e 6 versões
de schema. Este estudo fecha o outro lado: o que é preciso saber para
**escrever** um `.aq` que aquele mesmo leitor, e o AltoQi, aceitem.

> **O estudo foi feito sem alterar o projeto, e depois aplicado nele.** Durante a
> investigação os módulos do projeto foram apenas importados, sem modificação, e tudo o
> que era gerado ficou aqui dentro. Concluído o estudo, os achados foram levados para a
> documentação e o código oficiais (2026-09-02):
>
> - `CLAUDE.md` — seção "Escrever um `.aq`", cabeçalho OQ3D, correção do
>   `DIAMETRO_PECA`, sentinelas, 9 linhas de diagnóstico e a entrada de sessão;
> - `docs/skills/leitor-biblioteca-aq/` **2.3.0** e `pagina-biblioteca/` **1.5.0**;
> - `CONCEPTS.md` — Código de diâmetro, Sentinela, Forma representativa;
> - `scripts/read_aq.py` — `diametro_cm` → `diametro_codigo` e sentinela → `None`;
> - `scripts/oq3d.py` — `n_raizes_declarado()` e o aviso `OQ3DAvisoParse`;
> - `scripts/build.py` — `saida`/`output` em `_GENERIC_DIRS`.
>
> O que este diretório continua não fazendo: escrever fora de si. A única exceção é o
> `--zip` do `pipeline_ponta_a_ponta.py`, que grava em `output/` porque é o lugar padrão
> dos ZIPs do projeto, e só quando pedido.

---

## Resultado

**PDF comercial → `.aq` → catálogo publicável com viewer 3D**, ponta a ponta,
com o pipeline do próprio projeto lendo o arquivo que nós escrevemos.

| Etapa | Resultado |
|---|---|
| Extração do PDF | 24 páginas, 87 famílias, **269 produtos**, 0 códigos repetidos, 0 linhas incompletas, 0 avisos |
| Tabela de conversão polegada × milímetro | 12 linhas, da página 23 |
| `.aq` gerado | **262 peças** + 7 insumos, 1.494 valores de propriedade, 269 códigos comerciais, 83 grupos com classificação IFC |
| Leitura pelo `read_aq.py` do projeto | 20 checagens, todas passando, nas três variantes |
| Escritor OQ3D | 6 casos de round-trip, incluindo a reescrita de uma geometria real da Amanco |
| Formas paramétricas | 23 geradores, **262 de 262 peças**, 240.920 triângulos, zero arestas abertas, conferidas no viewer |
| `build.py` do projeto sobre o `.aq` gerado | `catalog.json` + **262 geometrias** + página de preview com viewer 3D |

### Os três arquivos gerados

| Arquivo em `saida/Akato/` | Geometria | Tamanho |
|---|---|---|
| `PVC Construção Civil (sem geometria)/` | nenhuma | 848 KB |
| `PVC Construção Civil/` | 12 tubos | 944 KB |
| `PVC Construção Civil (forma representativa)/` | 262 peças | 6,8 MB |

O **sem geometria** é o catálogo fiel: só o que o PDF diz. É a variante
correta, porque **o PDF não traz cota de forma nenhuma** — ver
`estudo/04-lacunas-do-catalogo-comercial.md`.

O **12 tubos** demonstra o caminho da geometria com a única forma que o
catálogo mais a norma determinam por completo.

O **forma representativa** tem malha para todas as 262 peças, gerada por
parâmetro. As formas **não são as cotas da Akato**: o diâmetro nominal é do
catálogo e a espessura de parede é da NBR, mas bolsa, colar, raio de curva e
corpo de registro são proporções inventadas. A ressalva está gravada dentro do
arquivo, no nome do grupo de simbologia e numa propriedade de cada peça. Ver
`estudo/06-formas-parametricas.md`.

> O nome da pasta importa. O `build.py` infere o título do catálogo a partir da
> pasta pai do `.aq`, então `PVC Construção Civil/` produz o título certo e uma
> pasta chamada `saida/` produziria o título "Saida". Ver o achado 5 em
> `estudo/05-achados-para-a-documentacao-do-projeto.md`.

---

## O estudo

| Documento | Assunto |
|---|---|
| [`estudo/01-escrever-um-aq.md`](estudo/01-escrever-um-aq.md) | O schema, os enums, as sentinelas, a ordem de inserção e **a armadilha do encoding**, que é a que corrompe o arquivo em silêncio |
| [`estudo/02-escrever-oq3d.md`](estudo/02-escrever-oq3d.md) | O formato binário da geometria, byte a byte, do lado de quem grava |
| [`estudo/03-extrair-tabelas-de-um-pdf-de-catalogo.md`](estudo/03-extrair-tabelas-de-um-pdf-de-catalogo.md) | Como ler tabelas de um PDF do Illustrator em que o `y` está corrompido |
| [`estudo/04-lacunas-do-catalogo-comercial.md`](estudo/04-lacunas-do-catalogo-comercial.md) | O que o PDF dá, o que não dá, e o que falta para uma biblioteca completa |
| [`estudo/05-achados-para-a-documentacao-do-projeto.md`](estudo/05-achados-para-a-documentacao-do-projeto.md) | Onde o `CLAUDE.md` e a skill `leitor-biblioteca-aq` estão incompletos ou errados |
| [`estudo/06-formas-parametricas.md`](estudo/06-formas-parametricas.md) | As 23 formas paramétricas: o que é dado, o que é norma e o que é invenção |

---

## As ferramentas

Todas são independentes e somente-leitura sobre as bibliotecas de `input/`.

| Ferramenta | O que faz |
|---|---|
| `tools/pdf_coords.py` | Extrai o texto do PDF **com coordenadas**, uma célula por operador de texto |
| `tools/pdf_akato.py` | Remonta as tabelas do catálogo a partir das células |
| `tools/aq_referencia.py` | Levanta de um `.aq` real os valores de enum que um gerador precisa |
| `tools/oq3d_anatomy.py` | Dissecação byte a byte de um blob OQ3D |
| `tools/oq3d_writer.py` | **Escreve** OQ3D, e gera cilindro e tubo paramétricos. Também usado por `scripts/geo_to_aq.py` (exportação `.aq` do editor 3D) |
| `tools/oq3d_roundtrip.py` | Prova o escritor contra o `scripts/oq3d.py` do projeto. O caso 6 reescreve um blob real da Amanco (`input/Amanco/…aq`, sid 169); sem o `.aq` é **FALHA**, não "pulado" — `--sem-real` pula de propósito (I8, 2026-09-04) |
| `tools/formas.py` | **Geometria paramétrica representativa**, 23 formas |
| `tools/formas_teste.py` | Gera as 262 formas e checa escala, proporção e estanqueidade |
| `tools/gerar_aq.py` | Gera o `.aq` a partir do catálogo extraído. **`scripts/geo_to_aq.py` importa daqui** `criar_schema`, `Gerador` (cp1252) e as constantes do AltoQi — não mover nem renomear sem ajustar |
| `tools/validar_aq.py` | Valida o `.aq` gerado com o `read_aq.py` do projeto |
| `tools/pipeline_ponta_a_ponta.py` | Roda o `build.py` do projeto sobre o `.aq` gerado |
| `tools/olhar_preview.mjs` | Abre a página no Playwright e fotografa as peças — a checagem que pega erro de posição relativa |

### Refazer tudo

```bash
cd /home/foltz/bilds-bim-3d

# 1. PDF → células com coordenadas → catálogo estruturado
python3 eng-reversa/tools/pdf_coords.py \
        input/Akato/AKATO-CATALOGO-CONSTRUCAO-CIVIL.pdf \
        eng-reversa/dados/akato-celulas.json
python3 eng-reversa/tools/pdf_akato.py \
        eng-reversa/dados/akato-celulas.json \
        eng-reversa/dados/akato-catalogo.json

# 2. o escritor de geometria, antes de confiar nele (exit 1 se input/Amanco faltar;
#    --sem-real para pular o blob real de propósito)
python3 eng-reversa/tools/oq3d_roundtrip.py

# 3. as formas, antes de confiar nelas
python3 eng-reversa/tools/formas_teste.py

# 4. catálogo → .aq. Sem flag: sem geometria (o fiel).
#    --geometria-demo: só os tubos.  --geometria-parametrica: todas as peças.
python3 eng-reversa/tools/gerar_aq.py \
        eng-reversa/dados/akato-catalogo.json \
        "eng-reversa/saida/Akato/PVC Construção Civil (forma representativa)/pecas_akato_construcao_civil.aq" \
        --geometria-parametrica

# 5. o .aq gerado é lido pelo pipeline do projeto?
AQ="eng-reversa/saida/Akato/PVC Construção Civil (forma representativa)/pecas_akato_construcao_civil.aq"
python3 eng-reversa/tools/validar_aq.py "$AQ"
SLUG=akato-formas python3 eng-reversa/tools/pipeline_ponta_a_ponta.py "$AQ"
```

### Ver a página com o viewer 3D

O template referencia o Three.js em caminho absoluto (`/vendor/three.module.js`,
via importmap), então a página precisa ser servida com o diretório de preview
como raiz:

```bash
python3 -m http.server -d eng-reversa/saida/preview 8080
# → http://localhost:8080/akato-formas/
```

O `pipeline_ponta_a_ponta.py` copia o `templates/vendor/` para lá, então o
preview é autocontido — conferido: `/`, a página, o `three.module.js` e os
JSONs de geometria respondem 200.

Dependências: `python3`, `pypdf` (já instalado) e `numpy` (opcional, o
`oq3d.py` degrada sem ele). Não precisa do AltoQi Builder — e é justamente por
isso que a validação é contra o leitor do projeto, não contra o AltoQi.

---

## Os dados intermediários

| Arquivo | Conteúdo |
|---|---|
| `dados/akato-celulas.json` | 1.925 células do PDF com x, y, corpo da fonte e ordem de desenho |
| `dados/akato-catalogo.json` | 87 famílias, 269 produtos, tabela de conversão |
| `dados/akato-pdf-texto.txt` | O `extract_text()` linear, guardado para comparação — é o que **não** funciona |
| `dados/schema-aq-607.sql` | DDL completo de um `.aq`: 77 tabelas e 84 índices |

---

## O limite desta validação

**O `.aq` gerado abriu no AltoQi Builder** (teste do usuário em 2026-09-02, em outra
máquina; registrado em 2026-09-03). Árvore de classes, grupos e peças correta,
propriedades personalizadas visíveis com acentos íntegros — a confirmação de que o
cp1252 via `CAST(? AS TEXT)` é o que o Builder espera. Print em
`estudo/img/builder-akato-aberto-2026-09-02.png`; detalhe em
`estudo/01-escrever-um-aq.md`, seção 8.

Nesta máquina não há Builder. Aqui o que está provado é que o `.aq` gerado é lido,
sem ressalva, pelos leitores do projeto — `read_aq.py` e `oq3d.py`, validados em 12
bibliotecas de fabricante e 6 versões de schema — e que atravessa o `build.py` até
uma página publicável.

O que **ainda falta provar** no Builder: a malha OQ3D renderizando na janela 3D, a
peça lançada numa rede (sem `ENTRADA_PECA` o encaixe automático é improvável) e o
comportamento sem simbologia 2D. Os riscos estão em `estudo/01-escrever-um-aq.md`,
seção "O que só o Builder pode dizer".
