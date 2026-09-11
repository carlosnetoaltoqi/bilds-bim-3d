# CLAUDE.md — bilds-bim-3d

Ponto de entrada para quem trabalha neste projeto, agente ou humano. É um **mapa**: o que o projeto é,
como rodar, onde está cada conhecimento e qual é o estado atual. O conhecimento em si mora em
`docs/conhecimento/`, nos READMEs de cada serviço e nas skills — este arquivo aponta, não repete.

> **`docs/historico/` não é para ser lido ao carregar o projeto.** É arquivo (sessões antigas, estudos,
> planos superados, lições de processo) para consulta pontual do operador. Só abra um arquivo de lá
> quando precisar da evidência de um número ou do raciocínio de uma decisão antiga.

---

## Regra fundamental: documentação primeiro

Se a informação não está no repositório, ela não existe para o próximo agente. Memória de agente e
skills fora do repo são auxiliares. O que vale é o **estado atual**, não a trilha de como se chegou nele:

1. Código corrigido e commitado — **um commit por item**, com o teste em `tests/` no mesmo commit
   quando há comportamento novo.
2. Conhecimento novo sobre formato, algoritmo ou padrão vai para o documento certo de
   `docs/conhecimento/` (ou o README do serviço, se for operação dele) — nunca para cá, nunca para o histórico.
3. Decisão nova ou revista é um ADR em `docs/decisoes/`; uma decisão superada ganha status
   "Substituída por ADR-nnn", não é apagada.
4. Se algo aqui ou em `docs/` se mostrou falso, corrigir **no documento de origem**, sem "antes dizia…".
   Documentação oficial não carrega narrativa do que deu errado; se uma lição de processo merece ficar,
   vai para `docs/historico/licoes-de-processo.md`.
5. Se aprendeu algo sobre `.aq`, OQ3D, IFC, STEP/IGES ou páginas de catálogo, a **skill** em
   `docs/skills/` recebe a linha e o bump de `version`.
6. **Sem fabricantes, arquivos ou caminhos da POC** em código, contratos, conhecimento ou skills
   (ADR-016; a lista está em `tests/arquitetura/termos_efemeros.txt`). Isso só cabe em `docs/historico/`,
   `docs/integracoes/` e `tests/fixtures.local.json`.
7. O bloco **"Estado atual e pendências"** no fim deste arquivo é atualizado ao encerrar — só fatos
   verificáveis e o que falta fazer.

## O que é este projeto

Catálogos BIM com viewer 3D a partir de bibliotecas `.aq` do AltoQi Builder — e o caminho de volta
(escrever `.aq`, converter CAD, ler catálogos de plugins e famílias Revit, gerar o ZIP que a bilds.com consome).
**A decisão central: a geometria vem do `.aq`, não do IFC** — o BLOB `SIMBOLOGIA_3D` guarda a malha
completa, com cor, no formato OQ3D; vínculo peça → geometria por chave estrangeira, zero matching por nome.

**Arquitetura (`docs/arquitetura.md`):** uma **biblioteca Python comum** (`biblioteca/`, pacote
`bim_pipeline`, stateless) e **um serviço por contexto** em `servicos/` — criador de catálogos (:4100),
API de catálogo (:4000), editor de peças (:4400), gerador de ZIP (:4200, stateless), conversores
(:4300, stateless) — mais o `web/` (:3000) com um cliente por serviço e os pacotes TypeScript comuns
(`pacotes/base`, `pacotes/dominio`). Cada contexto pode ser portado levando só o que é seu (§4 da
arquitetura). Enquanto viver aqui é POC: sem auth, sem admin (ADR-007).

## Como rodar

```bash
bash scripts/bootstrap.sh --check        # a tabela do ambiente; sem --check instala o que falta (nunca sudo)
sudo apt-get install -y libnss3 libnspr4 libasound2t64     # libs do Chromium — único passo com sudo
python3 -m bim_pipeline.cli.zip_bilds biblioteca.aq --saida saida.zip   # só o ZIP, sem serviços
cp .env.example .env && pnpm dev          # cinco serviços + web (compila os pacotes antes)
python3 -m pytest                         # 240 testes, ≈ 4 min; -m "not thumbs" sem Chromium
```

