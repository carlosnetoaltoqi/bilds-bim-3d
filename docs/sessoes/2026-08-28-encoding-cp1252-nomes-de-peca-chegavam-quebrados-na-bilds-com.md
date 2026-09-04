# 2026-08-28 — Encoding cp1252: nomes de peça chegavam quebrados na bilds.com

**Data:** 2026-08-28 · Registro **extraído do `CLAUDE.md`** em 2026-09-04 (S7.8, I22) — esta
sessão não tinha arquivo próprio; o texto abaixo é o que havia lá, sem alteração.

---

**Achado durante a verificação do BILDS-552.** Com a página do catálogo finalmente
carregando rápido, deu para ler os nomes — e eles estavam errados:
`5U \x96 19\x94 x 570mm MRD 557` em vez de `5U – 19” x 570mm MRD 557`.

**A causa estava escrita no próprio docstring:** _"Encoding: latin-1 (Windows-1252)"_.
Os dois não são a mesma coisa. Diferem só na faixa 0x80–0x9F, que é justamente onde estão
os caracteres tipográficos que aparecem em nome de produto. A confusão vinha desde o
primeiro commit do `read_aq.py`, e nunca deu erro — latin-1 decodifica qualquer byte.

**Escopo real:** 2 das 9 bibliotecas têm caracteres nessa faixa, mas o defeito era
visível em produção para qualquer catálogo com travessão ou aspas no nome.

**O que quase deu errado no conserto.** Trocar o `text_factory` direto para cp1252 teria
corrompido a geometria: o latin-1 era byte-preserving e o código reconstruía o BLOB com
`.encode('latin-1')` quando a coluna voltava como `str`. Com cp1252 esse caminho não é
reversível. Resolvido com `CAST(... AS BLOB)` nas queries de `SIMBOLOGIA_3D`, que força
bytes e dispensa o re-encode.

**Verificação:** hash SHA-256 de todos os blobs de geometria e imagem, antes e depois —
idêntico em Dancor e Intelbras CFTV. E zero bytes de controle nos nomes das 9
bibliotecas (1.441 peças).

**Regra que fica:** ao mexer em decodificação, medir o binário antes e depois. Texto
errado é visível; binário corrompido não é.
