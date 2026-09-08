# 2026-09-09 — a peça que desenhava em 3D e não saía em planta

**Data:** 2026-09-09 · **Status:** concluída com ressalva (a aceitação no Builder é do usuário)
**Commits:** `edde3d3`, `58a7888`, `312a7e5`, `d7a132f`, `db16bef` — **não enviados**

---

## 1. O que era para fazer

Os dois itens decididos ao encerrar 2026-09-08, nesta ordem: (1) `WIREFRAME`, a representação em
planta e corte, começando pelo teste de minutos que poderia dispensá-lo; (2)
`ENTRADA_PECA`/`ENTRADA_3D`, os bocais e o encaixe em tubulação, cujo problema conhecido era a
**origem das posições** — nenhuma fonte de geometria marca bocal.

Os dois viraram um só: as entradas são o que resolve a planta, e o `WIREFRAME` saiu de escopo.

## 2. O que foi feito

- `biblioteca/bim_pipeline/geometria/bocais.py` — acha os pontos de ligação na malha. Teste:
  `tests/biblioteca/test_bocais.py` (11 casos, malha sintética em `tests/malhas_sinteticas.py`).
- `biblioteca/bim_pipeline/aq/entradas_aq.py` — bocal → linha de `ENTRADA_3D`/`ENTRADA_PECA`, com o
  código de bitola e o azimute. Teste: `tests/biblioteca/test_entradas_aq.py`.
- As duas tabelas nos **dois** escritores (`saida/geo_to_aq.py`, `saida/catalogo_to_aq.py`), com a
  guarda de quantidade e `geometrias_sem_entrada` no resumo do catálogo.
- `biblioteca/bim_pipeline/cli/ferramentas/preencher_entradas_aq.py` — preenche num `.aq` já
  exportado, idempotente. Teste em `tests/biblioteca/test_ferramentas.py`.
- Documentação: ADR-021; `aq-formato.md` (o que desenha em planta, o frame das `ENTRADA_3D`, o
  domínio de `OPCAO_RENDERIZACAO_PLANIFICADA`); `aq-escrita.md` (seção das entradas e os limites);
  `geometria.md` + `CONCEPTS.md` (bocal: marcador × ponto de ligação, e o placar do detector);
  `diagnostico.md` (quatro sintomas novos); `aceitacao.md` §4 (agora quatro passos, com planta);
  ADR-020 corrigido no documento de origem; skill `leitor-biblioteca-aq` 2.12.0.
- Arquivos para o Builder, fora do repositório, em `/mnt/c/Users/carlos.neto/Downloads/teste-geometria-aq/`:
  `G_nosso_com_entradas.aq` (conexões nossas, 10 entradas em 4 simbologias — **é o do teste de
  planta**), `H_gerado_do_zero_com_entradas.aq` (ida e volta completa a partir de uma nativa
  pequena de dispositivos elétricos), `ENTRADAS_CORRIGIDO_pecas_Schneider_*.aq` (válvulas, 14
  entradas em 19 simbologias).

## 3. O que foi verificado — e como

**No Builder, pelo usuário** (é o que fechou o item 1). Uma peça nossa lançada em planta sai com o
símbolo padrão — círculo com triângulo vermelho. Depois, três nativas de fabricante, cada uma num
arranjo diferente: aquecedor de passagem (só `WIREFRAME`) desenha; conexão de esgoto, grupo "Sifão
Expert" (só `WIREFRAME`, tipo 2) desenha; rack de piso 16U (só simbologia 2D) desenha. Ou seja:
qualquer um dos dois basta, e nós não tínhamos nenhum.

**Nos arquivos**, por medição nas 15 nativas de fabricante (a de PVC gerada de PDF foi descartada
como evidência pelo usuário — não é verdade de campo):

| medição | resultado |
|---|---|
| peças com 3D sem simbologia 2D **e** sem `WIREFRAME` | 0 de 1.410 nativas; 3.089 de 3.089 nossas |
| convenção do frame das `ENTRADA_3D` (6 ordens × 2 sinais, 48 simbologias) | `Rz(XY)·Ry(XZ)·Rx(YZ)` positivo + `DESLOCAMENTO_*`: mediana 2,37 cm contra 5,39+ do sinal negativo |
| entradas × marcador verde/azul do OQ3D | nenhuma nativa com `ENTRADA_3D` tem malha com cor de marcador |
| raio interno do bocal × código de bitola | 2,56 cm↔50 mm, 3,78↔75, 5,08↔100, 7,50↔150, 10,00↔200 |
| entradas por simbologia | 2 em 46 %, ≤4 em 68 %, máximo 38 |

