// Harness de `nomeOriginalUtf8` (S7.13): o multer 2.0.2 embutido no Nest 10 entrega o nome do
// arquivo decodificado como latin1. Puro, roda com strip-types; imprime JSON para test_www_config.py.
//
//   node --no-warnings --experimental-strip-types tests/paridade/upload_nome.mts
import { nomeOriginalUtf8 } from '../../pacotes/base/src/upload.ts'

const mojibake = Buffer.from('pecas_fabricante_aquecimento_agua_a_gás.aq', 'utf8').toString('latin1') // o que o busboy entrega
process.stdout.write(JSON.stringify({
  mojibake_corrigido: nomeOriginalUtf8(mojibake, 'x'),
  ascii_intacto: nomeOriginalUtf8('pecas_fabricante_bombas_incendio_2026_04.1.aq', 'x'),
  ja_correto_intacto: nomeOriginalUtf8('peça — gás.stp', 'x'),      // se um dia o multer decodificar UTF-8
  fora_do_latin1_intacto: nomeOriginalUtf8('peça \u2014 x.ifc', 'x'),
  ausente_usa_padrao: nomeOriginalUtf8(undefined, 'upload.aq'),
  vazio_usa_padrao: nomeOriginalUtf8('', 'upload.aq'),
}))
