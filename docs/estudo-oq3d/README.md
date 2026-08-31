# Estudo OQ3D — a geometria dentro do .aq

Investigação que decodificou o formato binário **OQ3D**, a malha 3D que o AltoQi Builder guarda dentro do `.aq`, e a validou contra os IFCs das mesmas bibliotecas. É a origem do caminho padrão atual do pipeline: **os IFCs deixaram de ser necessários.**

Leia o relatório completo em [`estudo-oq3d.html`](estudo-oq3d.html) — abra no navegador.

## Conclusão

Forma, cor e miniatura estão todas no `.aq`, e é a mesma geometria que alimenta o IFC. Onde o IFC é tessellated, os triângulos batem **exatamente**; onde é B-rep, a forma converge a 0,3 mm com tesselação independente.

Validado em nove bibliotecas, seis versões de schema (552–607) e três domínios — hidráulica, bombas e elétrica/telecom.

## Arquivos aqui

| Arquivo | O que é |
|---|---|
| `estudo-oq3d.html` | relatório completo, com renders e tabelas de validação |
| `render.py` | rasterizador z-buffer em numpy puro, usado para conferir a geometria visualmente sem depender de browser |
| `massval.py` | validação em massa `.aq` × IFC — bounding box e contagem peça a peça (usa o nome antigo `oq3dtree`) |
| `valida_ifc.py` | confere o parser contra o IFC peça a peça: **conjunto de pontos** em biblioteca tessellated, forma em B-rep |

O parser que saiu do estudo virou `scripts/oq3d.py`, em produção. O que está aqui é ferramenta de investigação, mantida para reproduzir a análise e conferir o parser contra os IFCs.

## Reproduzir

```bash
# render de uma peça, sem browser
python3 -c "
import sys, sqlite3; sys.path.insert(0,'scripts'); sys.path.insert(0,'docs/estudo-oq3d')
import oq3d, render, numpy as np
from PIL import Image
con = sqlite3.connect('file:input/Dancor/pecas.aq?mode=ro', uri=True)
con.text_factory = lambda b: b.decode('latin-1')
b = con.execute('SELECT SIMBOLOGIA_3D FROM SIMBOLOGIA_3D WHERE ID_SIMBOLOGIA_3D=1').fetchone()[0]
ms = oq3d.extract(b)
T = np.concatenate([v[t] for v,t,_ in ms])
C = np.concatenate([np.tile(np.array(c[:3],float),(len(t),1)) for v,t,c in ms])
Image.fromarray(render.render(T, C, size=420, elev=22, azim=48)).save('/tmp/peca.png')
"

# validação em massa contra os IFCs (precisa de ifcopenshell)
python3 docs/estudo-oq3d/massval.py
```

## Bug resolvido em 2026-08-30

Os parafusos que faltavam na CAM-W21 2CV (5 instâncias com malha, 13 sem) eram **dois** bugs:

1. **Instâncias repetidas.** `TQi3DReusedObject` sem definição inline referencia uma `TQi3DReusableObject` pelo **índice de serialização, base 1, sobre todos os objetos em ordem de documento** — não pelo GUID, que é único por instância. Um discriminador logo após o GUID (`0x01` = referência, `0x02` = inline) diz qual é o caso.
2. **Rotação transposta.** A 3×3 de `TCoordinateTransformation3D` é **column-major**; era lida como row-major. Não muda a contagem de triângulos, só a posição — era este o responsável pela peça "solta no ar".

Conferido contra o IFC: as 13 peças da Dancor batem **ponto a ponto**.

```bash
python3 docs/estudo-oq3d/valida_ifc.py Dancor
```

Detalhes em `CLAUDE.md`, seção "Conhecimento crítico: oq3d.py".