**Placar do detector** contra as entradas nativas (0,5 cm): aquecedores 21/21 (erro mediano
0,00 cm), conexões de esgoto 14/16 (0,06 cm), bombas pressurizadoras 10/16, bombas de incêndio
1/16, rack 0/105. Reproduzir: ver `docs/conhecimento/geometria.md`, seção Bocais.

**Suíte:** 238 na coleta; `python3 -m pytest tests/biblioteca tests/arquitetura -m "not thumbs"` dá
166 passando e 19 pulando por fixture ausente nesta máquina. `validar_aq` sem ressalvas em `G` e `H`.

## 4. Decisões tomadas

- **ADR-021** — as entradas vêm da malha; o `WIREFRAME` não é escrito. O raciocínio completo está lá.
- **A guarda de 38 bocais descarta, não trunca.** Escolher 38 de 107 seria inventar quais são ponto
  de ligação.
- **`LIGACAO_EP` fica em 0** enquanto o enum não estiver decodificado, e isso está escrito no
  módulo, não só aqui.
- **Bitola fora da escala do AltoQi fica sem código**, em vez de virar o vizinho mais próximo.

## 5. O que NÃO foi feito, e por quê

- **Reverter o blob de `WIREFRAME`** — era o item 1, e deixou de fazer sentido: o Builder o gera.
- **Simbologia 2D** — o outro caminho da planta segue por escrever. Se a geração do wireframe não
  bastar, é o próximo alvo, e o menor exemplar nativo tem 6 KB contra 0,4–2 MB do wireframe.
- **Melhorar o detector para bomba e para elétrica.** A bomba tem a entrada nativa recuada 0,6 a
  4,5 cm atrás da face do flange — cadastro à mão, segundo a engenharia; num rack, "ponto de
  ligação" é entrada de cabo e não abertura de malha. Nenhum dos dois é bug do detector.
- **Tentativas que falharam, para não repetir:**
  1. procurar bocal como **buraco na malha** (laço de arestas de borda) acha **zero** numa nativa de
     aquecedores — a malha é estanque e a ponta do tubo é fechada por triângulos coplanares;
  2. exigir **parede fina** (raio interno/externo ≥ 0,7) e depois relaxar para "face de flange com
     furo atrás" **não** melhorou a nativa de bombas — o problema lá é o recuo, não a forma;
  3. agrupar triângulos coplanares por **plano quantizado** (balde) é rápido e **errado**: grupo que
     cruza a fronteira do balde sai partido, e o placar das bombas caiu de 10/16 para 7/16 sem que
     nenhum teste acusasse. A união exata sobre pares adjacentes é rápida do mesmo jeito.

## 6. Surpresas — onde a documentação estava errada

- **ADR-020 e `aq-formato.md` diziam que `WIREFRAME` e entradas "não são necessários".** Verdade só
  para o ambiente 3D; para planta e corte são o que resolve. Corrigido nos dois documentos de
  origem, com a distinção explícita.
- **`POSICIONAR_SIMBOLOGIA_3D = 3` estava documentado como "as colunas exatas de uma peça com 3D",
  como um fabricante grava.** É enum de 0 a 6 que varia **entre peças que compartilham a
  simbologia**: é orientação de inserção, não representação. Nós gravamos valor fixo nos dois
  escritores (3 no de catálogo, 0 no de uma peça) e os dois desenham; corrigido em `aq-formato.md`.
- **A lição de 2026-09-08 sobre "difere da nativa não é prova" mordeu de novo, quatro vezes**:
  `SIMBOLO_SELECIONADO`, `INDICE_SIMBOLO3D_SELECIONADO`, as dimensões na sentinela e o
  `POSICIONAR_SIMBOLOGIA_3D` foram levantados como suspeitos do símbolo em planta e todos aparecem
  em nativa que funciona. O que fechou o caso foi experimento no Builder, como antes.

## 7. Onde a próxima sessão começa