Detalhes de uso em `README.md`; rotas e variáveis de cada serviço no `README.md` dele; roteiro de
aceitação com tudo de pé em `docs/aceitacao.md`.

## Onde está cada conhecimento

| Assunto | Onde |
|---|---|
| **Arquitetura**: camadas, sete regras de fronteira, quem grava o quê, guia de porte, regras de mudança | `docs/arquitetura.md`; decisões em `docs/decisoes/` (ADR-001…026) |
| Formato `.aq` (SQLite/ZIP, cp1252, sentinelas, código de diâmetro, enums, versões de schema, leitura; **o que desenha em planta**) | `docs/conhecimento/aq-formato.md` |
| Escrever `.aq` — uma peça e o catálogo inteiro (cinco regras, erros que abortam, validação) | `docs/conhecimento/aq-escrita.md` |
| Formato binário **OQ3D** — leitura tolerante e escrita | `docs/conhecimento/oq3d.md` |
| Contrato de geometria `{pos,col,idx}`, eixos, dedup, partes, **bocais** (achar na malha os pontos de ligação) | `docs/conhecimento/geometria.md` |
| IFC4 — leitura (placement, cores, unidades), escrita (o exportador do editor), verificação a 2 µm | `docs/conhecimento/ifc.md` |
| STEP e IGES → malha (OpenCASCADE), costura de faces soltas, orientação pelo volume | `docs/conhecimento/step-iges.md` |
| Plugin de CAD que é casca de um catálogo web (DLL, API, formulário de lead, IGES/RFA, termos de uso) | `docs/conhecimento/plugin-cad-catalogo-web.md` |
| Famílias Revit `.rfa` (OLE2, PartAtom, BasicFileInfo, type catalog `.txt`; o que não se lê; geometria irmã ou forma representativa) e projetos `.rvt` via IFC (APS Model Derivative, opt-in; `.rfa` não é aceito pela APS) | `docs/conhecimento/revit-familias.md`; decisões em ADR-018 e ADR-019 |
| Catálogo comercial em PDF → tabelas; o que um PDF nunca determina | `docs/conhecimento/pdf-catalogo.md` |
| Forma representativa por parâmetro (dado × norma × invenção; os dois defeitos que passam em teste) | `docs/conhecimento/formas-representativas.md` |
| **Aplicação e disciplina** — `PROJETO_APLICACAO` (bitmask), `TIPO_APLICACAO_PECA` (enum 1…84), a ponte `ENTIDADE_IFC` → aplicação, `POSICIONAR_SIMBOLOGIA_3D`, e como o pipeline classifica hoje | `docs/conhecimento/aplicacoes-builder.md`; ADR-024 |
| **Código de bitola** — a escala é em **polegada** (0…17), e 40/50/75 mm dependem da série | `docs/conhecimento/aq-formato.md` §`DIAMETRO_PECA`; ADR-025 |
| Inferência de fabricante, título, slug e layout | `docs/conhecimento/inferencia.md` |
| Miniaturas — mesma cena do viewer no Chromium, `page.evaluate` com string, harness por `http://` | `docs/conhecimento/miniaturas.md` |
| Modelo do catálogo — Import como máquina de estados, ponteiro de geometria, copy-on-write, remoção | `docs/conhecimento/catalogo-modelo.md` |
| Processos filhos — stdin EOF, stdout × stderr, timeouts, códigos | `docs/conhecimento/processos-filhos.md` |
| Fatos de serviço Nest/Next e de ferramentas (201, Ajv 2020, tsbuildinfo, project references, Atlas) | `docs/conhecimento/servicos-web.md` |
| Formato do ZIP (pacote genérico, com exemplo completo) · lado consumidor (bilds.com) | `docs/conhecimento/zip-bilds-formato.md` · `docs/integracoes/bilds-com.md` |
| **As duas fontes externas de verdade** (bibliotecas nativas + catálogo oficial do Builder; a ajuda em HTML), como distinguir nativa de saída nossa, e o método: medir → ajuda → experimento subtrativo | `docs/conhecimento/aq-formato.md` §"As duas fontes externas"; ferramenta `ferramentas.ajuda_builder` |
| **Sintoma → causa** (formatos e biblioteca) | `docs/conhecimento/diagnostico.md` |
| Contratos biblioteca ↔ serviços (JSON Schema) | `biblioteca/bim_pipeline/contratos/README.md` |
| Biblioteca: mapa de módulos, CLIs, regras | `biblioteca/README.md` |
| Cada serviço: rotas, variáveis, o que leva ao ser portado | `servicos/<nome>/README.md`, `web/README.md` |
| Vocabulário | `CONCEPTS.md` |
| Arquivo (sessões antigas, estudos, planos, spec original do ZIP, lições de processo) | `docs/historico/` — **não carregar**; consulta pontual |

