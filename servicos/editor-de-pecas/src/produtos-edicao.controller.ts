import { BadRequestException, Body, Controller, NotFoundException, Param, Patch } from '@nestjs/common';
import { InjectModel } from '@nestjs/mongoose';
import { Model } from 'mongoose';
import { BimCatalog, BimCatalogDocument, BimProduct, BimProductDocument, recomputarCatalogo } from '@bim/dominio';
import { normalizarCurva, normalizarSpecs } from '@bim/base';
import { PatchProdutoDto } from './patch-produto.dto';

/**
 * Edição das informações de um produto (editor de peças, ADR-014; sem auth — ADR-007).
 *
 * PATCH /produtos/:id — atualiza nome, serie, specs, curva, potencia, conexoes. Só os campos presentes
 * no corpo são alterados. Na primeira edição guarda `infoOriginal` com os valores vindos do .aq, para
 * poder comparar e voltar. Trocar `serie` recomputa `catalog.filters` (a lista de séries distintas).
 * Tipos e limites do corpo estão em `patch-produto.dto.ts`, aplicados pelo `ValidationPipe` global.
 * A leitura (`GET /produtos/:id`) e o `DELETE` são da API de catálogo.
 */
const EDITAVEIS = ['nome', 'serie', 'specs', 'curva', 'potencia', 'conexoes'] as const;

@Controller('produtos')
export class ProdutosEdicaoController {
  constructor(
    @InjectModel(BimProduct.name) private readonly productModel: Model<BimProductDocument>,
    @InjectModel(BimCatalog.name) private readonly catalogModel: Model<BimCatalogDocument>,
  ) {}

  @Patch(':id')
  async patch(@Param('id') id: string, @Body() body: PatchProdutoDto) {
    const p = await this.productModel.findById(id).lean().exec();
    if (!p) throw new NotFoundException('produto não encontrado');

    const set: Record<string, unknown> = {};
    if (body.nome !== undefined) set.nome = body.nome;
    if (body.serie !== undefined) set.serie = body.serie;
    if (body.specs !== undefined) set.specs = normalizarSpecs(body.specs);
    if (body.curva !== undefined) set.curva = body.curva === null ? null : normalizarCurva(body.curva);
    if (body.potencia !== undefined) set.potencia = body.potencia;
    if (body.conexoes !== undefined) set.conexoes = body.conexoes;

    if (Object.keys(set).length === 0) throw new BadRequestException('nenhum campo editável no corpo');

    if (!p.infoOriginal) {
      const original: Record<string, unknown> = {};
      for (const c of EDITAVEIS) original[c] = (p as any)[c] ?? null;
      set.infoOriginal = original;
    }
    set.editadoEm = new Date();

    const atualizado = await this.productModel
      .findByIdAndUpdate(id, { $set: set }, { new: true })
      .lean()
      .exec();

    if (set.serie !== undefined && set.serie !== p.serie) {
      await recomputarCatalogo({ products: this.productModel as any, catalogs: this.catalogModel as any } as any, p.catalogId);
    }

    return this.toDto(atualizado!);
  }

  private toDto(p: any) {
    return {
      _id: p._id,
      catalogId: p.catalogId,
      importId: p.importId,
      id: p.id,
      nome: p.nome,
      serie: p.serie,
      specs: p.specs ?? {},
      curva: p.curva ?? null,
      potencia: p.potencia ?? null,
      conexoes: p.conexoes ?? null,
      geoKey: p.geoKey,
      geoUrl: `/geometrias/${p._id}`,
      thumbUrl: p.thumbKey ? `/thumbs/${p._id}` : null,
      editadoEm: p.editadoEm ?? null,
      geoEditadoEm: p.geoEditadoEm ?? null,
      // I14 grava os dois no produto; até a S7.13 o DTO não os devolvia e a edição parecia não regerar a miniatura
      thumbAtualizadaEm: p.thumbAtualizadaEm ?? null,
      thumbErro: p.thumbErro ?? null,
      infoOriginal: p.infoOriginal ?? null,
      createdAt: p.createdAt,
    };
  }
}