**Antes de executar qualquer coisa: liste o que está pendente e pergunte ao usuário por onde
seguir** (ou o que ele já testou). Foi o pedido explícito ao encerrar esta sessão.

O que está pendente, com o que cada item destrava:

1. **Aceitação no Builder de `G_nosso_com_entradas.aq`** — "Pontos de ligação 3D: Sim" no Cadastro,
   peça lançada, planta e corte (`aceitacao.md` §4, passos 2 e 4). É o único jeito de saber se
   ADR-021 fecha o problema da planta. Só o usuário pode fazer.
2. **Três perguntas para a engenharia da AltoQi**, que decidem o que ainda está chutado:
   o que é "Ligação" na aba de entradas (o enum `LIGACAO_EP`, 0 a 3); a **lista de diâmetros do
   Builder na ordem** (decodifica a escala de `DIAMETRO_EP` — temos 40→8, 50→9, 60→10, 75→11,
   100→12, 150→14, 200→15 e nada abaixo de 40, o que deixa sem código toda bitola de sistema que
   não é PVC); e como o cadastro nativo coloca a entrada (clique ou derivação), porque se o Builder
   deriva sozinho a heurística pode ser dispensável para quem cadastra lá.
3. **Se a planta não sair mesmo com as entradas:** o caminho é a **simbologia 2D**
   (`CLASSE_SIMBOLOGIA` → `GRUPO_SIMBOLOGIA` → `CONTEUDO_SIMBOLOGIA.SIMBOLOGIA` → `SIMBOLOGIA` →
   `PECA_SIMBOLOGIA`). Blob Delphi próprio, `TIPO_SIMBOLOGIA` sempre `'INTERNO'` nas 1.164 linhas
   nativas (não há rota por referência externa), e o menor exemplar tem 6.088 bytes — uma ordem de
   grandeza abaixo do wireframe, e por isso o alvo preferível.
4. **Detector para bocal recuado**, se a engenharia disser que o recuo da nativa de bombas é
   convenção e não descuido: `bocais` já devolve o eixo de cada bocal, então recuar é uma soma.
5. Pendências antigas que seguem abertas: leitura humana dos 17 documentos de `docs/conhecimento/`;
   as quatro bibliotecas de 2026-09-08 conferidas no Builder (só a de conexões foi); LICENSE; push.

**O que precisa estar de pé:** nada para os itens 1 a 4 — é biblioteca Python e Builder. Para
exportar de novo pelo criador (:4100), `pnpm dev:criador` depois de mudar TypeScript.

**Armadilhas concretas desta sessão:** o `sqlite3` do Python estoura em nome acentuado de nativa
(`open_aq` já resolve — use ele, não `sqlite3.connect` cru); nunca `SELECT *` em `SIMBOLOGIA_3D`
(traz o `WIREFRAME`, centenas de MB — e `typeof(WIREFRAME)` é a forma barata de saber se está
preenchido, `LENGTH` lê o blob inteiro e leva minutos numa biblioteca de 647 MB); `ENTRADA_3D` não
tem `TIPO_SECAO` nem `DIAMETRO` nos schemas antigos, então monte o `SELECT` a partir do
`PRAGMA table_info`; e a regra ADR-016 vale para docstring e teste também — o nome do fabricante
não entra em `biblioteca/`, `docs/conhecimento/` nem `tests/`.

## 8. Estado verificável ao encerrar

| O quê | Estado | Como conferir |
|---|---|---|
| `main` | 5 commits desta sessão, **nada enviado** | `git log --oneline -5`; `git rev-list --count origin/main..HEAD` |
| árvore | limpa | `git status --short` |
| suíte | 238 na coleta | `python3 -m pytest --collect-only -q \| tail -1` |
| biblioteca + arquitetura | 166 passam, 19 pulam (fixtures ausentes aqui) | `python3 -m pytest tests/biblioteca tests/arquitetura -m "not thumbs" -q` |
| entradas numa saída nossa | 10 em 4 simbologias | `sqlite3 …/G_nosso_com_entradas.aq 'SELECT COUNT(*) FROM ENTRADA_3D'` |
| ida e volta de uma nativa pequena | 32 peças, 18 simbologias, 3,3 MB, 9,4 s | os três comandos da seção 2 (`catalogo_de_aq` → manifesto → `catalogo_para_aq`) |
| ADRs | até ADR-021 | `ls docs/decisoes/` |