### Skills — versionadas em `docs/skills/`

`leitor-biblioteca-aq` (ler e escrever `.aq`, OQ3D), `leitor-ifc`, `leitor-step`, `pagina-biblioteca`.
São how-tos curtos que apontam para `docs/conhecimento/` (cada uma leva `referencias/`, symlink para
lá). `bash scripts/link_skills.sh` cria symlinks em `~/.claude/skills/`. Servem outros projetos; **para
trabalhar aqui não são necessárias** — este mapa e `docs/` bastam.

## Estrutura

```
bilds-bim-3d/
├── biblioteca/bim_pipeline/{aq,geometria,catalogo(/fontes: plugin_catalogo_web, familias_revit),conversores,miniaturas,saida,cli(/ferramentas),contratos}
│   ← ★ a biblioteca comum (README próprio); miniaturas/ tem package.json próprio (playwright + three)
├── pacotes/base (@bim/base) · pacotes/dominio (@bim/dominio)   ← TypeScript compilado para dist/ (project references)
├── servicos/{criador-de-catalogos :4100, catalogo-api :4000, editor-de-pecas :4400, gerador-zip :4200, conversores :4300}
├── web/ :3000                    ← Next; src/servicos/<nome>.ts = um cliente por serviço; tools/ = round-trips do editor
├── tests/{biblioteca,servicos,arquitetura}/ · tests/paridade/ (harnesses Node) · tests/e2e/ · fixtures por papel
├── docs/{arquitetura.md, decisoes/, conhecimento/, integracoes/, skills/, aceitacao.md, historico/ (não carregar)}
├── scripts/bootstrap.sh · link_skills.sh
├── .env.example (portas por contexto, URLs, Mongo, STORAGE_PATH, APS_CLIENT_ID/SECRET opcionais) · pnpm-workspace.yaml · pyproject em biblioteca/
├── storage/ · input/ · output/   ← gitignored: storage dos serviços, .aq do usuário, saída do lote
```

## Pré-requisitos e armadilhas de ambiente

`bash scripts/bootstrap.sh --check` confere tudo. Versões nos arquivos: `.python-version` (3.12),
`.nvmrc` (24), `packageManager` (pnpm 11). `pip install -r requirements.txt` instala a biblioteca em
modo editável; `requirements-cad.txt` traz OpenCASCADE/ifcopenshell (STEP/IGES/IFC); `pnpm install` na
raiz instala pacotes, serviços, web e as dependências Node das miniaturas.

- **Dois Node na máquina** (apt v18 e nvm): um subprocess pega o do apt e o Playwright recusa. A
  biblioteca procura sozinha em `~/.nvm` (`miniaturas.render.find_node`); senão `BILDS_NODE=…`.
- **`sudo npx playwright install-deps` falha** com nvm (o sudo descarta o PATH): use o `apt-get` acima.
- **PEP 668**: `pip install` fora de venv pede `--user --break-system-packages`; o bootstrap tenta.
- **Só pnpm**; `npm install` gera lockfile que não é versionado.
- **Atlas com whitelist de IP**: o Mongoose culpa o whitelist para qualquer causa; diagnóstico no
  README do `catalogo-api`. Um Mongo local tira isso do caminho.
