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
export function nomeOriginalUtf8(originalname: string | undefined, padrao: string): string {
  if (!originalname) return padrao;
  const bytes = Buffer.from(originalname, 'latin1');
  const utf8 = bytes.toString('utf8');
  return Buffer.from(utf8, 'utf8').equals(bytes) ? utf8 : originalname;
}
