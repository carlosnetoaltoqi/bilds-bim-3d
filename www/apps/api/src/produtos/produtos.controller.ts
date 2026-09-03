import {
  BadRequestException,
  Body,
  Controller,
  Get,
  NotFoundException,
  Param,
  Patch,
} from '@nestjs/common';
import { InjectModel } from '@nestjs/mongoose';
import { Model } from 'mongoose';
import { BimProduct, BimProductDocument } from '../bim-products/bim-products.schema';
import { BimCatalog, BimCatalogDocument } from '../bim-catalogs/bim-catalogs.schema';

/**
 * Leitura e edição das informações de um produto (POC de edição — sem auth).
 *
 * GET   /produtos/:id   — documento completo, com `infoOriginal` quando já editado
 * PATCH /produtos/:id   — atualiza nome, serie, specs, curva, potencia, conexoes
 *
 * Só os campos presentes no corpo são alterados. Na primeira edição o controller
 * guarda `infoOriginal` com os valores vindos do .aq, para poder comparar e voltar.
 * Trocar `serie` recomputa `catalog.filters`, que é a lista de séries distintas.
 */

const EDITAVEIS = ['nome', 'serie', 'specs', 'curva', 'potencia', 'conexoes'] as const;
type CampoEditavel = (typeof EDITAVEIS)[number];

interface PatchProdutoBody {
  nome?: string;
  serie?: string;
  specs?: Record<string, string>;
  curva?: number[][] | null;
  potencia?: number | null;
  conexoes?: string | null;
}

@Controller('produtos')
export class ProdutosController {
  constructor(
    @InjectModel(BimProduct.name) private readonly productModel: Model<BimProductDocument>,
    @InjectModel(BimCatalog.name) private readonly catalogModel: Model<BimCatalogDocument>,
  ) {}

  @Get(':id')
  async get(@Param('id') id: string) {
    const p = await this.productModel.findById(id).lean().exec();
    if (!p) throw new NotFoundException('produto não encontrado');
    return this.toDto(p);
  }

  @Patch(':id')
  async patch(@Param('id') id: string, @Body() body: PatchProdutoBody) {
    const p = await this.productModel.findById(id).lean().exec();
    if (!p) throw new NotFoundException('produto não encontrado');

    const set: Record<string, unknown> = {};

    if (body.nome !== undefined) {
      if (typeof body.nome !== 'string' || !body.nome.trim()) throw new BadRequestException('"nome" não pode ser vazio');
      set.nome = body.nome.trim();
    }
    if (body.serie !== undefined) {
      if (typeof body.serie !== 'string') throw new BadRequestException('"serie" deve ser texto');
      set.serie = body.serie.trim();
    }
    if (body.specs !== undefined) {
      if (!body.specs || typeof body.specs !== 'object' || Array.isArray(body.specs)) {
        throw new BadRequestException('"specs" deve ser um objeto { chave: valor }');
      }
      const specs: Record<string, string> = {};
      for (const [k, v] of Object.entries(body.specs)) {
        const chave = k.trim();
        if (!chave) continue;
        if (v === null || v === undefined) continue;
        specs[chave] = typeof v === 'string' ? v : String(v);
      }
      set.specs = specs;
    }
    if (body.curva !== undefined) {
      if (body.curva !== null) {
        if (!Array.isArray(body.curva)) throw new BadRequestException('"curva" deve ser array de pontos ou null');
        for (const [i, ponto] of body.curva.entries()) {
          if (!Array.isArray(ponto) || ponto.length < 2 || ponto.length > 4 || ponto.some((n) => typeof n !== 'number' || !Number.isFinite(n))) {
            throw new BadRequestException(`"curva[${i}]" deve ser [vazao, altura, potencia?, rendimento?] numéricos`);
          }
        }
        // Ordena por vazão — o gráfico assume isso.
        set.curva = body.curva.length ? [...body.curva].map((pt) => [pt[0], pt[1], pt[2] ?? 0, pt[3] ?? 0]).sort((a, b) => a[0] - b[0]) : null;
      } else {
        set.curva = null;
      }
    }
    if (body.potencia !== undefined) {
      if (body.potencia !== null && (typeof body.potencia !== 'number' || !Number.isFinite(body.potencia))) {
        throw new BadRequestException('"potencia" deve ser número ou null');
      }
      set.potencia = body.potencia;
    }
    if (body.conexoes !== undefined) {
      if (body.conexoes !== null && typeof body.conexoes !== 'string') throw new BadRequestException('"conexoes" deve ser texto ou null');
      set.conexoes = body.conexoes;
    }

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
      await this.recomputarFiltros(p.catalogId);
    }

    return this.toDto(atualizado!);
  }

  private async recomputarFiltros(catalogId: string) {
    const series = (await this.productModel.find({ catalogId }).distinct('serie').exec()) as string[];
    await this.catalogModel.findByIdAndUpdate(catalogId, { filters: series.filter((s) => s != null) }).exec();
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
      infoOriginal: p.infoOriginal ?? null,
      createdAt: p.createdAt,
    };
  }
}

export { EDITAVEIS };
export type { CampoEditavel, PatchProdutoBody };
