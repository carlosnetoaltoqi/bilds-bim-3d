#!/usr/bin/env python3
"""
ifc_elementos.py — um IFC de PROJETO → seus elementos, um a um, com geometria local e identidade.

`conversores/ifc.py` devolve o arquivo inteiro como UMA geometria (é o que o viewer de uma peça quer).
Um projeto exportado do Revit é o contrário: dezenas de instâncias de famílias colocadas pelo modelo, e o
que vira produto de catálogo é o **tipo** ("Família:Tipo"), não a instância. Este módulo entrega, por
elemento com representação:

    {'id', 'guid', 'nome', 'classe' (IfcFlowStorageDevice…), 'familia', 'tipo', 'tipo_ifc' (IfcTypeObject.Name),
     'psets': {conjunto: {prop: valor}}, 'verts' (N×3, metros, LOCAL ao elemento, Z-up), 'faces' (M×3), 'cores' (M×3 em 0–1)}

Geometria LOCAL (sem `USE_WORLD_COORDS`): a malha fica na origem que a família define, então duas instâncias
do mesmo tipo em lugares diferentes dão a mesma malha — e o catálogo guarda uma só. "Família:Tipo" é como o
exportador IFC do Revit preenche `Name` e `ObjectType` da instância; quando não há dois-pontos, a família é
o `Name` do `IfcTypeObject` (ou o `Name` inteiro) e o tipo é o resto. Exige `ifcopenshell` (`[cad]`).
"""
import multiprocessing
import os

from bim_pipeline.geometria.eixos import zup_para_viewer_np

COR_PADRAO = (0.533, 0.588, 0.667)


def _rgb(material):
    from bim_pipeline.conversores.ifc import _rgb_do_material
    return _rgb_do_material(material)


# Propriedades de INSTÂNCIA (posição no modelo, fase, marca) que não dizem nada sobre o produto de catálogo
_PROPS_DE_INSTANCIA = {
    'mark', 'design option', 'host', 'level', 'reference level', 'offset', 'elevation', 'offset from host', 'schedule level',
    'moves with nearby elements', 'phase created', 'phase demolished', 'type id', 'family and type', 'family', 'type',
    'loss method', 'workset', 'edited by', 'comments', 'image', 'system classification', 'system name', 'system type',
    'flow', 'pressure drop', 'additional flow', 'area', 'volume', 'insulation thickness', 'insulation type', 'lining thickness',
}


def familia_e_tipo(nome, object_type=None, tipo_ifc=None, psets=None):
    """
    ("Família", "Tipo") de um elemento exportado do Revit. Prioridade: os psets "Family Name"/"Type Name"
    (Identity Data, quando o exportador inclui as propriedades do Revit); senão `Name`/`ObjectType`
    "Família:Tipo" — o exportador da Autodesk acrescenta ":IdDoElemento" ao `Name`, que é descartado;
    senão o `IfcTypeObject.Name` como tipo.
    """
    ps = psets or {}
    fam_ps = tipo_ps = None
    for props in ps.values():
        fam_ps = fam_ps or props.get('Family Name')
        tipo_ps = tipo_ps or props.get('Type Name')
    if fam_ps and tipo_ps:
        return str(fam_ps).strip(), str(tipo_ps).strip()
    for candidato in (object_type, nome):
        if candidato and ':' in candidato:
            partes = [p.strip() for p in candidato.split(':')]
            if len(partes) > 2 and partes[-1].isdigit():
                partes = partes[:-1]
            fam, tipo = ':'.join(partes[:-1]), partes[-1]
            if tipo_ifc and tipo_ifc.strip() and tipo_ifc.strip() != tipo and ':'.join(partes).endswith(tipo_ifc.strip()):
                tipo = tipo_ifc.strip()
            return (fam or tipo_ifc or candidato).strip(), (tipo or tipo_ifc or '').strip()
    base = (nome or object_type or tipo_ifc or '').strip()
    if tipo_ifc and tipo_ifc.strip() and tipo_ifc.strip() != base:
        return base, tipo_ifc.strip()
    return base, base


