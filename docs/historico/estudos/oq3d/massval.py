#!/usr/bin/env python3
"""Validacao em massa Amanco: .aq (OQ3D) vs IFC (ADVANCEDBREP), peca a peca."""
import sys, os, re, json, glob, time, sqlite3, unicodedata
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, 'scripts')
import numpy as np
import oq3dtree
from parse_ifc import parse_ifc_file

ROOT = "input/Amanco/PVC Esgoto SN, SR e Silentium"
AQ = ROOT + "/pecas_Amanco_Esgoto_SN_SR_Silentium.aq"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "massval.json")


def norm(s):
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    s = s.lower().replace('º', '').replace('°', '')
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()


def toks(s):
    return set(norm(s).split())


# ── catálogo do .aq ───────────────────────────────────────────────────────
con = sqlite3.connect(f'file:{AQ}?mode=ro', uri=True)
con.text_factory = lambda b: b.decode('latin-1')
rows = con.execute("""
    SELECT s.ID_SIMBOLOGIA_3D, g.NOME_GRUPO, s.NOME, s.SIMBOLOGIA_3D
    FROM SIMBOLOGIA_3D s
    JOIN GRUPO_SIMBOLOGIA_3D g ON g.ID_GRUPO_SIMBOLOGIA_3D = s.ID_GRUPO_SIMBOLOGIA_3D
""").fetchall()

cat = []
t0 = time.time()
for sid, grupo, nome, blob in rows:
    b = blob if isinstance(blob, bytes) else blob.encode('latin-1')
    try:
        ms = oq3dtree.extract(b)
    except Exception as e:
        cat.append({'id': sid, 'grupo': grupo, 'nome': nome, 'erro': str(e)})
        continue
    if not ms:
        cat.append({'id': sid, 'grupo': grupo, 'nome': nome, 'erro': 'sem malha'})
        continue
    P = np.concatenate([v for v, _, _ in ms])
    ntri = sum(len(t) for _, t, _ in ms)
    bb = (P.max(0) - P.min(0))
    cores = sorted({c[:3] for _, _, c in ms})
    cat.append({'id': sid, 'grupo': grupo, 'nome': nome, 'ntri': ntri,
                'bbox': sorted(np.round(bb, 2).tolist()),   # ordenado: invariante a eixo
                'ncor': len(cores), 'cores': [list(c) for c in cores],
                'tk': sorted(toks(grupo) | toks(nome))})
t_aq = time.time() - t0
print(f"[aq] {len(cat)} pecas em {t_aq:.2f}s", flush=True)

# ── IFCs ──────────────────────────────────────────────────────────────────
ifcs = [f for f in glob.glob(ROOT + "/**/*.ifc", recursive=True)
        if ':Zone' not in f]
ifcs += [f for f in glob.glob(ROOT + "/**/*.IFC", recursive=True)
         if ':Zone' not in f]
ifcs = sorted(set(ifcs))
print(f"[ifc] {len(ifcs)} arquivos", flush=True)

res = []
t0 = time.time()
for k, f in enumerate(ifcs):
    rel = os.path.relpath(f, ROOT)
    try:
        d = parse_ifc_file(f)
    except Exception as e:
        res.append({'ifc': rel, 'erro': str(e)})
        continue
    pos = np.array(d['pos'], dtype=float).reshape(-1, 3) if d['pos'] else None
    if pos is None or not len(pos):
        res.append({'ifc': rel, 'erro': 'sem geometria'})
        continue
    ntri = len(d['idx']) // 3 if d.get('idx') else len(pos) // 3
    bb = pos.max(0) - pos.min(0)
    col = np.array(d['col']).reshape(-1, 3) if d.get('col') else np.zeros((0, 3))
    cores = {tuple(np.round(c, 2)) for c in col[::max(1, len(col) // 400 or 1)]}
    res.append({'ifc': rel, 'ntri': ntri,
                'bbox_m': sorted(np.round(bb, 4).tolist()),
                'bbox_cm': sorted(np.round(bb * 100, 2).tolist()),
                'ncor': len(cores),
                'tk': sorted(toks(rel.replace('.ifc', '').replace('.IFC', '')))})
    if (k + 1) % 50 == 0:
        print(f"  ...{k+1}/{len(ifcs)}  {time.time()-t0:.0f}s", flush=True)
t_ifc = time.time() - t0
print(f"[ifc] concluido em {t_ifc:.1f}s", flush=True)

json.dump({'aq': cat, 'ifc': res, 't_aq': t_aq, 't_ifc': t_ifc},
          open(OUT, 'w'), ensure_ascii=False)
print("gravado em", OUT, flush=True)
