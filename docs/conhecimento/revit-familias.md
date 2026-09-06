# Famílias Revit — o que um `.rfa` entrega sem o Revit, e como vira catálogo

Uma **família** Revit (`.rfa`) é o componente de biblioteca do Autodesk Revit: uma peça
parametrizada com **tipos** (as variações — "VS350X26", "DN50", "Esp. 0,80 mm") que o projetista
carrega num **projeto** (`.rvt`). Fabricantes distribuem bibliotecas BIM como pacotes de `.rfa`, cada um
com um **type catalog** (`.txt` de mesmo nome) quando a família tem muitos tipos. Este documento diz o
que é legível desses arquivos fora do Revit, o que não é, e a regra que a fonte
`catalogo/fontes/familias_revit.py` segue para transformá-los num catálogo que vira `.aq`.

## O contêiner: OLE2 com streams

`.rfa`, `.rvt`, `.rte` e `.rft` são documentos **OLE2** (Compound File Binary, a casca do `.doc`
antigo). Uma biblioteca OLE genérica (`olefile`) abre e lista os streams; o layout é o mesmo desde o
Revit 2016 pelo menos:

| Stream | Conteúdo | Legível? |
|---|---|---|
| `BasicFileInfo` | versão do Revit, build, caminho original, locale — UTF-16 | sim |
| `PartAtom` | XML Atom (`urn:schemas-autodesk-com:partatom`): título, categoria, tipos com parâmetros | sim |
| `RevitPreview4.0` | PNG de pré-visualização (nem toda família tem — as baseadas em linha costumam vir sem) | sim |
| `Formats/Latest` | esquema de classes do Revit (nomes e campos) | sim, mas só nomes |
| `Global/*`, `Partitions/<n>` | os elementos e a **geometria** — gzip de um binário proprietário | **não** |
| `TransmissionData`, `Contents` | vínculos externos, índice | irrelevantes aqui |

