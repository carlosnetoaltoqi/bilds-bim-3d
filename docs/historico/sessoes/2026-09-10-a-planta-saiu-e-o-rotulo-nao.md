# 2026-09-10 — a planta saiu, o rótulo não

**Data:** 2026-09-10 · **Status:** concluída com ressalva (a nova verificação no Builder é do usuário)
**Commits:** ver `git log`

---

## 1. O que era para fazer

A sessão abriu como o usuário pediu ao encerrar 2026-09-09: **listar as pendências e perguntar**
antes de executar. Ele respondeu com o resultado do teste no Builder, e o resultado virou a pauta.

## 2. O que o teste no Builder deu

O usuário gerou bibliotecas novas de três fabricantes pelo roteiro de teste e abriu no Builder.

**Funcionou:**
- todas as peças desenharam a simbologia 3D;
- lançadas em projeto, **saíram em planta**, na representação **unifiliar**, correta.

É a aceitação de ADR-021 — a primeira vez que uma peça nossa sai em planta.

**Não funcionou:**
- o `WIREFRAME` não foi gerado no arquivo. **Não é defeito:** a equipe do Builder informou que o
  wireframe é montado **em tempo de execução**, a cada uso, e não gravado de volta no `.aq`. Isso
  mata o plano B que estava na fila (escrever a simbologia 2D, blob Delphi próprio) — não há o que
  escrever.
- todas as peças abriram com **"Pontos de ligação 3D: Não"** no Cadastro — ao mesmo tempo em que os
  pontos de ligação apareciam desenhados no lugar certo (as bolinhas vermelhas).

## 3. A caçada ao rótulo

Contradição útil: as entradas estão gravadas e o Builder as lê (desenha), mas o rótulo não acende.
Logo, o rótulo não sai das tabelas de entrada. Quatro passos, nesta ordem:

1. **`PECA` coluna a coluna, correlacionando com "tem `ENTRADA_PECA`"** nas 14 nativas. Nenhuma
   coluna candidata (`POSICIONAR_SIMBOLOGIA_3D`, `CONEXAO_VOLUMETRICA`,
   `INCLUIR_REPRESENTACAO3D_PARAMETRICA`, `INDICE_SIMBOLO3D_SELECIONADO`, `FORMATO_PECA`) separa os
   dois grupos.
2. **`LIGACAO_EP` seria índice da entrada?** Seria bonito: explicaria o "enum de 0 a 3" como
   "peça com até 4 entradas". **Falso** — dentro da mesma peça as nativas trazem `(0,0,0)`,
   `(1,1)`, `(2,1)`, `(0,3)`: repetem e pulam. Continua enum, continua indeterminado.
3. **Procurar o texto do rótulo no executável do Builder** — não instalado nesta máquina.
4. **O método do ADR-020**: diferença sistemática entre *toda* nativa e *toda* saída nossa,
   restrita às peças **com** entrada. Sobraram exatamente duas colunas:
   `PECA.SECAO` e `PECA.DIAMETRO_INTERNO`, nulas em **1.441 de 1.441** peças nativas com entrada e
   iguais a 10 (o *default* do schema) nas 17 nossas.

O corte não é convenção de fabricante: acontece **dentro da mesma biblioteca** — na de esgoto,
1.115 peças com entrada com as duas nulas contra 48 sem entrada em 10; na de barramento, 220 contra
32. Seção e diâmetro de peça conectável moram nas entradas (`SECAO_EP`/`DIAMETRO_EP`); nenhum dos
dois escritores nomeava as colunas, então o *default* entrava sozinho. Virou ADR-022.

## 4. O que foi feito

- `entradas_aq.secao_para_as_entradas` — anula as duas colunas de toda peça que recebe entrada;
  chamada de dentro do `gravar`, então vale nos dois escritores e na ferramenta, sem repetição.
- `preencher_entradas_aq` ganhou uma varredura final sobre **todas** as peças com entrada. Sem ela,
  o `ja_tem` faria a ferramenta pular justamente os arquivos de 2026-09-09 — que já têm entradas e
  são exatamente os que precisam da correção. O relatório passou a dizer quantas peças ficaram com
  a seção nas entradas e quantas precisaram do conserto.
- `validar_aq` ganhou a conferência **9. pontos de ligação 3D**: peça com entrada sem seção no
  cadastro, e nenhuma `ENTRADA_PECA` órfã.
