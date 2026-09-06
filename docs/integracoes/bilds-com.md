# Integração com a bilds.com — upload, erros, upsert, URL pública

Este é o único documento do repositório que descreve o lado **consumidor** do pacote ZIP
(`docs/conhecimento/zip-bilds-formato.md`): a plataforma bilds.com, para onde o ZIP gerado por
este pipeline é enviado. A plataforma não é um fabricante — é o produto que exibe os catálogos —
então nomeá-la aqui não conflita com a regra de não citar fabricante em `docs/conhecimento/`.

## Endpoint de upload

```
POST /companies/{companyId}/b-bim-3d
Content-Type: multipart/form-data

Campo:  zip    ← arquivo .zip (o formato descrito em zip-bilds-formato.md)
Campo:  layout ← (opcional) "series-rows" | "catalog-grid"
                  sobrescreve o layout do manifest.json quando fornecido
```

- Apenas o criador ou administrador da empresa de destino pode fazer upload.
- O campo `layout` do formulário tem **precedência** sobre o `layout` do `manifest.json`.
- Tamanho máximo do arquivo comprimido: 100 MB; descomprimido, 500 MB; até 10.000 entradas; cada
  `geo/<nome>.json` até 10 MB.

## Erros retornados pelo servidor

| Código | Causa |
|---|---|
| 400 | ZIP inválido, excede limites, sem `manifest.json`/`catalog.json`, JSON malformado |
| 400 | `manifest.json` sem `slug`/`title`, ou `slug`/`layout` fora do formato aceito |
| 400 | empresa de destino sem identificador público configurado |
| 400 | `geo/<nome>.json` acima de 10 MB, ou o campo enviado não é um `.zip` |
| 403 | usuário sem permissão de criador/administrador na empresa |
| 404 | empresa não encontrada |
| 413 | ZIP comprimido acima do limite (rejeitado antes de chegar ao parser) |
| 500 | falha ao gravar no storage ou ao persistir no banco (o storage já gravado é revertido) |

## Upsert por slug

Um upload cujo `manifest.slug` já existe para a empresa **substitui** o catálogo existente, não
cria um segundo:

1. Os arquivos antigos (`geo/`, `thumbs/`) são substituídos no storage — o conteúdo do prefixo
   anterior é apagado e o novo é gravado no lugar.
2. O registro no banco é atualizado via upsert, mantendo o mesmo identificador interno.
3. A data de publicação é atualizada para o momento do upload.
4. O `layout` gravado segue a precedência: campo do formulário > `manifest.json` > padrão
   (`series-rows`).

Reenviar o mesmo pacote (mesmo `slug`) é, portanto, a forma correta de corrigir ou atualizar um
catálogo já publicado — não é preciso apagar antes.

## URL pública resultante

Depois de um upload bem-sucedido, o catálogo fica disponível em:

```
https://bilds.com/{customLink}/{slug}
```

onde `{customLink}` é o identificador público da empresa de destino na plataforma, e `{slug}` é o
mesmo `slug` do `manifest.json`/`catalog.json` enviados. O `layout` pode ser trocado depois, sem
reenviar o ZIP, editando o catálogo pelo painel administrativo da plataforma.

## Onde está no código

O servidor deste endpoint não vive neste repositório — é a plataforma bilds.com. Neste
repositório, o lado que produz o pacote consumido por ele é:

- `biblioteca/bim_pipeline/cli/zip_bilds.py` — gera o ZIP no formato descrito em
  `docs/conhecimento/zip-bilds-formato.md`.
- `servicos/gerador-zip/` — o serviço stateless que expõe essa geração por HTTP para quem for
  automatizar o envio.

## Ver também

- `docs/conhecimento/zip-bilds-formato.md` — o formato do pacote que este endpoint recebe.
- `docs/conhecimento/miniaturas.md` — por que enviar `thumbs/` junto muda o desempenho de
  carregamento da página pública.
