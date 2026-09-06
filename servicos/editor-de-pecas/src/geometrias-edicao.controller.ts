import { BadRequestException, Body, Controller, Get, Inject, Logger, NotFoundException, Param, Post, Put, Req, Res } from '@nestjs/common';
import { InjectModel } from '@nestjs/mongoose';
import { Model } from 'mongoose';
import type { Request, Response } from 'express';
import { ASSET_CACHE_CONTROL, AssetStat, BimProduct, BimProductDocument, IGeometryStore, assetEtag, ifNoneMatchSatisfied } from '@bim/dominio';
import { GeoValidationError, geoStats, originalKeyFor, validateGeoBuffers } from '@bim/base';
import { CriadorClient } from './criador-client';

/**
 * Edição da geometria de um produto (editor de peças, ADR-014):
 *
 * GET  /geometrias/:id/original   — o JSON como veio do .aq, se já houve edição
 * PUT  /geometrias/:id            — grava geometria editada (sem auth — ADR-007)
 * POST /geometrias/:id/restaurar  — volta ao original
 *
 * Dois casos na primeira edição (ADR-005):
 *   geometria EXCLUSIVA do produto  → copia o arquivo vivo para `<id>.orig.json` no mesmo prefixo do
 *                                     import; "restaurar" nunca depende do .aq;
 *   geometria COMPARTILHADA (uma por simbologia; centenas de produtos podem apontar para a mesma)
 *                                   → copy-on-write: o produto ganha `geo/<importId>/<productId>.json` só
 *                                     dele e guarda a chave compartilhada em `geoKeyCompartilhada`.
 *
 * PUT e restaurar pedem ao criador de catálogos a miniatura nova (ADR-006) — o editor não tem Chromium.
 * Se o criador não responder, o produto recebe `thumbErro` e a resposta diz `miniatura: 'nao-solicitada'`.
 * A leitura (`GET /geometrias/:id`) é da API de catálogo.
 */
@Controller('geometrias')
export class GeometriasEdicaoController {
  private readonly logger = new Logger(GeometriasEdicaoController.name);

  constructor(
    @InjectModel(BimProduct.name) private readonly productModel: Model<BimProductDocument>,
    @Inject('GEOMETRY_STORE') private readonly store: IGeometryStore,
    private readonly criador: CriadorClient,
  ) {}

  @Get(':productId/original')
  async getOriginal(@Param('productId') productId: string, @Req() req: Request, @Res() res: Response) {
    const product = await this.productModel.findById(productId).lean().exec();
    if (!product) throw new NotFoundException('produto não encontrado');
    let key = product.geoKey;   // sem edição ainda: o original É o arquivo vivo
    if (product.geoKeyCompartilhada) key = product.geoKeyCompartilhada;
    else if (await this.exists(originalKeyFor(product.geoKey))) key = originalKeyFor(product.geoKey);
    await this.sendBlob(key, req, res);
  }

  @Put(':productId')
  async putGeometry(@Param('productId') productId: string, @Body() body: unknown) {
    const product = await this.productModel.findById(productId).lean().exec();
    if (!product) throw new NotFoundException('produto não encontrado');

    let geo;
    try {
      geo = validateGeoBuffers(body);
    } catch (err) {
      if (err instanceof GeoValidationError) throw new BadRequestException(err.message);
      throw err;
    }

    const agora = new Date();
    const set: Record<string, unknown> = { geoEditadoEm: agora };
    let geoKey = product.geoKey;
    let backupFeito = false;
    let copiaFeita = false;

    if (!product.geoKeyCompartilhada) {
      const outros = await this.productModel.countDocuments({ geoKey: product.geoKey, _id: { $ne: productId } }).exec();
      if (outros > 0) {
        // copy-on-write: este produto passa a ter arquivo próprio; o compartilhado é o "original"
        geoKey = `geo/${product.importId}/${productId}.json`;
        set.geoKey = geoKey;
        set.geoKeyCompartilhada = product.geoKey;
        copiaFeita = true;
      } else {
        const origKey = originalKeyFor(product.geoKey);
        if (!(await this.exists(origKey))) {
          try {
            await this.store.put(origKey, await this.store.get(product.geoKey));
            backupFeito = true;
          } catch (err: any) {
            if (err.code !== 'ENOENT') throw err;   // sem arquivo vivo não há o que preservar — segue gravando
          }
        }
      }
    }

    const blob = Buffer.from(JSON.stringify(geo));
    await this.store.put(geoKey, blob);
    await this.productModel.findByIdAndUpdate(productId, set).exec();

    const stats = geoStats(geo);
    this.logger.log(
      `geometria gravada — ${geoKey} — ${stats.vertices} vértices, ${stats.triangulos} triângulos, ${(blob.length / 1024).toFixed(0)} KB` +
        `${backupFeito ? ' (original preservado)' : ''}${copiaFeita ? ` (copy-on-write de ${product.geoKey})` : ''}`,
    );
    const miniatura = await this.pedirMiniatura(productId);
    return {
      ok: true,
      geoKey,
      geoEditadoEm: agora,
      backupFeito,
      copiaFeita,
      geoKeyCompartilhada: (set.geoKeyCompartilhada as string | undefined) ?? product.geoKeyCompartilhada ?? null,
      ...miniatura,
      ...stats,
      bytes: blob.length,
    };
  }

