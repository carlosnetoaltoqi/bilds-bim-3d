/**
 * @bim/base — o que TODO serviço Nest deste repositório compartilha e que não é dado de negócio
 * (docs/arquitetura.md §2): processo filho, a porta para a biblioteca Python, upload em disco,
 * validação global, download em stream e o bootstrap do serviço. Não sabe nada de Mongo — isso é
 * do @bim/dominio, que só os serviços com dados importam.
 */
export * from './processo';
export * from './biblioteca-cli';
export * from './upload';
export * from './validacao';
export * from './download';
export * from './servico';
export * from './contratos';
export * from './geo-buffers';
export * from './validadores';
export * from './biblioteca';
