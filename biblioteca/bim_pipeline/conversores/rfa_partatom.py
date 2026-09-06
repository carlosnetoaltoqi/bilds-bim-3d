#!/usr/bin/env python3
"""
rfa_partatom.py — o que dá para tirar de uma família Revit (`.rfa`) SEM o Revit.

O `.rfa` é um documento OLE2 (a mesma casca do .doc antigo). A geometria fica em
`Partitions/<n>`, num formato binário proprietário da Autodesk que ninguém fora do Revit lê —
por isso a geometria 3D das peças vem do IGES, não daqui. Quem usa: `plugin_catalogo_web.py` (spec
"Tipos Revit" de cada peça) e `docs/conhecimento/plugin-cad-catalogo-web.md`. O que É legível:

    PartAtom          XML Atom (`urn:schemas-autodesk-com:partatom`) com o título da família, a
                      categoria Revit ("Conexões de tubo"), o OmniClass (23.60.30.11.14 Pipework
                      Fittings), os parâmetros da família e UMA ENTRADA POR TIPO (`A:part`) — os
                      tamanhos (DN32, DN40, …) com Descrição, Modelo, Fabricante e URL. É a tabela
                      de variações da família, útil como especificação da peça no catálogo.
    BasicFileInfo     UTF-16 com a versão do Revit que gravou e o caminho original do arquivo. Até o
                      2019 é texto corrido ("Autodesk Revit 2017 (Build: …)"); do 2020 em diante é um
                      registro binário com campos UTF-16 de comprimento prefixado ("2021",
                      "20220517_1515(x64)", caminho) seguido do bloco de texto "Format: 2021 /
                      Build: … / Last Save Path: … / Locale when saved: ENU". O bloco de texto pode
                      começar em offset ímpar — decodificamos nos dois alinhamentos.
    RevitPreview4.0   PNG de pré-visualização (pequeno). Nem toda família tem (as baseadas em linha
                      costumam vir sem).

O que NÃO se lê: a geometria (`Partitions/<n>`, gzip de um binário proprietário) e, num `.rvt`
(projeto), as famílias embutidas — o projeto não tem `PartAtom`. Ver `docs/conhecimento/revit-familias.md`.

Saída: um JSON ao lado do `.rfa` (`<nome>.partatom.json`) e o PNG (`<nome>.preview.png`),
ou no diretório de `--saida`. Requer `olefile` (`pip install --user --break-system-packages olefile`).

Uso:
    python3 -m bim_pipeline.cli.rfa_partatom familia.rfa [outra.rfa …] [--saida DIR]
"""
import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

try:
    import olefile
    HAS_OLEFILE = True
except ImportError:  # pragma: no cover
    HAS_OLEFILE = False

NS = {'a': 'http://www.w3.org/2005/Atom', 'A': 'urn:schemas-autodesk-com:partatom'}


def _texto_utf16(b):
    if b[:2] == b'\xff\xfe':
        b = b[2:]
    return b.decode('utf-16-le', errors='ignore')


def _texto_utf16_ambos(b):
    """Os dois alinhamentos possíveis de um bloco UTF-16LE cujo início não se conhece (BasicFileInfo 2020+)."""
    return _texto_utf16(b) + '\n' + _texto_utf16(b[1:])


def info_basica(texto):
    """
    `{revit, formato, build, caminho_original, locale}` do texto do `BasicFileInfo` (já decodificado,
    nos dois alinhamentos). `revit` é o rótulo legível ("Autodesk Revit 2021 (Build: 20220517_1515(x64))"),
    `formato` o ano do formato (int) — o que decide compatibilidade de abertura no Revit.
    """
    out = {'revit': None, 'formato': None, 'build': None, 'caminho_original': None, 'locale': None}
    m = re.search(r'Autodesk Revit(?: [A-Za-z]+)? (\d{4})(?: \(Build: ([^)]*)\))?', texto)
    if m:
        out['formato'] = int(m.group(1))
        out['build'] = m.group(2)
    m = re.search(r'Format:\s*(\d{4})', texto)
    if m:
        out['formato'] = int(m.group(1))
    m = re.search(r'Build:\s*([0-9]{8}_[0-9]{4}(?:\([^)]*\))?)', texto)
    if m:
        out['build'] = m.group(1)
    if out['formato']:
        out['revit'] = f"Autodesk Revit {out['formato']}" + (f" (Build: {out['build']})" if out['build'] else '')
    m = re.search(r'Last Save Path:\s*(.+?)\s*(?:\r|\n|Open Workset)', texto)
    if m:
        out['caminho_original'] = m.group(1).strip()
    m = re.search(r'Locale when saved:\s*([A-Z]{3})', texto)
    if m:
        out['locale'] = m.group(1)
    return out


