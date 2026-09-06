# Modelo de dados do catálogo — import, geometria compartilhada, edição

## Import como máquina de estados

Toda entrada — uma biblioteca `.aq`/`.zip`, uma peça CAD avulsa (STEP/IGES/IFC) ou o catálogo web
de um plugin de CAD — vira um documento de import com um `status`:

```
recebido → parseando → gravando → publicado | vazio | falhou
```

`recebido` é só a fila: o upload chegou, mas ainda não começou a rodar (`note` diz "na fila — N à
frente" enquanto espera). `parseando` é o pipeline Python rodando; `gravando`, o upsert no banco.
Os três estados finais não são intercambiáveis:

- **`publicado`** — pelo menos um produto foi gravado, catálogo criado ou substituído.
- **`vazio`** — resultado **válido**, não erro: uma biblioteca só de tubos e kits, sem nenhuma
  peça com geometria fixa, produz zero produtos e o import termina aqui sem tocar o catálogo.
- **`falhou`** — qualquer exceção no meio do caminho. A limpeza é obrigatória e best-effort: apaga
  os produtos que já tinham sido gravados neste import e o prefixo de geometria que o pipeline
  gravou, registrando avisos (não abortando) se algum arquivo já não existir mais.

As miniaturas rodam **depois** do bloco publicado/vazio/falhou, ainda dentro da vaga da fila —
ver "Fila" abaixo — e nunca rejeitam: uma falha de miniatura vira `thumbCount`/`thumbFailed`/
`thumbError` no documento do import, não uma reversão do que já foi publicado.

## Ponteiro de geometria

O acoplamento entre o banco de dados e os arquivos é só um campo por produto:

| Campo | Formato da chave | Aponta para |
|---|---|---|
| `geoKey` | `geo/<importId>/<nome>.json` | a geometria que o produto usa |
| `thumbKey` | `thumbs/<importId>/<nome>.webp` | a miniatura pré-renderizada dessa geometria |

Ninguém resolve esse caminho na mão fora do `IGeometryStore` — nem para ler, nem para montar URL
pública. É a única costura entre "documento no banco" e "arquivo no storage".

## Uma geometria por simbologia, compartilhada por N produtos

O pipeline grava uma geometria por **simbologia** (a malha 3D de origem), não uma por produto.
Produtos que diferem só em dado — orientação de montagem, cor de acabamento, potência — apontam
para o mesmo `geoKey`. Numa biblioteca real de conexões isso é a diferença entre centenas de
produtos e menos da metade desse número em arquivos de geometria: 856 produtos → 448 geometrias.
O cache de geometria do viewer é por **URL**, não por produto, então o arquivo compartilhado é
baixado uma única vez independente de quantos produtos o referenciam.

## Copy-on-write na primeira edição

Editar a geometria de **um** produto não pode mudar os produtos irmãos que compartilham a mesma
simbologia; apagar um produto não pode apagar a geometria dos que restam. A regra depende de se a
geometria já é exclusiva do produto ou ainda compartilhada:

- **Geometria exclusiva** (nenhum outro produto usa o mesmo `geoKey`): a primeira escrita copia o
  arquivo vivo para `<geoKey-sem-extensão>.orig.json`, no mesmo prefixo do import, antes de
  sobrescrever. "Restaurar" nunca depende de reabrir o `.aq` original — copia esse arquivo de
  volta.
- **Geometria compartilhada** (outros produtos contam no `countDocuments` pelo mesmo `geoKey`):
  o produto ganha um arquivo só dele, `geo/<importId>/<productId>.json`, e o `geoKey` antigo
  (compartilhado) é guardado em `geoKeyCompartilhada`. Os irmãos não mudam — continuam apontando
  para o `geoKey` original. "Restaurar" nesse caso volta a apontar `geoKey` para
  `geoKeyCompartilhada` e limpa o arquivo próprio.

```typescript
if (!product.geoKeyCompartilhada) {
  const outros = await productModel.countDocuments({ geoKey: product.geoKey, _id: { $ne: productId } }).exec();
  if (outros > 0) {
    // copy-on-write: este produto passa a ter arquivo próprio; o compartilhado vira o "original"
    geoKey = `geo/${product.importId}/${productId}.json`;
    set.geoKey = geoKey;
    set.geoKeyCompartilhada = product.geoKey;
  } else {
    // já era exclusivo — preserva o `.orig.json` se ainda não existir
  }
}
```

O snapshot dos campos editáveis (nome, série, specs) como vieram do `.aq` vai em `infoOriginal`,
gravado também na primeira edição — é o que permite "voltar" às informações sem reabrir a origem.

## Remoção em cascata: só apaga o compartilhado com o último usuário

A contrapartida do copy-on-write é a remoção: um arquivo de geometria (ou de miniatura) só é
apagado do storage quando **nenhum outro produto** ainda aponta para ele.

```typescript
if (p.geoKeyCompartilhada) {
  // era copy-on-write: o arquivo em geoKey é só dele — sempre seguro apagar
  await apagarChave(store, p.geoKey, r);
} else {
  const outros = await productModel.countDocuments({ geoKey: p.geoKey, _id: { $ne: productId } }).exec();
  if (outros === 0) {
    await apagarChave(store, p.geoKey, r);
    await apagarChave(store, originalKeyFor(p.geoKey), r);   // o .orig.json, se existir
  }
}
```

A mesma checagem vale para `thumbKey`. A remoção em cascata sobe por nível — apagar um catálogo
apaga todos os produtos, os prefixos `geo/<importId>` e `thumbs/<importId>` de cada import que o
alimentou e os documentos de import; apagar uma empresa repete isso por catálogo. Apagar uma
importação sozinha é recusado enquanto ela ainda está em andamento (`recebido`/`parseando`/
`gravando`) — a fila e o pipeline ainda têm a mão nela.

## Substituição de import pelo mesmo slug

Reimportar uma biblioteca que gera o mesmo `slug` de catálogo faz **upsert**: o catálogo existente
é atualizado (não recriado), os produtos do import anterior são apagados e os prefixos de
geometria e miniatura desse import anterior são removidos do storage — depois que os novos
produtos já foram gravados, nunca antes (evita uma janela sem produto nenhum se a gravação nova
falhar no meio).

## Miniatura regenerada por pedido HTTP a outro serviço, e `thumbErro`

Quem tem Chromium para renderizar miniatura é o serviço que publica catálogos; o editor de peças
não tem. Depois de gravar uma geometria editada (`PUT`) ou de restaurar, o editor **pede** a
miniatura nova a esse outro serviço em vez de renderizar ele mesmo. Se esse serviço não responder
— estiver fora do ar, ou a URL dele estiver errada — a edição da geometria **não é desfeita**: o
produto grava `thumbErro` com o motivo, e a resposta ao cliente diz que a miniatura não foi
solicitada. A miniatura antiga continua servindo até a próxima tentativa bem-sucedida. É uma
degradação deliberada: a falha de um serviço auxiliar não pode bloquear uma escrita que já foi
persistida com sucesso.

Uma consequência sutil: se a edição não muda a **forma projetada** da peça (por exemplo, uma
escala uniforme), a miniatura regenerada pode sair pixel a pixel idêntica à anterior — a câmera
enquadra pelo bounding box, então uma peça maior ou menor na mesma proporção projeta a mesma
silhueta. Não é o worker falhando; é o enquadramento fazendo o que deveria.

## Fila em memória + recuperação no boot pressupõem uma instância

As importações passam por uma fila FIFO **em processo** (concorrência configurável, padrão 1):
duas importações simultâneas disputariam o mesmo Chromium e a mesma CPU sem que nada avisasse o
usuário que ele estava esperando. A fila é só em memória — morre com o processo — e por isso o
que estava em `recebido`/`parseando`/`gravando` quando o serviço cai é tratado no **boot**: todo
import não terminal é considerado órfão e vira `falhou` com uma mensagem pedindo para reenviar o
arquivo, e os uploads temporários que o multer deixou em disco são varridos pelo mesmo padrão de
nome que os gerou.

Essa recuperação assume **uma única instância** rodando contra a base: com mais de um processo,
"não terminal" deixa de significar "órfão" (pode estar em andamento em outra instância), e a
recuperação passaria a precisar de lease/heartbeat (idade mínima do `updatedAt` antes de marcar
como falho) em vez de "tudo que não é terminal, morreu".

## `IGeometryStore` como costura para S3

Toda geometria, miniatura e logo entra e sai do storage por uma interface pequena — `put`, `get`,
`stat` (metadados sem ler os bytes, para montar ETag e responder 304 sem tocar no arquivo),
`delete`, `deleteByPrefix`. A implementação de disco da POC e uma implementação em S3 são a mesma
interface do ponto de vista de quem grava e lê; nenhum outro código sabe se o backend é um
filesystem local ou um bucket.

## Quem grava o quê

| Coleção / prefixo | Grava | Lê |
|---|---|---|
| import | quem publica catálogos (ciclo de estados acima) | quem publica, quem lista importações |
| catálogo | quem publica (upsert, recontagem de `productCount`/filtros), a API de leitura (metadados, remoção), o editor (recontagem ao editar série) | todos |
| produto | quem publica (`insertMany`, `thumbKey`), o editor (`specs`, `infoOriginal`, `geoKey`, `geoKeyCompartilhada`, `geoEditadoEm`, `thumbErro`), a API de leitura (remoção) | todos |
| `geo/<importId>/…` | o pipeline via quem publica; o editor (copy-on-write, `.orig.json`) | leitura, publicação (miniaturas), edição |
| `thumbs/<importId>/…` | quem publica (import e regeneração) | leitura |

## `infoOriginal`

Um snapshot dos campos editáveis do produto (nome, série, dados técnicos) exatamente como vieram
do import, gravado na primeira edição — não a cada edição. É o material para "descartar as
edições e voltar ao que a origem tinha" sem reabrir o arquivo de origem, no mesmo espírito do
`.orig.json` da geometria.

## Onde está no código

- `pacotes/dominio/src/schemas/bim-imports.schema.ts` — os estados, `thumbCount`/`thumbFailed`/
  `thumbError`, `diag`.
- `pacotes/dominio/src/schemas/bim-products.schema.ts` — `geoKey`, `thumbKey`,
  `geoKeyCompartilhada`, `geoEditadoEm`, `thumbAtualizadaEm`, `thumbErro`, `infoOriginal`.
- `pacotes/dominio/src/geometry-store/geometry-store.interface.ts` — `IGeometryStore`.
- `pacotes/dominio/src/remocao.ts` — `apagarProduto`/`apagarCatalogo`/`apagarEmpresa`, a checagem
  de "último usuário" antes de apagar um arquivo compartilhado.
- `servicos/criador-de-catalogos/src/publicacao/publicacao.service.ts` — a máquina de estados do
  import, upsert por slug, disparo das miniaturas.
- `servicos/criador-de-catalogos/src/importacoes/fila.ts` — a fila FIFO em memória.
- `servicos/criador-de-catalogos/src/importacoes/recuperacao.service.ts` — a recuperação no boot.
- `servicos/editor-de-pecas/src/geometrias-edicao.controller.ts` — copy-on-write, restaurar,
  pedido de miniatura ao outro serviço.

## Ver também

- `docs/conhecimento/miniaturas.md` — como a miniatura é gerada e por que uma falha vira
  `thumbErro` em vez de erro de escrita.
- `docs/conhecimento/processos-filhos.md` — como o pipeline Python e o `thumbs.mjs` são chamados
  a partir do serviço que publica catálogos.
- `docs/decisoes/ADR-005-copy-on-write-na-geometria-compartilhada.md`,
  `docs/decisoes/ADR-006-miniatura-por-geometria-regerada-pelo-criador.md`.