- **`dev:*` dos serviços Nest não tem watch**: mudou TypeScript, reinicie (`ss -ltnp | grep ':4100 '`).
- **`storage/`, `input/`, `output/` são dados não rastreados**: antes de qualquer `git clean`, confira o
  `.gitignore` com `git clean -ndq` (dry-run).

## Testes — `tests/` em três camadas

`tests/biblioteca/` (Python puro + fixtures por papel), `tests/servicos/` (harnesses Node em
`tests/paridade/` com ts-node de cada serviço; round-trips do editor), `tests/arquitetura/` (as sete
regras de `docs/arquitetura.md` §3: `test_biblioteca_isolada`, `test_fronteiras`, `test_sem_empresas`
com `termos_efemeros.txt`, `test_contratos`, `test_deps`). O que cada arquivo prova está no docstring
dele. Fixtures reais por **papel** em `tests/fixtures.local.json` (gitignored; modelo
`fixtures.example.json`; papéis em `tests/fixtures.py`) — sem elas os testes pulam com motivo.
**Regra:** comportamento novo entra em `tests/` no mesmo commit. Depois de mexer na configuração do
pytest, confira a contagem de coleta (240).

## CI — `.github/workflows/ci.yml`

Job `biblioteca`: `pip install -e biblioteca`, `py_compile`, `pytest tests/biblioteca tests/arquitetura -m "not thumbs"`.
Job `servicos`: `pnpm install --frozen-lockfile`, `pnpm -r build`, `pytest tests/servicos`. Não sobe Mongo nem Chromium.
Push com arquivo em `.github/workflows/` exige o escopo `workflow` no token do `gh`.

## Git

Identidade `carlosnetoaltoqi`; branch `main`, histórico linear; nada de push sem pedido. `*.aq` é
`binary` no `.gitattributes`. Gitignored e regerável: `input/`, `output/`, `storage/`, `.env`, `dist/`,
`node_modules/`, `tests/fixtures.local.json`. Nunca commitar `.env` nem `tests/fixtures.local.json`.

---

## 👉 Estado atual e pendências

**Estado (2026-09-11):** sessão de **auditoria cruzada** — cada afirmação de `docs/conhecimento/`
conferida contra o código, a ajuda do Builder e o catálogo oficial (31.611 peças, 3.929 grupos,
6.132 simbologias). Dezoito achados, registrados em
`docs/historico/sessoes/2026-09-11-auditoria-cruzada-da-documentacao.md`. Suíte em **273** na coleta
(251 passam, 19 pulam por fixture ausente), `pnpm -r build` verde.

Três viraram código:

- **A ajuda tinha 281 páginas de versão antiga** misturadas às atuais, e a busca as citava como
  iguais. O índice do `ferramentas.ajuda_builder` agora classifica cada página pelo alcance a partir
  do sumário — `toc` (2.208), `link` (76) e `orfa` (281) — e pula a órfã por padrão. As quatro
  páginas que sustentam ADR-020 a ADR-025 estão todas no sumário.
- **ADR-026**: o degrau 1 da ADR-024 estava morto — ninguém preenchia `entidadeIfc`, então todo
  `.aq` que entrava e saía do pipeline perdia a entidade IFC de origem e era reclassificado pelo
  nome. Agora a entidade atravessa (`build_catalog_from_aq` → `bim_products` → manifesto), o
  supertipo abstrato (tipos 4133…4142) deixou de vencer o nome, e nove entidades novas entraram na
  tabela (41 de 42).
- **Um segundo container de geometria**: 1.224 das 6.132 simbologias do catálogo oficial não são
  OQ3D — são `TStreamableObjectsContainer`, com dicionário de classes e instância por índice, muitas
  vezes face 2D extrudada em vez de malha. Nenhuma biblioteca de fabricante (schemas 552 a 615) usa
  isso; só o schema 625. O erro passou a nomear o formato em vez de dizer "sem assinatura".

