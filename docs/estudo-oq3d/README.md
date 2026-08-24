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
| `massval.py` | validação em massa `.aq` × IFC — bounding box e contagem peça a peça |

O parser que saiu do estudo virou `scripts/oq3d.py`, em produção. O que está aqui é ferramenta de investigação, mantida para reproduzir a análise ou atacar o bug em aberto.

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

## Bug em aberto

Instâncias `TQi3DReusedObject` sem definição inline não emitem geometria — os GUIDs são únicos por instância e a chave de resolução não foi identificada. Na CAM-W21 2CV: 5 instâncias com malha, 13 sem. Efeito visível: parafusos faltando e um solto no ar.

Detalhes e hipóteses em `CLAUDE.md`, seção "Conhecimento crítico: oq3d.py".
