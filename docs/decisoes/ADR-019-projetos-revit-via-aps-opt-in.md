# ADR-019 — projetos Revit (.rvt) entram por IFC: irmão ou traduzido pela APS, opt-in

**Status:** Aceita (2026-09-06)

## Decisão

Um projeto Revit `.rvt` é entrada válida do importador de famílias Revit, mas só pelo seu IFC: o arquivo irmão
de mesmo nome quando existe, ou a tradução `.rvt → IFC` pela Autodesk Platform Services (Model Derivative,
`conversores/aps.py`) quando quem importa marca **"usar a APS"**. Do IFC, cada tipo de família colocado no
projeto vira um produto com a geometria real da primeira instância (`conversores/ifc_elementos.py`). As
credenciais ficam só no ambiente do criador de catálogos (`APS_CLIENT_ID`/`APS_CLIENT_SECRET`) e chegam à
biblioteca por um JSON temporário; o IFC traduzido fica em cache por SHA-256 do `.rvt` em `storage/aps/`.
Famílias `.rfa` **não** passam pela APS.

## Por quê

Fabricantes distribuem, além dos `.rfa`, modelos de amostra `.rvt` com as famílias colocadas — e um projeto não
tem `PartAtom`: fora do Revit não se lê nem tipo nem geometria. O Model Derivative aceita `.rvt` e exporta IFC
(verificado com um projeto real de fabricante: 17 MB, 157 s, IFC de 4,8 MB com 61 elementos), que a biblioteca
já lê; mas **não aceita `.rfa`** (a lista `GET designdata/formats` não o traz em nenhuma saída), então o caminho
serve a projetos e não substitui a forma representativa das famílias (ADR-018). Cada job custa tokens e envia o
arquivo à Autodesk, o que não pode acontecer sem quem importa saber — daí opt-in por importação, credenciais no
serviço e não no repositório, cache para não pagar duas vezes.

## Consequências

- A página `/importar/revit` mostra a opção de APS só quando o serviço tem credenciais (`GET
  /importacoes/familias-revit/aps`); um `.zip` só com projetos e sem a opção marcada é recusado na hora, com a
  explicação e a alternativa (o IFC irmão).
- Os produtos de um projeto trazem os psets do Revit como specs (Identity Data, dimensões, códigos do fabricante),
  filtradas as propriedades de instância; a série é o nome da família e "Instâncias no projeto" fica registrado.
- Dependência nova de rede na biblioteca, isolada em `conversores/aps.py` e só acionada com credenciais; o cliente
  HTTP é injetável e a suíte prova o fluxo contra um servidor falso, sem job.
- Quando alguém tiver o Revit, exportar o IFC do projeto e colocá-lo ao lado continua sendo o caminho gratuito.