**A ajuda decodifica os dois enums IFC.** `grupo_de_pecas.htm` lista as entidades IFC4 na ordem, e
essa ordem é o `TIPO_ENTIDADE_IFC` (4096 + índice) — 32 verificações contra os nomes de grupo do
catálogo, todas certas, com um par trocado que é erro de digitação da própria ajuda. A tabela das 42
entidades nomeadas está em `aplicacoes-builder.md`.

**Corrigido nos documentos:** `PROJETO_APLICACAO` tratado como enum com os valores que a ADR-024 já
corrigira; `2090` como "aquecedor a gás" (é inversor, e o tipo 4138 não existe em grupo nenhum);
"as três colunas IFC andam sempre juntas" (42 entidades, 52 combinações); a fronteira das versões de
schema (595 também não tem `ENTRADA_3D.DIAMETRO`); `SUBTIPO_IFC_2X3` "sempre igual" (438 grupos
divergem); a lista de erros que abortam a exportação (listava 5, o código levanta 8); e o **escopo
da ADR-025** — a escala de bitola é hidráulica, no elétrico o código 2 responde por 10.097 de 13.665
entradas. **Confirmados sem retoque:** ADR-022 (15.321/15.321), ADR-023 (4.206/4.206), ADR-020
(6.132/6.132 com `IMAGEM`), os 20 valores de bitmask, os 84 de aplicação, as 32 triplas do escritor
e a tabela inteira de `POSICIONAR_SIMBOLOGIA_3D`.

**Estado (2026-09-10, parte 3):** a exportação `.aq` passou a perguntar a **disciplina** em vez de
adivinhá-la (ADR-024, aceita e implementada). O cadastro da peça agora é montado num lugar só —
`biblioteca/bim_pipeline/aq/cadastro.py` —, chamado pelos dois escritores, que antes o montavam em
duplicata e divergiam. A classificação tem três degraus: entidade IFC que a fonte declara (31
entidades medidas, contra as 7 hidráulicas que o escritor conhecia) → vocabulário **da disciplina
escolhida** (sete, um por disciplina) → genérico da disciplina **com aviso**, no resumo da
exportação e na conferência "aplicação e disciplina" do `validar_aq`. A disciplina é campo obrigatório nos três
formulários de importação, pré-preenchido pelo palpite da fonte, gravado em
`bim_catalogs.disciplina`; exportar catálogo sem ela é **recusado**, com a mensagem dizendo o que
escolher. Entraram junto as correções que a medição sustentava: `PROJETO_APLICACAO` de água fria
4 (era 12 = hidráulico + sanitário) e de incêndio 20 (era 22), `POSICIONAR_SIMBOLOGIA_3D` por
aplicação (nulo em tubo, 0 em conexão, 1 em registro, 3 em bomba, 2 no elétrico e na climatização) e
`INDICE_SIMBOLO3D_SELECIONADO` em -1 nos dois escritores.

**O código de bitola não era o que se pensava (ADR-025).** Medido no catálogo oficial cruzando
`DIAMETRO_EP` com o **nome** da peça (o cruzamento com `DIAMETRO_PECA` não dá nada, porque essa
coluna guarda ora medida ora código): a escala é **em polegada** — 0 = 1/4" … 17 = 12". A tabela em
milímetro que usávamos era a equivalência do PVC esgoto, com `60 → 10` interpolado (não existe em
série nenhuma), e errava toda bitola de PVC soldável por um degrau. 40, 50 e 75 mm são ambíguos por
natureza (uma polegada em soldável, outra em esgoto): a série sai do título da biblioteca e, sem
ela, o bocal fica **sem código, com aviso**.

**ADR-023 aceito no Builder:** seis telas do Cadastro mostram, dentro da mesma biblioteca nossa,
peça com entradas em **"Pontos de ligação 3D: Sim"** (e a linha *Entradas* some) e peça com
`Entradas: 0` com o campo **desabilitado** em "Não" — confirma o rótulo e confirma que a propriedade
é alternativa a *Entradas*, como `peca.htm` diz. As mesmas telas mostram atuadores de HVAC e um
aquecedor a gás com "Aplicação: Conexão", que é a prova visual do defeito do ADR-024. Registro em
`docs/historico/sessoes/2026-09-10-b-a-disciplina-e-a-escala-em-polegada.md`.

