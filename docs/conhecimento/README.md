# Conhecimento do projeto

O que se sabe sobre os formatos, os algoritmos e os padrões — sem fabricantes, arquivos ou caminhos da
POC (ADR-016; a guarda `tests/arquitetura/test_sem_empresas.py` cobre esta pasta). Censos de uma
biblioteca específica viram proporções; a evidência mora em `docs/historico/`. Modelo de escrita:
introdução de um parágrafo, seções curtas, tabelas, e ao fim "Onde está no código" e "Ver também".
**Conhecimento novo entra aqui**, no documento certo; `CLAUDE.md` só aponta.

| Documento | Assunto |
|---|---|
| `aq-formato.md` | o `.aq` (SQLite/ZIP), cp1252, sentinelas, código de diâmetro, enums, versões de schema, leitura |
| `aq-escrita.md` | escrever `.aq`: DDL 607, `EscritorAq`, uma peça, catálogo inteiro (cinco regras), erros que abortam, validação |
| `oq3d.md` | o binário OQ3D: cabeçalho, árvore, instâncias, rotação, leitura tolerante, escrita |
| `geometria.md` | o contrato `{pos,col,idx}`, eixos, dedup, malhas por cor, partes, bocais |
| `ifc.md` | IFC4: leitura, escrita (exportador do editor), verificação de ida e volta a 2 µm |
| `step-iges.md` | STEP/IGES com OpenCASCADE; costura de faces soltas e orientação pelo volume |
| `plugin-cad-catalogo-web.md` | plugin de CAD que é casca de um catálogo web: DLL, API, lead, IGES/RFA, termos de uso |
| `pdf-catalogo.md` | tabelas de um catálogo comercial em PDF; o que um PDF nunca determina |
| `formas-representativas.md` | geometria por parâmetro: dado × norma × invenção; os defeitos que passam em teste |
| `inferencia.md` | fabricante, título, slug e layout inferidos do `.aq` e do caminho |
| `miniaturas.md` | a mesma cena do viewer no Chromium; `page.evaluate` com string; harness por `http://` |
| `catalogo-modelo.md` | Import como máquina de estados, ponteiro de geometria, copy-on-write, remoção em cascata |
| `processos-filhos.md` | filho morre com o pai (stdin EOF), stdout × stderr, timeouts, códigos |
| `servicos-web.md` | armadilhas de Nest/Next e de ferramentas (201, Ajv 2020, tsbuildinfo, git clean…) |
| `zip-bilds-formato.md` | o formato genérico do pacote ZIP (o lado consumidor está em `docs/integracoes/bilds-com.md`) |
| `diagnostico.md` | sintoma → causa → o que fazer, para formatos e biblioteca |

Skills de agente (`docs/skills/`) são how-tos que apontam para cá; em cada uma, `referencias/` é um
symlink para esta pasta, para que a skill leve o conhecimento junto quando é usada de fora.
