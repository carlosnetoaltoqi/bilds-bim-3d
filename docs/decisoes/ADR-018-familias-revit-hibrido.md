# ADR-018 — famílias Revit: metadados do .rfa, geometria irmã ou forma representativa

**Status:** Aceita (2026-09-06)

## Decisão

O importador de famílias Revit (`catalogo/fontes/familias_revit.py`) lê de cada `.rfa` só o que é
legível fora do Revit — `PartAtom` (tipos e parâmetros), `BasicFileInfo` (versão), type catalog `.txt`
— e obtém a geometria de forma **híbrida e offline**: de um arquivo irmão IFC/STEP/IGES de mesmo nome
quando existe (geometria real, compartilhada pelos tipos da família); senão, uma **forma representativa**
gerada dos parâmetros do tipo (`geometria/perfis.py`), com a ressalva gravada na série e na spec
"Geometria 3D". Tipo sem cota reconhecível fica fora. `.rvt` é recusado. Nenhum serviço externo.

## Por quê

A geometria de um `.rfa` está num binário proprietário sem especificação pública; nenhum leitor aberto
a decodifica (verificado: o mais avançado emite um IFC sem sólidos para uma família real) e o Revit não
exporta família para IFC sem projeto. As alternativas eram a nuvem da Autodesk (APS Model Derivative:
conta, credenciais, custo por job, rede — quebra o pipeline offline e stateless, ADR-011) ou não ter
geometria (sem geometria não há peça no `.aq`, `aq-escrita.md`). Fabricantes de perfis, tubos e telhas
cotam a seção nos parâmetros do tipo, então a forma representativa é, nesses casos, a seção exata
extrudada — e `formas-representativas.md` já fixava como marcar o que é aproximado.

## Consequências

- Um `.zip` de fabricante com dezenas de `.rfa` e type catalogs vira um catálogo com milhares de
  produtos em segundos, exportável para `.aq` pelo caminho existente (`catalogo_para_aq`), com todo
  texto garantido em cp1252 (`cp1252_seguro`).
- A geometria de famílias sem cota de seção (equipamentos com só largura e altura, por exemplo) é uma
  caixa com profundidade inventada — a spec diz isso; a geometria fiel exige o arquivo irmão.
- Nova dependência da biblioteca: `olefile` (puro Python) passa de opcional a obrigatória.
- Fica registrado, para quando fizer sentido, o caminho APS como alternativa de geometria fiel.
