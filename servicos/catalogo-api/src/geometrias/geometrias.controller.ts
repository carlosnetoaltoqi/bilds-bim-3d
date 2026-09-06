import { Controller, Get, Inject, NotFoundException, Param, Req, Res } from '@nestjs/common';
import { InjectModel } from '@nestjs/mongoose';
import { Model } from 'mongoose';
import type { Request, Response } from 'express';
import { ASSET_CACHE_CONTROL, AssetStat, BimProduct, BimProductDocument, IGeometryStore, assetEtag, ifNoneMatchSatisfied } from '@bim/dominio';

/**
 * Leitura da geometria de um produto: GET /geometrias/:id — o JSON que o viewer consome (com ETag/304).
 * A edição (PUT, restaurar, original) é do editor de peças (:4400, ADR-014).
 */
@Controller('geometrias')
export class GeometriasController {
  constructor(
    @InjectModel(BimProduct.name) private readonly productModel: Model<BimProductDocument>,
    @Inject('GEOMETRY_STORE') private readonly store: IGeometryStore,
  ) {}

  @Get(':productId')
  async getGeometry(@Param('productId') productId: string, @Req() req: Request, @Res() res: Response) {
    const product = await this.productModel.findById(productId).lean().exec();
    if (!product) throw new NotFoundException('produto não encontrado');
    await this.sendBlob(product.geoKey, req, res);
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
