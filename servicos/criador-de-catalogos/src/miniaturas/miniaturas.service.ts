import { Inject, Injectable, Logger, NotFoundException } from '@nestjs/common';
import { InjectModel } from '@nestjs/mongoose';
import { Model } from 'mongoose';
import * as path from 'node:path';
import { BimImport, BimImportDocument, BimProduct, BimProductDocument, storagePath } from '@bim/dominio';
import type { ResumoMiniaturas } from '@bim/base';
import { FILA_MINIATURAS, Fila } from '../importacoes/fila';
import { PipelineService } from '../pipeline/pipeline.service';
import { descreveResumo, stemDe } from '../publicacao/descricoes';

/**
 * MiniaturasService — uma WebP por geometria, no Chromium (ADR-006).
 *
 *   gerarMiniaturas    as de um import inteiro, ainda na vaga da fila de importações (S7.13); grava
 *                      `thumbKey` em cada produto que usa a geometria e o resumo no import. Nunca rejeita.
 *   regerarMiniatura   a de UM produto, depois de uma edição de geometria (pedida pelo editor de peças):
 *                      fila própria, para não esperar um import de minutos.
 */
@Injectable()
export class MiniaturasService {
  private readonly logger = new Logger(MiniaturasService.name);

  constructor(
    @InjectModel(BimImport.name) private readonly importModel: Model<BimImportDocument>,
    @InjectModel(BimProduct.name) private readonly productModel: Model<BimProductDocument>,
    @Inject(FILA_MINIATURAS) private readonly filaMiniaturas: Fila,
    private readonly pipeline: PipelineService,
  ) {}

  /**
   * Miniaturas de um import: uma por geometria, gravada em cada produto que a usa. Registra o
   * resultado no documento do import (`thumbCount`, `thumbFailed`, `thumbError`, linha no `note`)
   * e no log. Nunca rejeita.
   */
  async gerarMiniaturas(importId: string, geoDir: string, geos: string[], porStem: Map<string, string[]>): Promise<ResumoMiniaturas | null> {
    const tag = `[${importId.slice(0, 8)}]`;
    const outDir = path.join(storagePath(), 'thumbs', importId);
    const t0 = Date.now();
    let resumo: ResumoMiniaturas | null = null;
    let erro: string | null = null;
    this.logger.log(`${tag} miniaturas — ${geos.length} geometria(s)`);
    try {
      let n = 0;
      resumo = await this.pipeline.miniaturas({
        geoDir, geos, outDir,
        onMiniatura: () => {
          n++;
          if (n === 1 || n % 50 === 0) this.logger.log(`${tag} thumbs: ${n}/${geos.length} — +${((Date.now() - t0) / 1000).toFixed(1)}s`);
        },
        onFalha: (stem, message) => this.logger.warn(`${tag} miniatura falhou — ${stem}: ${message}`),
      });
      if (resumo.geradas.length) {
        await this.productModel.bulkWrite(resumo.geradas.map((stem) => ({
          updateMany: { filter: { _id: { $in: porStem.get(stem) ?? [] } }, update: { $set: { thumbKey: `thumbs/${importId}/${stem}.webp` } } },
        })));
      }
    } catch (err: any) {
      erro = err?.message ?? String(err);
      this.logger.error(`${tag} ${erro}`);
    }
    const linha = erro ?? descreveResumo(resumo!);
    if (!erro && resumo!.falhas.length) this.logger.warn(`${tag} ${linha}`);
    else if (!erro) this.logger.log(`${tag} ${linha} em ${((Date.now() - t0) / 1000).toFixed(1)}s`);
    try {
      const imp = await this.importModel.findById(importId).select('note').lean().exec();
      const note = imp?.note ? `${imp.note} — ${linha}` : linha;
      await this.importModel.findByIdAndUpdate(importId, {
        note,
        thumbCount: resumo?.geradas.length ?? 0,
        thumbFailed: resumo ? resumo.falhas.length : geos.length,
        ...(erro ? { thumbError: erro } : {}),
        updatedAt: new Date(),
      }).exec();
    } catch (e: any) {
      this.logger.error(`${tag} não registrou o resultado das miniaturas no import — ${e?.message ?? e}`);
    }
    return resumo;
  }

  // ── miniatura de UM produto (após edição — A6) ───────────────────────────

  /**
   * Enfileira a miniatura nova de um produto (a API chama depois do PUT/restaurar). Volta na
   * hora com a posição na fila; o resultado vai para `thumbAtualizadaEm` ou `thumbErro` no produto.
   */
  async regerarMiniatura(productId: string): Promise<{ productId: string; naFrente: number }> {
    const p = await this.productModel.findById(productId).lean().exec();
    if (!p) throw new NotFoundException('produto não encontrado');
    let naFrente = 0;
    this.filaMiniaturas
      .executar(`thumb:${productId}`, () => this.renderizarMiniaturaDoProduto(p as any), (n) => { naFrente = n; })
      .catch((e: any) => this.logger.error(`[${productId.slice(0, 8)}] regeneração escapou — ${e?.message ?? e}`));
    return { productId, naFrente };
  }

  private async renderizarMiniaturaDoProduto(p: { _id: string; importId: string; geoKey: string }) {
    const tag = `[${p._id.slice(0, 8)}]`;
    const geoAbs = path.join(storagePath(), p.geoKey);
    const stem = stemDe(p.geoKey);
    const outDir = path.join(storagePath(), 'thumbs', p.importId);
    let erro: string | null = null;
    try {
      const r = await this.pipeline.miniaturas({ geoDir: path.dirname(geoAbs), geos: [path.basename(geoAbs)], outDir });
      if (r.falhas.length) erro = r.falhas[0].message;
      else if (!r.geradas.length) erro = 'thumbs.mjs terminou sem gerar a miniatura';
    } catch (err: any) {
      erro = err?.message ?? String(err);
    }
    if (erro) this.logger.error(`${tag} miniatura NÃO regerada após edição — ${erro}`);
    else this.logger.log(`${tag} miniatura regerada após edição — thumbs/${p.importId}/${stem}.webp`);
    try {
      await this.productModel.findByIdAndUpdate(p._id, erro
        ? { thumbErro: erro }
        : { thumbKey: `thumbs/${p.importId}/${stem}.webp`, thumbAtualizadaEm: new Date(), thumbErro: null }).exec();
    } catch (e: any) {
      this.logger.error(`${tag} não registrou o resultado da miniatura no produto — ${e?.message ?? e}`);
    }
  }

}
