# 2026-09-02 — POC subida local, armadilha do Atlas e limpeza da base

**Data:** 2026-09-02 · Registro **extraído do `CLAUDE.md`** em 2026-09-04 (S7.8, I22) — esta
sessão não tinha arquivo próprio; o texto abaixo é o que havia lá, sem alteração.

---

Sessão sem mudança de código: subir a POC nesta máquina, documentar o que barrou, e
**zerar banco e storage** a pedido.

**A POC subiu, depois de um bloqueio de 15 minutos no Atlas.** O web (`:3000`) levantou
normal; a API (`:4000`) ficou em retry infinito com o Mongoose acusando whitelist de IP. A
mensagem é texto fixo do driver e cobre cinco causas distintas, então medi as camadas
separadamente: DNS SRV resolvia os três nós, o TCP em `:27017` **conectava**, e o TLS
morria com `tlsv1 alert internal error` (SSL alert 80) nos três. Essa combinação — TCP
abrindo, TLS caindo com alert 80 — é a assinatura de IP não liberado: o handshake termina
antes de qualquer credencial trafegar. Liberado o IP no Atlas, a API **reconectou sozinha**
no ciclo de retry seguinte, sem reinício. Receita completa em "A API não sobe e o Mongoose
culpa o whitelist"; três linhas novas na tabela de diagnóstico.

**Validação da carga que existia, antes de apagar.** Confirmou a S5.2 integralmente: 869
produtos, todos com `geoUrl` e `thumbUrl`; geometria da CAM-W21 2CV com **27.425
triângulos** (o número do parser corrigido, não os 20.452 do antigo); miniaturas em
`image/webp` distintas por produto; revalidação da S6.1 devolvendo `304` com a ETag; as
duas páginas públicas em `200` e slug inexistente em `404`.

**Limpeza.** `deleteMany({})` nas quatro coleções — `bim_products` (869), `bim_catalogs`
(2), `bim_imports` (2) e `companies` (1) — e todos os 1.738 arquivos de
`www/storage/bim/`, preservando os diretórios. Conferido depois: 0 documentos, 0 arquivos,
e a API respondendo certo no vazio (`404` nas páginas e em `/empresas/minha`, `200` com
corpo vazio em `/importacoes/ultima`, login seguindo em `200` porque não consulta o banco).

> **A limpeza é irreversível nesta máquina.** Os `.aq` da Dancor e da Amanco não estão em
> `input/`, e as chaves de storage embutem o `importId` — nada do que foi apagado se
> reconstitui a partir do que sobrou. Quem quiser exercitar a POC aqui deve importar uma
> das 7 bibliotecas da Intelbras, que são pequenas e atravessam o mesmo caminho.

**Duas coisas que o arquivo afirmava e não eram mais verdade** — ambas corrigidas: os
`importId` documentados (`d5a4acb5`, `28826de9`) já não existiam desde antes desta sessão
(eram `4180e887` e `5c2dc29a`, e agora nenhum), e a coleção de empresa chama-se
`companies`, não `bim_companies`. Ficou registrado também o formato da resposta de
`GET /catalogos/:empresa/:slug`: raiz `{ catalog, products }` em inglês, com
`geoUrl`/`thumbUrl` no produto — diferente do `catalog.json` do pipeline estático e dos
`geoKey`/`thumbKey` do documento do Mongo.