`BasicFileInfo` mudou de forma no Revit 2020: até o 2019 é texto corrido ("Autodesk Revit 2017
(Build: …)"); a partir daí é um registro binário com campos UTF-16 de comprimento prefixado, seguido
de um bloco de texto "Format: 2021 / Build: … / Last Save Path: … / Locale when saved: ENU". Esse
bloco pode começar em **offset ímpar**, então o leitor decodifica o stream nos dois alinhamentos e
procura os rótulos nos dois (`rfa_partatom.info_basica`). O número que importa é o **formato** (o
ano): um `.rfa` só abre num Revit de versão igual ou mais nova.

## `PartAtom`: a tabela de tipos

```xml
<entry xmlns="http://www.w3.org/2005/Atom" xmlns:A="urn:schemas-autodesk-com:partatom">
  <title>Viga_PerfilSoldado</title>
  <category><term>23.25.30.11.14.14</term><scheme>adsk:revit:grouping</scheme></category>
  <A:family type="user"><A:variationCount>80</A:variationCount>
    <A:part type="user"><title>VS350X26</title>
      <Width type="custom" typeOfParameter="Section Property">140.00 mm</Width>
      <Manufacturer type="system" typeOfParameter="Text">Fabricante</Manufacturer>
      <Structural_Material type="custom" typeOfParameter="Material">Aço ASTM A36</Structural_Material>
      …
```

- **`category/term`** é o nome da categoria Revit ("Specialty Equipment", "Conexões de tubo") **ou**
  um código **OmniClass** Tabela 23 (`23.25.30.11.14.14`), conforme o que o autor preencheu. O
  leitor guarda o que vier: nome → spec "Categoria Revit"; código → spec "OmniClass".
- **Um `A:part` por tipo**, com um elemento por parâmetro. O nome XML troca espaço e pontuação por
  `_`; o nome legível está em `displayName` quando existe. `typeOfParameter` diz o tipo de dado do
  Revit ("Length", "Section Property", "Text", "Material", "Yes/No", "URL", "Integer"…); `type=
  "system"` marca parâmetro embutido do Revit (Manufacturer, Model, URL, Description),
  `"custom"` os da família.
- **Valores vêm formatados na unidade de projeto**: "350.00 mm", "0.84 m", "89.100 kgf/m",
  `29 7/8"`. Converter para milímetro exige ler número **e** unidade (polegada fracionária
  inclusive); sem unidade assume-se milímetro (`familias_revit.valor_em_mm`).

## Type catalog: o `.txt` manda

Quando a família tem muitos tipos, o `.rfa` costuma guardar **um único tipo-molde** e o fabricante
distribui um `.txt` de mesmo nome ao lado — o Revit o lê na hora de carregar e oferece a lista de
tipos. Por isso um `PartAtom` pode declarar um tipo enquanto o `.txt` traz cento e sessenta. Formato
(`conversores/type_catalog.py`):

```
,Largura##SECTION_PROPERTY##MILLIMETERS,Peso nominal##WEIGHT_PER_UNIT_LENGTH##KILOGRAMS_FORCE_PER_METER,Descrição##OTHER##
Tubo ret 25 x 15 x 0.75,15,0.44,"Perfil, retangular"
```

- CSV com vírgula (o que o Revit grava) **ou TAB** (o que algumas ferramentas gravam); célula com
  vírgula entre aspas; primeira célula do cabeçalho vazia; primeira coluna de cada linha = nome do tipo.
- Cabeçalho `NOME##TIPO##UNIDADE`: `TIPO` é o tipo de dado (LENGTH, SECTION_PROPERTY, NUMBER, TEXT,
  MATERIAL, YESNO, URL, OTHER, WEIGHT_PER_UNIT_LENGTH, AREA_FORCE, LINEAR_FORCE…); `UNIDADE` é a unidade
  em que a coluna está escrita (MILLIMETERS, METERS, INCHES, FEET, KILOGRAMS_FORCE_PER_METER…). **Comprimento
  sem unidade é pé** — a unidade interna do Revit.
- Codificação: ANSI da máquina que gravou (cp1252 no Windows em português) na maioria; alguns em
  UTF-16 ou UTF-8 com BOM. Decide-se pelo BOM; sem BOM, UTF-8 estrito antes de cair no cp1252.

**Fusão** (`familias_revit.fundir_tipos`): os tipos do `.txt` são os produtos; parâmetros que só o
`PartAtom` tem completam cada tipo; parâmetros **constantes** em todos os tipos do `PartAtom`
(fabricante, URL, norma, material) vão para todos; quando o `.rfa` tem um só tipo e há `.txt`, o
tipo-molde não vira produto. Sem `.txt`, os tipos do `PartAtom` são os produtos.

## O que NÃO se lê — e por quê a geometria vem de fora

A geometria fica em `Partitions/<n>`: gzip (inflável) de um binário proprietário sem especificação
pública. Não há leitor aberto que devolva a malha de uma família — o mais avançado se declara
"not yet a full Revit model reader" e só emite extrusões retangulares de paredes e lajes de projeto.
O Revit **não exporta uma família para IFC** sem carregá-la num projeto. Um **`.rvt`** (projeto)
não tem `PartAtom` e não entrega as famílias embutidas — é recusado com essa explicação. A única
rota que devolve a malha real é a nuvem da Autodesk (APS Model Derivative), fora do escopo de um
pipeline offline.

Daí a regra **híbrida** da fonte:

1. **Geometria irmã** — um `.ifc`/`.ifczip`/`.stp`/`.step`/`.igs`/`.iges` com o **mesmo nome** da
   família (mesma pasta primeiro, qualquer pasta depois), exportado do Revit via projeto ou baixado do
   portal do fabricante (que costuma oferecer IFC ao lado do RFA): a geometria real vem pelos conversores
   da biblioteca e é **compartilhada por todos os tipos da família** (uma simbologia, N peças — como o
   `.aq` faz). Um arquivo irmão ilegível não derruba a família: avisa e cai na regra 2.
2. **Forma representativa por parâmetro** — as cotas da seção vêm dos parâmetros do tipo (DADO); o que a
   família não cota é INVENÇÃO explícita em `PROPORCOES` (`formas-representativas.md`). Tipos com as
   mesmas cotas, cor e orientação compartilham a geometria.
3. **Sem cota reconhecível** → o tipo fica fora, avisado no diagnóstico (sem geometria não há peça
   no `.aq`, `aq-escrita.md`).

### As formas e como são escolhidas

`geometria/perfis.py` extruda seções 2D (centímetros, Z-up, `[(verts, tris, rgba)]`): um anel
(polígono simples, tampa por *ear clipping*) ou dois anéis de mesma contagem (externo e furo, tampa em
faixa). Todo sólido sai fechado — zero arestas de borda, volume analítico. A escolha
(`familias_revit.forma_representativa`), pelos parâmetros casados por sinônimo EN/PT
(`SINONIMOS`: "Width"/"Largura"/"b", "Flange Thickness"/"Espessura da mesa"/"tf"…):

| Cotas presentes | Forma | Invenção |
|---|---|---|
| espessura da chapa + largura do módulo | chapa trapezoidal (telha-forma/steel deck); com "Capa de concreto" = sim e espessura, uma laje por cima | altura de nervura (60 mm) e passo (280 mm) se não cotados; trecho |
| diâmetro + parede | tubo redondo | trecho |
| diâmetro | barra redonda | trecho |
| largura + altura + mesa + alma | perfil I (ou U, se o título diz U/canal) | trecho; cantos vivos, sem solda nem raio |
| largura + altura + parede, título "cantoneira/L" | cantoneira | trecho |
| largura + altura + parede | tubo retangular | trecho; cantos vivos |
| largura + altura + profundidade | caixa | nada |
| largura + altura, título estrutural (viga, perfil, tubo…) | barra retangular | trecho |
| largura + altura | caixa | profundidade = menor das duas |

"Trecho" é o comprimento do segmento representativo: o parâmetro `Length`/`Comprimento` do tipo
quando plausível (100 mm a 20 m), senão `PROPORCOES['comprimento_perfil_mm']` (1000, ajustável por
`--comprimento-mm`). **Orientação**: pilar/coluna/poste em pé (comprimento em +Z); o resto deitado
(comprimento em +X, altura da seção na vertical); a chapa assentada (largura em X, comprimento em Y,
nervura para +Z). As rotações são próprias (permutação cíclica), para as normais continuarem para
fora. Cor pelo material: aço, galvanizado, concreto, genérico — escolha de visualização.

**A ressalva vai dentro do catálogo**, como manda `formas-representativas.md`: a série recebe o
sufixo " (forma representativa)" — é o que vira `GRUPO_PECA` no `.aq` — e cada peça leva a spec
**"Geometria 3D"** com o texto da ressalva e a **regra** que gerou a forma ("perfil I: largura, altura,
mesa e alma do tipo; trecho de 1000 mm (aprox.); sem solda nem raio"), mais "Fonte 3D" (o arquivo irmão
ou "forma representativa (perfil_i)").

## O catálogo que sai

Mesmo contrato `catalogo` de toda fonte (`hints.schema = 'familias-revit'`):

- **série** = título da família humanizado (`_` → espaço); **produto** = um por tipo, `nome` = título do
  tipo, `id` = slug de família + tipo, `codigo` = `Model`/`Modelo`/`Código` quando há;
- **specs** = todos os parâmetros do tipo ("350 mm", "89.1 kgf/m") + "Família Revit", "Tipo Revit",
  "Categoria Revit" ou "OmniClass", "Revit" (versão), "Fonte 3D", "Geometria 3D";
- **fabricante** = o `Manufacturer` mais frequente, salvo `--fabricante`; **título** = `--titulo` ou o
  nome do arquivo/pasta;
- **`conexoes`** = categoria (nome ou OmniClass) — vira `PECA.DESCRICAO_DADOS`.

**Compatibilidade com o `.aq`**: todo texto (nome, série, chave e valor de spec, título, fabricante)
passa por `cp1252_seguro` — "→" vira "->", "≥" vira ">=", o resto vira "?" — porque o escritor do
`.aq` é estrito e abortaria (`aq-escrita.md`). Um aviso conta quantos textos foram ajustados. O
`.aq` exportado do catálogo tem uma `SIMBOLOGIA_3D` por geometria distinta, compartilhada entre os
tipos que a usam, e uma `PROPRIEDADE_PERSONALIZADA` por chave de spec.

## O que este caminho não faz

- Não lê geometria de `.rfa` nem de `.rvt`; não converte `.aq` de volta para `.rfa`.
- Não distingue idiomas: um pacote com a mesma família em `ENU/` e `PTB/` gera duas séries (os nomes
  diferem). Filtrar é decisão de quem importa.
- Não usa a miniatura do `.rfa` como thumb do produto: a miniatura sai da geometria, pelo Chromium,
  como para toda fonte (ADR-006).
- Não mapeia OmniClass para nome de categoria (o código fica como spec).

## Onde está no código

- `biblioteca/bim_pipeline/conversores/rfa_partatom.py` — OLE2 → `BasicFileInfo` (`info_basica`, dois
  alinhamentos), `PartAtom` (`tipos_detalhados` com `typeOfParameter`), preview PNG.
- `biblioteca/bim_pipeline/conversores/type_catalog.py` — o `.txt`: `decodificar`, `separador`, `parsear`,
  `para_mm`, `rotulo_unidade`, `eh_type_catalog`.
- `biblioteca/bim_pipeline/geometria/perfis.py` — `extrudar`, anéis (`retangulo`, `circulo`, `secao_i`,
  `secao_u`, `secao_l`), `chapa_trapezoidal`, `deitar`/`assentar`, `arestas_de_borda`, `volume_assinado`.
- `biblioteca/bim_pipeline/catalogo/fontes/familias_revit.py` — `descobrir`, `ler_familia`, `fundir_tipos`,
  `dimensoes`, `forma_representativa`, `catalogo_de_familias`, `inspecionar`, `importar`, CLI
  `inspecionar`/`importar`; contrato `contratos/info-familias-revit.schema.json`.
- `pacotes/base/src/biblioteca.ts` — `inspecionarFamiliasRevit`, `catalogoDeFamiliasRevit`;
  `servicos/criador-de-catalogos` — `POST /importacoes/familias-revit` (e `.rfa` solto em `POST /importacoes`);
  `web/src/app/importar/revit/`.
- Testes: `tests/biblioteca/test_familias_revit.py` (sintético e, com a fixture `rfa_familias`, real).

## Ver também

- `docs/conhecimento/formas-representativas.md` — dado × norma × invenção; os defeitos que só a
  renderização pega.
- `docs/conhecimento/plugin-cad-catalogo-web.md` — a outra fonte que lê `.rfa` (só como spec, geometria do IGES).
- `docs/conhecimento/aq-escrita.md` — o que o `.aq` exige de cada produto (geometria, cp1252, série → grupo).
- `docs/decisoes/ADR-018-familias-revit-hibrido.md` — a decisão.
