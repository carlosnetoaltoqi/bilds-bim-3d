/**
 * disciplinas.ts — as sete disciplinas do AltoQi Builder, para os formulários de importação.
 *
 * É uma **cópia deliberada** da lista de `pacotes/base/src/disciplinas.ts` (e, antes dela, de
 * `bim_pipeline.aq.cadastro.DISCIPLINAS`). O web não depende de `@bim/base`: aquele pacote é a
 * infraestrutura Nest dos serviços, e importá-lo aqui arrastaria o bootstrap do Nest para dentro
 * do bundle do Next — além de furar a regra de porte de `docs/arquitetura.md` §4, que é o web
 * sair levando só o que é seu.
 *
 * O que impede as três listas de divergirem é o teste `tests/paridade/test_disciplinas.py`, que
 * lê os três arquivos e compara slug a slug. A fonte da verdade é o Python, que é quem grava.
 */
export const DISCIPLINAS = [
  { slug: 'hidraulico', rotulo: 'Hidráulico (água fria e quente)' },
  { slug: 'sanitario', rotulo: 'Sanitário (esgoto e pluvial)' },
  { slug: 'incendio', rotulo: 'Incêndio' },
  { slug: 'gas', rotulo: 'Gás' },
  { slug: 'eletrico', rotulo: 'Elétrico (força, cabeamento, fotovoltaico)' },
  { slug: 'spda', rotulo: 'SPDA e aterramento' },
  { slug: 'climatizacao', rotulo: 'Climatização' },
] as const

export type DisciplinaSlug = (typeof DISCIPLINAS)[number]['slug']

/**
 * O palpite que **pré-preenche** o campo — nunca o que decide.
 *
 * Existe só para poupar um clique de quem importa: o campo continua obrigatório, e é a pessoa
 * que confirma. Sem pista reconhecível devolve `undefined` e a tela abre sem nada marcado, que é
 * o certo — adivinhar calado é o defeito que o ADR-024 corrige.
 */
export function palpiteDeDisciplina(...textos: (string | undefined | null)[]): DisciplinaSlug | undefined {
  const alvo = textos
    .filter(Boolean)
    .join(' ')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toUpperCase()
  const pistas: [DisciplinaSlug, RegExp][] = [
    ['sanitario', /\b(ESGOTO|PLUVIAL|SANITARI|VENTILACAO|SERIE NORMAL|SERIE REFORCADA)/],
    ['incendio', /\b(INCENDIO|SPRINKLER|HIDRANTE|MANGOTINHO)/],
    ['gas', /\b(GAS|GLP|GN)\b/],
    ['climatizacao', /\b(HVAC|CLIMATIZACAO|SPLIT|VRF|CONDENSADORA|EVAPORADORA|DUTO|AR CONDICIONADO)/],
    ['spda', /\b(SPDA|ATERRAMENTO|CAPTOR|PARA-RAIOS|PARA RAIOS)/],
    ['eletrico', /\b(ELETRIC|ELETROCALHA|ELETRODUTO|QUADRO|DISJUNTOR|TOMADA|RACK|FOTOVOLTAIC|CABEAMENTO|BARRAMENTO)/],
    ['hidraulico', /\b(AGUA FRIA|AGUA QUENTE|SOLDAVEL|ROSCAVEL|CPVC|PPR|HIDRAULIC|PEX)/],
  ]
  for (const [slug, re] of pistas) if (re.test(alvo)) return slug
  return undefined
}