def elementos(caminho, progresso=None):
    """Itera os elementos com geometria (ver docstring do módulo). Lança `ImportError` sem ifcopenshell."""
    import numpy as np
    import ifcopenshell
    import ifcopenshell.geom
    import ifcopenshell.util.element as ue

    f = ifcopenshell.open(caminho)
    s = ifcopenshell.geom.settings()
    it = ifcopenshell.geom.iterator(s, f, multiprocessing.cpu_count())
    if not it.initialize():
        return
    n = 0
    while True:
        sh = it.get()
        g = sh.geometry
        faces = np.asarray(g.faces, dtype=np.int64).reshape(-1, 3)
        if len(faces):
            verts = np.asarray(g.verts, dtype=np.float64).reshape(-1, 3)
            mats = list(getattr(g, 'materials', []))
            mids = np.asarray(getattr(g, 'material_ids', []), dtype=np.int64)
            cores = np.tile(np.asarray(COR_PADRAO, dtype=np.float64), (len(faces), 1))
            if mats and len(mids) == len(faces):
                paleta = np.asarray([_rgb(m) for m in mats], dtype=np.float64)
                ok = (mids >= 0) & (mids < len(paleta))
                cores[ok] = paleta[mids[ok]]
            el = f.by_id(sh.id)
            tipo_obj = None
            try:
                tipo_obj = ue.get_type(el)
            except Exception:
                pass
            tipo_ifc = getattr(tipo_obj, 'Name', None) if tipo_obj is not None else None
            try:
                psets = {k: {p: v for p, v in props.items() if p != 'id'} for k, props in ue.get_psets(el).items()}
            except Exception:
                psets = {}
            fam, tipo = familia_e_tipo(getattr(el, 'Name', None), getattr(el, 'ObjectType', None), tipo_ifc, psets)
            n += 1
            if progresso and n % 200 == 0:
                progresso(f'    {n} elementos lidos')
            yield {'id': sh.id, 'guid': sh.guid, 'nome': getattr(el, 'Name', None) or sh.type, 'classe': sh.type,
                   'familia': fam, 'tipo': tipo, 'tipo_ifc': tipo_ifc, 'psets': psets,
                   'verts': verts, 'faces': faces, 'cores': cores}
        if not it.next():
            break


def geo_do_viewer(el):
    """Um elemento → `{pos, col, idx}` (metros, Y-up), cor por vértice = cor da face (vértices duplicados por cor)."""
    import numpy as np
    from bim_pipeline.geometria.dedup import dedup_arrays
    tri = el['verts'][el['faces']].reshape(-1, 3)
    col = np.repeat(el['cores'], 3, axis=0)
    pos_u, col_u, idx = dedup_arrays(zup_para_viewer_np(tri), col)
    return {'pos': np.round(pos_u, 7).ravel().tolist(), 'col': np.round(col_u, 4).ravel().tolist(), 'idx': idx.astype(int).tolist()}


def specs_de(el, max_len=400):
    """
    Os psets achatados em `{prop: valor}` de texto (o nome do conjunto só quando há colisão), mais a classe
    IFC. Ficam de fora as propriedades de instância (`_PROPS_DE_INSTANCIA`), valores vazios/"n/a" e GUIDs.
    """
    specs = {}
    vistos = {}
    for conjunto, props in (el.get('psets') or {}).items():
        for prop, valor in props.items():
            if valor is None or valor == '' or isinstance(valor, (dict, list, tuple)) or prop.lower() in _PROPS_DE_INSTANCIA:
                continue
            if isinstance(valor, bool):
                v = 'Sim' if valor else 'Não'
            elif isinstance(valor, float):
                v = f'{valor:.6g}'
            else:
                v = str(valor).strip()
            if not v or v.lower() in ('n/a', 'na', '-', 'none') or _eh_guid(v):
                continue
            chave = prop if prop not in vistos or vistos[prop] == v else f'{conjunto} · {prop}'
            vistos.setdefault(prop, v)
            specs[chave] = v[:max_len]
    specs['Classe IFC'] = el['classe']
    if el.get('tipo_ifc'):
        specs['Tipo IFC'] = str(el['tipo_ifc'])[:max_len]
    return specs


def _eh_guid(v):
    import re
    return bool(re.fullmatch(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}', v))


def por_tipo(elementos_iter):
    """Agrupa por (família, tipo): `{(familia, tipo): {'primeiro': el, 'instancias': n}}`, na ordem de aparição."""
    grupos = {}
    for el in elementos_iter:
        chave = (el['familia'], el['tipo'])
        g = grupos.get(chave)
        if g is None:
            grupos[chave] = {'primeiro': el, 'instancias': 1}
        else:
            g['instancias'] += 1
    return grupos


def nome_curto(caminho):
    return os.path.splitext(os.path.basename(caminho))[0]
