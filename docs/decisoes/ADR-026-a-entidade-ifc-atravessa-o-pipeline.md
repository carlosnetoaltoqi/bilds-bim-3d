# ADR-026 — a entidade IFC atravessa o pipeline, e supertipo abstrato não classifica

**Status:** Aceita (2026-09-11) · implementada no mesmo dia

## Decisão

Três mudanças no primeiro degrau da ADR-024, todas saídas da auditoria cruzada de 2026-09-11
(`docs/historico/sessoes/2026-09-11-auditoria-cruzada-da-documentacao.md`):

1. **A entidade IFC do `.aq` de origem chega ao produto e volta na reexportação.**
   `catalogo.build_catalog_from_aq` grava `entidadeIfc` (o `GRUPO_PECA.ENTIDADE_IFC` do grupo) em
   cada produto; o criador a persiste em `bim_products.entidadeIfc` e a devolve no manifesto de
   exportação. Até aqui o campo era lido pelos dois escritores, estava no contrato e no tipo
   TypeScript — e **nenhuma fonte o preenchia**, o que deixava o degrau 1 morto fora dos testes.

2. **Supertipo abstrato do IFC não vence o nome.** As entidades cujo `TIPO_ENTIDADE_IFC` cai em
   4133…4142 (`IfcDistributionFlowElement`, `IfcFlowFitting`, `IfcFlowController`, `IfcFlowTerminal`,
   `IfcFlowMovingDevice`, `IfcFlowStorageDevice`, `IfcEnergyConversionDevice`,
   `IfcDistributionControlElement`, `IfcFlowTreatmentDevice`, `IfcBuildingElementProxy`) declaram
   que a peça **é uma peça de instalação**, e nada além disso. Elas deixam o vocabulário da
   disciplina falar primeiro e só valem como rede, quando o nome também não diz nada — aí ficam
   elas mesmas, que ao menos são o que a fonte afirmou, em vez do genérico da disciplina.

3. **Nove entidades novas na tabela** (`cadastro.IFC`, agora 41 de 42): 2058 `IfcElectricAppliance`,
   2061 `IfcElectricTimeControl`, 2063 `IfcFilter`, 2066 `IfcInterceptor`, 2070 `IfcOutlet`,
   2077 `IfcSensor`, 2082 `IfcTransformer`, 2083 `IfcUnitaryControlElement` e 2092
   `IfcSanitaryTerminal`. Fora ficou a **2057**, cujos dois grupos no catálogo oficial trazem
   `TIPO_ENTIDADE_IFC = 0` — cadastro incompleto do próprio catálogo, que não serve de padrão.

## Por quê

**O degrau 1 não existia na prática.** Medido no repositório inteiro: `entidadeIfc` aparecia como
leitura em `catalogo_to_aq.py` e `geo_to_aq.py`, no `manifesto-catalogo-aq.schema.json` e no tipo de
`pacotes/base` — e nenhuma escrita em lugar nenhum. Toda exportação caía no degrau 2, o vocabulário
por nome, que é justamente o mecanismo que a ADR-024 quis destronar. O caso mais caro era o
round-trip: um `.aq` nativo entrava com a entidade certa em `GRUPO_PECA` e saía reclassificado pelo
nome do grupo — perdendo informação que o arquivo de origem já trazia pronta.

**O supertipo confundia declaração com ignorância.** `2087` (`IfcDistributionFlowElement`) era ao
mesmo tempo o genérico da climatização no degrau 3 e um fato declarado no degrau 1. No catálogo
oficial, das 1.024 peças declaradas com 2087 a aplicação dominante é **conexão** (56 %), não
"equipamento" — ou seja, a entidade não prevê a aplicação, e fixá-la contra o nome só piora. As
entidades concretas continuam vencendo o nome, que é o que a ADR-024 decidiu e o que a medição
sustenta (`IfcValve`, `IfcPump`, condensadora: 100 % de concordância).

**As dez ausentes caíam no genérico com aviso** mesmo quando a fonte dizia exatamente o que a peça
era. São poucas peças no catálogo (2 a 26 cada), mas o custo de conhecê-las é uma linha de tabela.

## Consequências

- Reexportar uma biblioteca importada de `.aq` passa a preservar a entidade IFC de origem, e com
  ela a aplicação — sem depender do nome do grupo estar em português reconhecível.
- `bim_products` ganha a coluna `entidadeIfc` (`default: null`). Catálogos importados **antes** desta
  mudança não a têm: para eles nada muda, a classificação segue pelo nome. Reimportar preenche.
- A classificação por supertipo muda de resultado para fontes que declarem 4133…4142 — na prática,
  catálogos de climatização vindos de IFC. É mudança desejada: passa a valer o nome.

## Alternativas consideradas

- **Deduzir a entidade do nome e gravá-la** — é o degrau 2 com outro nome; não acrescenta.
- **Manter o supertipo vencendo e corrigir a aplicação dominante de 2087 para "conexão"** — trocaria
  um palpite por outro, e continuaria calando o nome, que no catálogo acerta mais.
- **Traduzir a classe IFC de um arquivo IFC importado (`IFCVALVE` → 2084)** — é o passo seguinte,
  e depende de fechar a tabela nome IFC4 → código para as entidades que a ajuda não lista
  (as de climatização). Fica como pendência, não como decisão.

## Ver também

`docs/conhecimento/aplicacoes-builder.md` §"Os dois enums IFC têm nome" e §"A ponte prática";
ADR-024 (os três degraus); `biblioteca/bim_pipeline/aq/cadastro.py`;
`tests/biblioteca/test_cadastro.py`, `tests/biblioteca/test_catalogo_to_aq.py`.
