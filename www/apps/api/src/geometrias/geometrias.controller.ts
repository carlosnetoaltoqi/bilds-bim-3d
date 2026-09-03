import {
  BadRequestException,
  Body,
  Controller,
  Get,
  Inject,
  Logger,
  NotFoundException,
  Param,
  Post,
  Put,
  Req,
  Res,
} from '@nestjs/common';
import { InjectModel } from '@nestjs/mongoose';
import { Model } from 'mongoose';
import { Request, Response } from 'express';
import { BimProduct, BimProductDocument } from '../bim-products/bim-products.schema';
import { AssetStat, IGeometryStore } from '../geometry-store/geometry-store.interface';
import { ASSET_CACHE_CONTROL, assetEtag, ifNoneMatchSatisfied } from '../common/asset-cache';
import {
  GeoValidationError,
  geoStats,
  originalKeyFor,
  validateGeoBuffers,
} from '../common/geo-buffers';

/**
 * Leitura e escrita da geometria de um produto.
 *
 * GET  /geometrias/:id            — o JSON que o viewer consome (com ETag/304)
 * PUT  /geometrias/:id            — grava geometria editada (POC de edição, sem auth)
 * GET  /geometrias/:id/original   — o JSON como veio do .aq, se já houve edição
 * POST /geometrias/:id/restaurar  — volta ao original
 *
 * A primeira escrita copia o arquivo vivo para `<id>.orig.json` no mesmo prefixo
 * do import, para que "restaurar" nunca dependa do .aq de origem.
 */
@Controller('geometrias')
export class GeometriasController {
  private readonly logger = new Logger(GeometriasController.name);

  constructor(
    @InjectModel(BimProduct.name) private readonly productModel: Model<BimProductDocument>,
    @Inject('GEOMETRY_STORE') private readonly store: IGeometryStore,
  ) {}

  @Get(':productId')
  async getGeometry(
    @Param('productId') productId: string,
    @Req() req: Request,
    @Res() res: Response,
  ) {
    const product = await this.productModel.findById(productId).lean().exec();
    if (!product) throw new NotFoundException('produto não encontrado');
    await this.sendBlob(product.geoKey, req, res);
  }

  @Get(':productId/original')
  async getOriginal(
    @Param('productId') productId: string,
    @Req() req: Request,
    @Res() res: Response,
  ) {
    const product = await this.productModel.findById(productId).lean().exec();
    if (!product) throw new NotFoundException('produto não encontrado');
    // Sem edição ainda: o original É o arquivo vivo.
    const key = (await this.exists(originalKeyFor(product.geoKey))) ? originalKeyFor(product.geoKey) : product.geoKey;
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

    const origKey = originalKeyFor(product.geoKey);
    let backupFeito = false;
    if (!(await this.exists(origKey))) {
      try {
        const atual = await this.store.get(product.geoKey);
        await this.store.put(origKey, atual);
        backupFeito = true;
      } catch (err: any) {
        // Sem arquivo vivo não há o que preservar — segue gravando.
        if (err.code !== 'ENOENT') throw err;
      }
    }

    const blob = Buffer.from(JSON.stringify(geo));
    await this.store.put(product.geoKey, blob);
    const agora = new Date();
    await this.productModel.findByIdAndUpdate(productId, { geoEditadoEm: agora }).exec();

    const stats = geoStats(geo);
    this.logger.log(
      `geometria gravada — ${product.geoKey} — ${stats.vertices} vértices, ${stats.triangulos} triângulos, ${(blob.length / 1024).toFixed(0)} KB${backupFeito ? ' (original preservado)' : ''}`,
    );
    return { ok: true, geoKey: product.geoKey, geoEditadoEm: agora, backupFeito, ...stats, bytes: blob.length };
  }

  @Post(':productId/restaurar')
  async restaurar(@Param('productId') productId: string) {
    const product = await this.productModel.findById(productId).lean().exec();
    if (!product) throw new NotFoundException('produto não encontrado');

    const origKey = originalKeyFor(product.geoKey);
    if (!(await this.exists(origKey))) {
      return { ok: true, restaurado: false, motivo: 'geometria nunca foi editada' };
    }
    const orig = await this.store.get(origKey);
    await this.store.put(product.geoKey, orig);
    await this.store.delete(origKey).catch(() => {});
    await this.productModel.findByIdAndUpdate(productId, { geoEditadoEm: null }).exec();
    this.logger.log(`geometria restaurada — ${product.geoKey}`);
    return { ok: true, restaurado: true, geoKey: product.geoKey };
  }

  // ── helpers ──────────────────────────────────────────────────────────────

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
