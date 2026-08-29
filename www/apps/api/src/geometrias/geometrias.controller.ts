import { Controller, Get, Inject, NotFoundException, Param, Res } from '@nestjs/common';
import { InjectModel } from '@nestjs/mongoose';
import { Model } from 'mongoose';
import { Response } from 'express';
import { BimProduct, BimProductDocument } from '../bim-products/bim-products.schema';
import { IGeometryStore } from '../geometry-store/geometry-store.interface';

@Controller('geometrias')
export class GeometriasController {
  constructor(
    @InjectModel(BimProduct.name) private readonly productModel: Model<BimProductDocument>,
    @Inject('GEOMETRY_STORE') private readonly store: IGeometryStore,
  ) {}

  @Get(':productId')
  async getGeometry(@Param('productId') productId: string, @Res() res: Response) {
    const product = await this.productModel.findById(productId).lean().exec();
    if (!product) throw new NotFoundException('produto não encontrado');

    let blob: Buffer;
    try {
      blob = await this.store.get(product.geoKey);
    } catch (err: any) {
      if (err.code === 'ENOENT') throw new NotFoundException('geometria não encontrada');
      throw err;
    }

    res.setHeader('Content-Type', 'application/json');
    res.send(blob);
  }
}