def _limpo(tag):
    return tag.split('}', 1)[1] if '}' in tag else tag


_NAO_PARAMETRO = ('title', 'id', 'updated', 'link', 'category', 'taxonomy', 'features', 'family', 'group')


def _parametros(el):
    """Elementos-filho arbitrários (`<Fabricante type=…>FABRICANTE S.A.</Fabricante>`) → {nome: valor}."""
    return {k: v['valor'] for k, v in _parametros_detalhados(el).items()}


def _parametros_detalhados(el):
    """
    O mesmo, com o `typeOfParameter` do Revit ("Length", "Section Property", "Text", "Material", "Yes/No"…)
    e a origem (`type="system"` = parâmetro embutido do Revit, `"custom"` = da família):
    {nome: {valor, tipo, origem}}. O nome é o `displayName` quando existe (o tag XML troca espaço e
    pontuação por `_`).
    """
    out = {}
    for ch in el:
        nome = _limpo(ch.tag)
        if nome in _NAO_PARAMETRO:
            continue
        out[ch.get('displayName') or nome.replace('_', ' ')] = {
            'valor': (ch.text or '').strip(), 'tipo': ch.get('typeOfParameter'), 'origem': ch.get('type'),
        }
    return out


def ler(caminho):
    if not HAS_OLEFILE:
        raise SystemExit('olefile não instalado — pip install --user --break-system-packages olefile')
    o = olefile.OleFileIO(caminho)
    out = {'arquivo': os.path.basename(caminho), 'bytes': os.path.getsize(caminho), 'streams': {}}
    for e in o.listdir(streams=True, storages=False):
        p = '/'.join(e)
        out['streams'][p] = o.get_size(p)

    if o.exists('BasicFileInfo'):
        out.update(info_basica(_texto_utf16_ambos(o.openstream('BasicFileInfo').read())))

    if o.exists('PartAtom'):
        raw = o.openstream('PartAtom').read()
        xml = _texto_utf16(raw) if raw[:2] == b'\xff\xfe' or raw[1:2] == b'\x00' else raw.decode('utf-8', 'ignore')
        root = ET.fromstring(xml.strip())
        pa = {'titulo': (root.findtext('a:title', namespaces=NS) or '').strip(),
              'atualizado': root.findtext('a:updated', namespaces=NS),
              'categorias': [{'termo': c.findtext('a:term', namespaces=NS), 'esquema': c.findtext('a:scheme', namespaces=NS)}
                             for c in root.findall('a:category', NS)],
              'parametros_familia': {}, 'tipos': [], 'tipos_detalhados': []}
        for grupo in root.findall('.//A:features/A:feature/A:group', NS):
            gtit = (grupo.findtext('a:title', namespaces=NS) or '').strip()
            params = _parametros(grupo)
            if params:
                pa['parametros_familia'][gtit] = params
        fam = root.find('A:family', NS)
        if fam is not None:
            pa['variacoes'] = int(fam.findtext('A:variationCount', namespaces=NS) or 0)
            for part in fam.findall('A:part', NS):
                titulo = (part.findtext('a:title', namespaces=NS) or '').strip()
                pa['tipos'].append({'titulo': titulo, **_parametros(part)})
                pa['tipos_detalhados'].append({'titulo': titulo, 'parametros': _parametros_detalhados(part)})
        out['partatom'] = pa

    png = None
    if o.exists('RevitPreview4.0'):
        b = o.openstream('RevitPreview4.0').read()
        i = b.find(b'\x89PNG')
        if i >= 0:
            png = b[i:]
    o.close()
    return out, png


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('rfa', nargs='+')
    ap.add_argument('--saida', help='diretório de saída (padrão: ao lado de cada .rfa)')
    ap.add_argument('--quiet', action='store_true')
    args = ap.parse_args()
    for caminho in args.rfa:
        info, png = ler(caminho)
        base = os.path.splitext(os.path.basename(caminho))[0]
        pasta = args.saida or os.path.dirname(os.path.abspath(caminho))
        os.makedirs(pasta, exist_ok=True)
        with open(os.path.join(pasta, base + '.partatom.json'), 'w', encoding='utf-8') as f:
            json.dump(info, f, ensure_ascii=False, indent=1)
        if png:
            with open(os.path.join(pasta, base + '.preview.png'), 'wb') as f:
                f.write(png)
        if not args.quiet:
            pa = info.get('partatom') or {}
            tipos = ', '.join(t['titulo'].rsplit(' - ', 1)[-1] for t in pa.get('tipos', []))
            print(f"{info['arquivo']}: {info.get('revit') or '?'} · {pa.get('titulo') or '?'} · "
                  f"{pa.get('variacoes', 0)} tipo(s): {tipos}" + (' · preview PNG' if png else ''), file=sys.stderr)


if __name__ == '__main__':
    main()