- Testes: `test_peca_com_entrada_fica_sem_secao_no_cadastro` (o caminho do escritor) e, em
  `test_ferramentas`, o caminho do conserto de um `.aq` que **já** tinha entradas.
- Docs: ADR-022; atualização no topo de ADR-021 (aceitação + wireframe em tempo de execução);
  `aq-formato.md` (linha nova na tabela da planta e seção do rótulo); `aq-escrita.md`;
  `aceitacao.md` §4, agora com cinco passos; o README das ADRs, que estava sem 020 e 021.
- Arquivos para o Builder, em `Downloads/teste-geometria-aq/`, prefixo `SECAO_`: as cópias
  corrigidas de `G_nosso_com_entradas`, `H_gerado_do_zero_com_entradas`, a de válvulas Schneider, a
  de conexões Tupy (que ganhou também as entradas: 20 em 4 simbologias) e a do projeto `.rvt`.

## 5. O que NÃO foi feito, e por quê

- **Não se escreveu simbologia 2D.** O plano B morreu com a informação do wireframe em tempo de
  execução: a planta já sai sem ele.
- **Não se mexeu em `LIGACAO_EP`.** Medido que não é índice; o significado segue sendo pergunta
  para a engenharia.
- **`SECAO_ENTRADAS_CORRIGIDO_Projeto4.aq` não serve de aceitação.** Ele carrega 107 entradas numa
  simbologia só — o artefato anterior à guarda de 38 bocais (`db16bef`). É o projeto `.rvt` inteiro
  virando uma peça; a guarda de hoje o rejeitaria.
- **A biblioteca de perfis (famílias Revit) ficou sem entrada**: 0 bocais em 3.061 peças. Perfil
  estrutural não tem bocal — não é defeito do detector, e por isso a cópia `SECAO_` dela foi
  descartada (não mudava nada).

## 6. Surpresas — onde a documentação estava errada

- Três lugares afirmavam que **sem** as tabelas de entrada a peça abre com "Pontos de ligação 3D:
  Não" — implicando que **com** elas o rótulo acende. O teste mostrou que não: o rótulo é outra
  coisa. Corrigido em `entradas_aq.py`, `preencher_entradas_aq.py`, `aq-escrita.md` e
  `aq-formato.md`.
- "O Builder gera o wireframe" estava certo, mas a leitura natural (gera **e grava**) estava
  errada. Não adianta reabrir o `.aq` procurando o blob para conferir que a planta funcionou.

## 7. Onde a próxima sessão começa

1. **A verificação no Builder** (do usuário): abrir `SECAO_G_nosso_com_entradas.aq` ou
   `SECAO_pecas_Tupy_TupyPres.aq` e olhar **só** o rótulo "Pontos de ligação 3D" no Cadastro. A
   planta já está aceita; o que está em teste é ADR-022.
2. **Se o rótulo acender:** ADR-022 vira fato, e o que sobra do assunto entradas são as perguntas
   para a engenharia (o enum `LIGACAO_EP`, a escala completa de diâmetros, se o cadastro nativo
   clica a entrada à mão).
3. **Se continuar em "Não":** não há mais diferença sistemática de coluna para perseguir — o
   próximo passo é experimento subtrativo no Builder, transplantando o cadastro de uma peça nativa
   que mostra "Sim" e removendo um campo por arquivo.
4. As pendências que não dependem disso continuam onde estavam: aceitação dos `.aq` de plugin web e
   de famílias Revit, leitura humana dos documentos de `docs/conhecimento/`, revogar o secret da
   APS, LICENSE.

## 8. Estado verificável ao encerrar

| O quê | Estado | Como conferir |
|---|---|---|
| árvore | limpa | `git status --short` |
| suíte | 239 na coleta | `python3 -m pytest --collect-only -q \| tail -1` |
| biblioteca + arquitetura | 171 passam, 19 pulam (fixtures ausentes aqui) | `python3 -m pytest tests/biblioteca tests/arquitetura -m "not thumbs" -q` |
| seção nas saídas corrigidas | nenhuma peça com entrada e seção no cadastro | `python3 -m bim_pipeline.cli.ferramentas.validar_aq …/SECAO_*.aq` |
| ADRs | até ADR-022 | `ls docs/decisoes/` |