Suíte em **268** na coleta (era 240); `pnpm -r build` verde nos 9 workspaces.

**Estado (2026-09-10):** a peça nossa **sai em planta** — aceitação de ADR-021 feita pelo usuário no
Builder, em três bibliotecas: desenharam a simbologia 3D, foram lançadas em projeto e saíram na
representação **unifiliar**. Duas coisas vieram do mesmo teste. O `WIREFRAME` não aparece no arquivo
depois, e não é defeito: o Builder o monta **em tempo de execução** e não grava de volta (equipe do
Builder) — o que encerra o plano B de escrever simbologia 2D. E o Cadastro mostrava **"Pontos de
ligação 3D: Não"** ao mesmo tempo em que desenhava os pontos no lugar certo. O rótulo é
**`PECA.CONEXAO_VOLUMETRICA`** (ADR-023), que os dois escritores gravavam em 0: a ajuda do Builder
(`peca.htm`) nomeia a propriedade e diz que ela é alternativa à propriedade *Entradas*, e no
catálogo oficial do Builder (`Catalog.db`, schema 625, 31.611 peças) `CONEXAO_VOLUMETRICA = 1`
implica ter `ENTRADA_3D` em **4.206 de 4.206** peças — a coluna sai por eliminação, porque a lista
de propriedades da peça bate uma a uma com as colunas e sobra um único booleano. Agora
`entradas_aq.marcar_pontos_de_ligacao` grava a marca de dentro do `gravar` (vale nos dois
escritores), junto com as colunas de seção de ADR-022, que continuam valendo como formato
(15.321/15.321 no catálogo oficial) mas **não** eram a causa do rótulo — hipótese testada e caída
no mesmo dia. `preencher_entradas_aq` varre também `.aq` que **já** tinha entradas; `validar_aq`
confere as duas coisas na conferência 9. Suíte em 240 na coleta. A ajuda em HTML do Builder entrou como fonte de consulta pela ferramenta `ferramentas.ajuda_builder`, e o método de engenharia reversa (medir → ajuda → experimento subtrativo) está em `aq-formato.md`. Também descartado por medição:
`LIGACAO_EP` não é índice da entrada (dentro da mesma peça as nativas trazem `(0,0,0)`, `(2,1)`,
`(0,3)`), segue enum indeterminado.

**Estado (2026-09-09):** a peça exportada agora tem **pontos de ligação**, e com eles a planta
(ADR-021). Uma peça nossa desenhava em 3D e, lançada em **planta**, saía com o símbolo padrão do
Builder — porque planta e corte vêm da simbologia 2D **ou** do `WIREFRAME`, e nossas 3.089 peças não
tinham nenhum dos dois (nas 15 nativas de fabricante, **zero** das 1.410 peças com 3D está sem os
dois). O `WIREFRAME` não precisa ser escrito: o Builder o gera, desde que a peça tenha
`ENTRADA_3D`/`ENTRADA_PECA` e "Bifiliar realista" (`OPCAO_RENDERIZACAO_PLANIFICADA`) não esteja em
"Simbologia 2D". Então o pipeline passou a escrever as entradas, derivadas da própria malha:
`geometria/bocais.py` acha o bocal (a face **anelar** na ponta de um tubo; a entrada nativa fica no
centro dela e o raio interno é a bitola) e `aq/entradas_aq.py` grava as duas tabelas nos dois
escritores. Medido contra as nativas: 21 de 21 entradas reencontradas numa de aquecedores (erro
mediano 0,00 cm) e 14 de 16 numa de conexões de esgoto (0,06 cm); onde a entrada foi clicada à mão
(uma de bombas, recuada atrás do flange) ou não é abertura de malha (rack), o detector não acha e
não inventa. `ferramentas.preencher_entradas_aq` conserta `.aq` já exportado. Suíte em 234 na coleta.
Também ficou medido o frame das `ENTRADA_3D` (centímetro Z-up, malha **com** o *placement* da
simbologia: `Rz(XY)·Ry(XZ)·Rx(YZ)` com ângulo positivo mais `DESLOCAMENTO_*`).

