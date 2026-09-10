/**
 * disciplinas.ts — as sete disciplinas do AltoQi Builder, o espelho TypeScript de
 * `bim_pipeline.aq.cadastro.DISCIPLINAS`.
 *
 * A disciplina decide em que projeto do Builder a peça aparece no lançamento
 * (`GRUPO_PECA.PROJETO_APLICACAO`, que é bitmask). **Quem escolhe é quem importa** — o programa
 * não tem como adivinhar, e adivinhar errado foi o que fez uma biblioteca de válvulas de HVAC
 * sair inteira cadastrada como conexão hidráulica (ADR-024).
 *
 * A máscara aqui é só para exibição e conferência: quem grava o `.aq` é a biblioteca Python, e
 * a fonte da verdade da máscara é o `cadastro.py`. Se um dia divergirem, o Python vence — e o
 * teste `test_disciplinas_batem_com_o_typescript` acusa.
 */
export const DISCIPLINAS = [
  { slug: 'hidraulico', rotulo: 'Hidráulico (água fria e quente)', mascara: 4 },
  { slug: 'sanitario', rotulo: 'Sanitário (esgoto e pluvial)', mascara: 8 },
  { slug: 'incendio', rotulo: 'Incêndio', mascara: 20 },
  { slug: 'gas', rotulo: 'Gás', mascara: 36 },
  { slug: 'eletrico', rotulo: 'Elétrico (força, cabeamento, fotovoltaico)', mascara: 64 },
  { slug: 'spda', rotulo: 'SPDA e aterramento', mascara: 256 },
  { slug: 'climatizacao', rotulo: 'Climatização', mascara: 512 },
] as const;

export type DisciplinaSlug = (typeof DISCIPLINAS)[number]['slug'];

export const SLUGS_DISCIPLINA: readonly string[] = DISCIPLINAS.map((d) => d.slug);

export function ehDisciplina(valor: unknown): valor is DisciplinaSlug {
  return typeof valor === 'string' && SLUGS_DISCIPLINA.includes(valor);
}

export function rotuloDaDisciplina(slug: string | undefined | null): string {
  return DISCIPLINAS.find((d) => d.slug === slug)?.rotulo ?? 'não definida';
}

/**
 * O palpite que **pré-preenche** o campo na tela — nunca o que decide.
 *
 * Vem do título e do nome do arquivo da fonte, e existe só para poupar um clique de quem
 * importa: o campo continua obrigatório e a escolha continua sendo da pessoa. Sem palpite,
 * devolve `undefined` e a tela abre sem nada marcado.
 */
export function palpiteDeDisciplina(...textos: (string | undefined | null)[]): DisciplinaSlug | undefined {
  const alvo = textos
    .filter(Boolean)
    .join(' ')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toUpperCase();
  const pistas: [DisciplinaSlug, RegExp][] = [
    ['sanitario', /\b(ESGOTO|PLUVIAL|SANITARI|VENTILACAO|SERIE NORMAL|SERIE REFORCADA)/],
    ['incendio', /\b(INCENDIO|SPRINKLER|HIDRANTE|MANGOTINHO|COMBATE A INCENDIO)/],
    ['gas', /\b(GAS|GLP|GN\b)/],
    ['climatizacao', /\b(HVAC|CLIMATIZACAO|SPLIT|VRF|CONDENSADORA|EVAPORADORA|DUTO|AR CONDICIONADO)/],
    ['spda', /\b(SPDA|ATERRAMENTO|CAPTOR|PARA-RAIOS|PARA RAIOS)/],
    ['eletrico', /\b(ELETRIC|ELETROCALHA|ELETRODUTO|QUADRO|DISJUNTOR|TOMADA|RACK|FOTOVOLTAIC|CABEAMENTO|BARRAMENTO)/],
    ['hidraulico', /\b(AGUA FRIA|AGUA QUENTE|SOLDAVEL|ROSCAVEL|CPVC|PPR|HIDRAULIC|PEX)/],
  ];
  for (const [slug, re] of pistas) if (re.test(alvo)) return slug;
  return undefined;
}