  @Post(':productId/restaurar')
  async restaurar(@Param('productId') productId: string) {
    const product = await this.productModel.findById(productId).lean().exec();
    if (!product) throw new NotFoundException('produto não encontrado');

    if (product.geoKeyCompartilhada) {
      // copy-on-write desfeito: volta a apontar para a geometria compartilhada e apaga a cópia
      await this.store.delete(product.geoKey).catch((e: any) => this.logger.warn(`não removeu ${product.geoKey} — ${e?.message ?? e}`));
      await this.productModel.findByIdAndUpdate(productId, { geoKey: product.geoKeyCompartilhada, geoKeyCompartilhada: null, geoEditadoEm: null }).exec();
      this.logger.log(`geometria restaurada — ${productId} volta a ${product.geoKeyCompartilhada}`);
      const miniatura = await this.pedirMiniatura(productId);
      return { ok: true, restaurado: true, geoKey: product.geoKeyCompartilhada, ...miniatura };
    }

    const origKey = originalKeyFor(product.geoKey);
    if (!(await this.exists(origKey))) {
      return { ok: true, restaurado: false, motivo: 'geometria nunca foi editada' };
    }
    const orig = await this.store.get(origKey);
    await this.store.put(product.geoKey, orig);
    await this.store.delete(origKey).catch((e: any) => this.logger.warn(`não removeu ${origKey} — ${e?.message ?? e}`));
    await this.productModel.findByIdAndUpdate(productId, { geoEditadoEm: null }).exec();
    this.logger.log(`geometria restaurada — ${product.geoKey}`);
    const miniatura = await this.pedirMiniatura(productId);
    return { ok: true, restaurado: true, geoKey: product.geoKey, ...miniatura };
  }

  // ── helpers ──────────────────────────────────────────────────────────────

  /** Pede a miniatura ao criador de catálogos; se ele não responder, registra em `thumbErro`. */
  private async pedirMiniatura(productId: string): Promise<{ miniatura: 'regerando' | 'nao-solicitada'; miniaturaErro: string | null }> {
    const r = await this.criador.regerarMiniatura(productId);
    if (r.ok) return { miniatura: 'regerando', miniaturaErro: null };
    const erro = r.erro ?? 'criador de catálogos não respondeu';
    this.logger.error(`[${productId.slice(0, 8)}] miniatura NÃO solicitada — ${erro}`);
    await this.productModel.findByIdAndUpdate(productId, { thumbErro: erro }).exec().catch(() => undefined);
    return { miniatura: 'nao-solicitada', miniaturaErro: erro };
  }

  private async exists(key: string): Promise<boolean> {
    try {
      await this.store.stat(key);
      return true;
    } catch (err: any) {
      if (err.code === 'ENOENT') return false;
      throw err;
    }
  }

  private async sendBlob(key: string, req: Request, res: Response) {
    let stat: AssetStat;
    try {
      stat = await this.store.stat(key);
    } catch (err: any) {
      if (err.code === 'ENOENT') throw new NotFoundException('geometria não encontrada');
      throw err;
    }

    const etag = assetEtag(key, stat);
    res.setHeader('ETag', etag);
    res.setHeader('Cache-Control', ASSET_CACHE_CONTROL);

    // 304 antes de ler o arquivo — evita puxar vários MB do disco a cada navegação.
    if (ifNoneMatchSatisfied(req.headers['if-none-match'], etag)) {
      res.status(304).end();
      return;
    }

    let blob: Buffer;
    try {
      blob = await this.store.get(key);
    } catch (err: any) {
      if (err.code === 'ENOENT') throw new NotFoundException('geometria não encontrada');
      throw err;
    }

    res.setHeader('Content-Type', 'application/json');
    res.send(blob);
  }
}
