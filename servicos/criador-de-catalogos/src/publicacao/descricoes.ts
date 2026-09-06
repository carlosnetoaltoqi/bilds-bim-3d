import * as path from 'node:path';
import type { ResumoMiniaturas } from '@bim/base';

/** `geo/<importId>/<stem>.json` → `<stem>` — o nome da geometria e da miniatura. */
export const stemDe = (geo: string) => path.basename(geo).replace(/\.json$/i, '');

/** Slug de um título de catálogo ou nome de peça CAD (a biblioteca Python tem o seu para o .aq). */
export function slugify(s: string): string {
  return (s ?? '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '');
}

/** Uma linha sobre o diagnóstico do pipeline: só o que não é o esperado (tubos/kits). */
export function descreveDiag(diag: any): string {
  if (!diag) return '';
  const partes: string[] = [];
  if (diag.pecas_sem_simbologia) partes.push(`${diag.pecas_sem_simbologia} peça(s) sem 3D (tubos/kits)`);
  const descartadas = (diag.sim_sem_blob ?? 0) + (diag.sim_nao_oq3d ?? 0) + (diag.sim_ilegivel?.length ?? 0) + (diag.sim_vazia?.length ?? 0);
  if (descartadas) partes.push(`AVISO: ${descartadas} simbologia(s) descartada(s), ${diag.pecas_sim_descartada ?? 0} peça(s) sem 3D por isso`);
  if (diag.avisos?.length) partes.push(`AVISO: ${diag.avisos.length} aviso(s) de parse`);
  return partes.join(' · ');
}

export function descreveResumo(r: ResumoMiniaturas): string {
  return r.falhas.length
    ? `${r.geradas.length} de ${r.total} miniatura(s) geradas — ${r.falhas.length} falharam`
    : `${r.geradas.length} miniatura(s) geradas`;
}