**Estado (2026-09-08):** o defeito que tornava toda biblioteca exportada **invisível no Builder** está
corrigido (ADR-020): `SIMBOLOGIA_3D.IMAGEM` — o BMP 100×100 de preview — é requisito do AltoQi Builder
para desenhar a peça, e os dois escritores a deixavam nula. Sem ela a peça abre no Cadastro com nome,
código, descrição e propriedades e **não desenha**, nem em 3D, com o OQ3D íntegro ao lado. O campo foi
isolado por experimento no Builder (nativa despida × cadastro nosso com geometria nativa × só sem
`IMAGEM` × só sem `WIREFRAME`); `WIREFRAME` e `ENTRADA_PECA`/`ENTRADA_3D` **não** são necessários para
desenhar. Agora `bim_pipeline.aq.imagem_aq.render(malhas)` rasteriza o BMP em numpy (sem Chromium; 42 s
para 1.399 simbologias), ligado ao `geo_to_aq` e ao `catalogo_to_aq`; o `validar_aq` falha se alguma
simbologia estiver sem `IMAGEM`; `ferramentas.preencher_imagem_aq` conserta um `.aq` já exportado sem
repetir a importação. Aceitação: peça nossa desenhada no ambiente 3D e lançada num projeto — o primeiro
registro disso (`docs/aceitacao.md` §4 agora exige o lançamento, não só a abertura).

**Arquitetura e fontes de entrada:** a arquitetura de `docs/arquitetura.md` está implementada por inteiro; suíte com
207 testes (coleta) verde — nesta máquina 17 pulam porque as fixtures `.aq` de `tests/fixtures.local.json`
não estão em `input/`; `pnpm -r build` e `pnpm start:*` funcionam do `dist/`. Fonte nova **famílias Revit**
(ADR-018): `.rfa`/`.zip` → catálogo pelo criador (`POST /importacoes/familias-revit`, página
`/importar/revit`), geometria do IFC/STEP/IGES irmão ou forma representativa; testado com um pacote real
de fabricante (fixture `rfa_familias`, 27 famílias, 3.061 tipos) até a exportação `.aq` pelo caminho
existente (`validar_aq` passa; a checagem "uma simbologia por peça" foi relaxada para geometria
compartilhada). **Projetos `.rvt`** entram pelo IFC irmão ou traduzidos pela APS Model Derivative com opt-in
na página (ADR-019; credenciais só no `.env` do criador; cache em `storage/bim/aps/`); testado com um modelo
de amostra real de fabricante (fixture `rvt_projeto`, 61 elementos → 8 tipos/produtos, um job na APS de 157 s,
depois tudo do cache) até o `.aq`. A APS **não aceita `.rfa`** — famílias continuam pela forma representativa.
**Peças auxiliares** de projetos `.rvt` (prefixo `x_`, Pipe Types) podem ser filtradas na importação via opção
`filtrarAuxiliares` (flag CLI `--filtrar-auxiliares`, checkbox na página — marcado por padrão); detecção em
`catalogo/fontes/familias_revit.py: eh_auxiliar`; documentado em `revit-familias.md` e ADR-019.
O `storage/` não tem os downloads do plugin web de CAD (`catallog/`) — refazê-los exige baixar do catálogo do
fabricante, o que depende de autorização explícita (Termos de Uso).

**Pendências do usuário:**
- **Aceitação de ADR-024 e ADR-025, no Builder:** reexportar as bibliotecas pelo pipeline corrigido,
  informando a disciplina de cada uma, e conferir no Cadastro que a **Aplicação** agora sai certa —
  a de válvulas e atuadores de HVAC é o caso de teste, porque tem de deixar de dizer "Conexão". No
  mesmo arquivo dá para conferir se o **Posicionar simbologia 3D** por aplicação orienta a peça
  certo no lançamento; os prints de 2026-09-10 mostram três modos diferentes em bibliotecas
  diferentes e, sem os `.aq` para cruzar, não permitem concluir nada sobre isso.
