/**
 * upload.ts — nome do arquivo enviado, como o cliente mandou (S7.13).
 *
 * O `@nestjs/platform-express` 10 embute o **seu** multer (2.0.2 — o `multer@2.3` do
 * `package.json` só fornece o `diskStorage`; são duas cópias). O busboy dessa versão
 * decodifica o `filename` do multipart como latin1 e ela ainda não conhece
 * `defParamCharset`: `pecas_komeco_aquecimento_agua_a_gás.aq` chegava como `…a_gÃ¡s.aq`
 * no log, no `fileName` do import e — no CAD — no nome do produto derivado do arquivo.
 *
 * Refazemos a decodificação aqui: os bytes latin1 do nome recebido, lidos como UTF-8. A
 * guarda de ida e volta evita corromper um nome que já veio certo (se o multer do Nest um
 * dia decodificar UTF-8, `Buffer.from(nome, 'latin1')` não fecha e o nome fica como está).
 * `tests/test_www_config.py` acusa `originalname` usado sem passar por aqui.
 */
import * as crypto from 'node:crypto';
import * as os from 'node:os';
import * as path from 'node:path';
import { diskStorage } from 'multer';

export function nomeOriginalUtf8(originalname: string | undefined, padrao: string): string {
  if (!originalname) return padrao;
  const bytes = Buffer.from(originalname, 'latin1');
  const utf8 = bytes.toString('utf8');
  return Buffer.from(utf8, 'utf8').equals(bytes) ? utf8 : originalname;
}


/**
 * Armazenamento em disco para uploads grandes (uma biblioteca `.aq` passa de 600 MB — nada
 * disso cabe em RAM): o arquivo vai para `os.tmpdir()` como `<prefixo>-<uuid><ext>`. O prefixo
 * identifica o dono (quem apaga órfãos no boot procura por ele); a extensão é preservada para
 * a biblioteca decidir o formato. `prefixoDe` pode escolher o prefixo pela extensão.
 */
export function armazenamentoTemporario(prefixo: string | ((ext: string) => string), extPadrao = '') {
  return diskStorage({
    destination: (_req, _file, cb) => cb(null, os.tmpdir()),
    filename: (_req, file, cb) => {
      const ext = (path.extname(file.originalname ?? '') || extPadrao).toLowerCase();
      const p = typeof prefixo === 'function' ? prefixo(ext) : prefixo;
      cb(null, `${p}-${crypto.randomUUID()}${ext}`);
    },
  });
}