- Conferir no Builder as quatro bibliotecas de 2026-09-08 corrigidas com `preencher_imagem_aq` (as duas
  de famílias Revit, a de conexões e a do projeto `.rvt`) — a de conexões já foi verificada, com peça
  lançada no projeto e, em 2026-09-10, em planta.
- Nada pendente de push: os 8 commits de 2026-09-11 foram enviados (`main` == `origin/main` em
  `92372b6`). Confira com `git rev-list --count origin/main..HEAD`.
- **Próxima sessão: comece listando estas pendências e pergunte ao usuário por onde seguir (ou o
  que ele já testou) antes de executar qualquer coisa.** Os registros das duas últimas sessões, com
  as tentativas que falharam e as armadilhas, estão em
  `docs/historico/sessoes/2026-09-09-a-peca-que-nao-saia-em-planta.md` §5 e §7 e
  `docs/historico/sessoes/2026-09-10-a-planta-saiu-e-o-rotulo-nao.md` §5 e §7.
- ~~Aceitação de ADR-023~~ — **feita** em 2026-09-10, pelas seis telas do Cadastro. Os `.aq` do teste
  já não estão em `Downloads/teste-geometria-aq/`.
- **"Caixa de Cabos" sai como conexão (aberta, de propósito):** o termo não aparece em nenhuma peça
  do catálogo oficial, então pôr a palavra no vocabulário seria ajustar o classificador a uma
  biblioteca só. Se aparecer numa segunda fonte, vira regra (achado 18 da auditoria).
- **Bitola em biblioteca elétrica (decisão aberta):** `entradas_aq` converte raio medido → código
  em qualquer disciplina, e no elétrico o catálogo oficial grava **2** em 10.097 de 13.665 entradas,
  qualquer que seja a bitola. Copiar o 2 é palpite sobre valor não documentado; a medição está na
  auditoria de 2026-09-11 (achado 16).
- **Traduzir a classe IFC de um arquivo importado** (`IFCVALVE` → 2084) é o que falta para as outras
  fontes atravessarem a ponte da ADR-026 — hoje só o caminho do `.aq` a atravessa. Depende de fechar
  o nome → código das entidades de climatização, que são as que a ajuda não lista.
- **Uma pergunta para a engenharia**, que decide o que ainda está chutado no escritor: o que
  significa "Ligação" na aba de entradas do Cadastro — é o enum `LIGACAO_EP`, 0 a 3, que gravamos
  fixo em 0 porque `TIPO_LIGACAO` está vazia em toda nativa (medido: **não** é índice da entrada).
- ~~A lista de diâmetros do Builder na ordem~~ — **saiu por medição** (ADR-025): a escala é em
  polegada, 0 = 1/4" … 17 = 12". A pergunta à engenharia vira confirmação, não bloqueio; o que
  continua fora é o código 1 (5/16" pela posição, mas nenhuma peça do catálogo o usa com nome em
  polegada).
- ~~Como o cadastro nativo coloca as entradas~~ — **respondido pela ajuda do Builder**
  (`entradas_3d.htm`): é à mão, "clicando diretamente sobre a simbologia 3D, através do comando
  Adicionar Entradas 3D, na janela de Posicionamento da simbologia 3D". Não há rota automática, o
  que confirma a necessidade do nosso detector de bocais.
- Leitura humana dos 17 documentos de `docs/conhecimento/` e das quatro skills (escritos por agentes sob
  a guarda de termos; ninguém os leu de ponta a ponta ainda).
- Abrir no AltoQi Builder o `.aq` exportado do catálogo de plugin web e o do catálogo de famílias Revit
  (aceitação final, `docs/aceitacao.md` §4).
- Famílias Revit: se as formas representativas de equipamentos (caixa) bastam; se o trecho padrão de
  1000 mm é o desejado para o catálogo. APS: revogar e regerar o client secret que passou pelo chat da
  sessão de 2026-09-06.
- LICENSE (decisão em aberto).
