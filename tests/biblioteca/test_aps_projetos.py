"""
Projetos Revit `.rvt` → catálogo via IFC (ADR-019): a APS Model Derivative simulada e o leitor de elementos.

O que se prova aqui, offline:
  * `ClienteAPS` contra um servidor FALSO (urlopen injetado): token com Basic e renovação, bucket já existente
    (409), upload S3 assinado em partes de 5 MB com conclusão, job ifc, polling do manifesto até `success`,
    derivado `.ifc` no manifesto, download por signed cookies (e o fallback direto); token recusado, job
    recusado e tradução `failed` viram `SystemExit` com a causa, sem o segredo na mensagem;
  * `rvt_para_ifc` reaproveita o cache por SHA-256 sem tocar na rede e grava no cache o que traduziu;
  * `ifc_elementos.familia_e_tipo`: "Família:Tipo:Id" do exportador da Autodesk, psets Family Name/Type Name,
    IfcTypeObject; `specs_de` deixa fora propriedades de instância, GUIDs e "n/a";
  * com `ifcopenshell`: um IFC sintético com duas instâncias do mesmo tipo e uma de outro → `elementos` dá
    geometria LOCAL (as duas instâncias, colocadas em lugares diferentes, têm a mesma malha), `por_tipo` agrupa,
    `geo_do_viewer` segue o contrato; `familias_revit` com um `.rvt` falso e o IFC irmão → um produto por tipo,
    specs dos psets, série = família, instâncias contadas; com um cliente APS falso, o mesmo pela rota 'aps';
    sem IFC e sem APS, o projeto fica fora com a explicação;
  * com a fixture `rvt_projeto` (e o IFC em cache), o caminho inteiro pela CLI sem gastar um job.
"""
import io
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(RAIZ, 'biblioteca'))
sys.path.insert(0, os.path.join(RAIZ, 'tests'))

from bim_pipeline import contratos                                     # noqa: E402
from bim_pipeline.catalogo.fontes import familias_revit as fr          # noqa: E402
from bim_pipeline.conversores import aps, ifc_elementos                # noqa: E402
from fixtures import FIXTURAS, caminho as fixture                      # noqa: E402

PROJETO_REAL = fixture('rvt_projeto')
HOST = aps.HOST


# ─── servidor APS falso ───────────────────────────────────────────────────────

class Resposta(io.BytesIO):
    def __init__(self, status, corpo=b'', headers=None):
        super().__init__(corpo if isinstance(corpo, bytes) else json.dumps(corpo).encode())
        self.status = status
        self.headers = _Headers(headers or {})

    def __enter__(self): return self
    def __exit__(self, *a): return False


class _Headers(dict):
    def get_all(self, nome):
        v = self.get(nome)
        return v if isinstance(v, list) else ([v] if v else [])


class ServidorFalso:
    """Responde ao fluxo inteiro e anota o que recebeu. `manifestos` é a sequência de estados devolvida ao polling."""

    def __init__(self, manifestos=None, token_ok=True, job_ok=True, cookies=True):
        self.chamadas = []
        self.manifestos = list(manifestos or [{'status': 'pending', 'progress': '0%'}, {'status': 'inprogress', 'progress': '50%'},
                                             {'status': 'success', 'progress': 'complete',
                                              'derivatives': [{'outputType': 'ifc', 'status': 'success',
                                                               'children': [{'role': 'ifc', 'urn': 'urn:adsk.viewing:fs.file:X/output/Resource/IFC/a.ifc'}]}]}])
        self.token_ok, self.job_ok, self.cookies = token_ok, job_ok, cookies
        self.tokens = 0
        self.partes = []
        self.ifc = b'ISO-10303-21;\nHEADER;ENDSEC;DATA;ENDSEC;END-ISO-10303-21;'

    def __call__(self, req, timeout=None):
        url, m = req.full_url, req.get_method()
        self.chamadas.append((m, url.split('?')[0]))
        auth = req.get_header('Authorization', '')
        if url.endswith('/authentication/v2/token'):
            assert auth.startswith('Basic ') and 'grant_type=client_credentials' in req.data.decode()
            self.tokens += 1
            if not self.token_ok:
                raise urllib.error.HTTPError(url, 401, 'x', _Headers(), io.BytesIO(b'{"developerMessage":"The client_id specified does not have access"}'))
            return Resposta(200, {'access_token': f'tok{self.tokens}', 'expires_in': 3599, 'token_type': 'Bearer'})
        if url.startswith(HOST):
            assert auth == f'Bearer tok{self.tokens}', auth        # a APS sempre com o token; S3 e CDN nunca (URLs assinadas/cookies)
        else:
            assert not auth
        if url.endswith('/oss/v2/buckets') and m == 'POST':
            raise urllib.error.HTTPError(url, 409, 'x', _Headers(), io.BytesIO(b'{"reason":"Bucket already exists"}'))
        if 'signeds3upload' in url and m == 'GET':
            n = int(url.split('parts=')[1].split('&')[0])
            return Resposta(200, {'uploadKey': 'UK', 'urls': [f'https://s3.falso/parte{i}' for i in range(n)]})
        if url.startswith('https://s3.falso/'):
            self.partes.append(len(req.data))
            return Resposta(200)
        if 'signeds3upload' in url and m == 'POST':
            assert json.loads(req.data) == {'uploadKey': 'UK'}
            chave = url.split('/objects/')[1].split('/')[0]
            return Resposta(200, {'objectId': f'urn:adsk.objects:os.object:b/{chave}', 'size': sum(self.partes)})
        if url.endswith('/designdata/job'):
            corpo = json.loads(req.data)
            assert corpo['output']['formats'] == [{'type': 'ifc'}] and req.get_header('X-ads-force') == 'true'
            if not self.job_ok:
                raise urllib.error.HTTPError(url, 400, 'x', _Headers(), io.BytesIO(b'{"diagnostic":"Failed to trigger translation for this file."}'))
            return Resposta(200, {'result': 'success', 'urn': corpo['input']['urn']})
        if url.endswith('/manifest'):
            return Resposta(200, self.manifestos.pop(0) if len(self.manifestos) > 1 else self.manifestos[0])
        if url.endswith('/signedcookies'):
            if not self.cookies:
                raise urllib.error.HTTPError(url, 404, 'x', _Headers(), io.BytesIO(b'null'))
            return Resposta(200, {'url': 'https://cdn.falso/a.ifc', 'size': len(self.ifc)},
                            {'Set-Cookie': ['CloudFront-Policy=P; Path=/', 'CloudFront-Signature=S; Path=/', 'CloudFront-Key-Pair-Id=K; Path=/']})
        if url == 'https://cdn.falso/a.ifc':
            assert req.get_header('Cookie') == 'CloudFront-Policy=P; CloudFront-Signature=S; CloudFront-Key-Pair-Id=K'
            return Resposta(200, self.ifc)
        if '/manifest/' in url and m == 'GET':      # download direto (fallback)
            return Resposta(200, self.ifc)
        raise AssertionError(f'chamada inesperada {m} {url}')


def _cliente(servidor, agora=None):
    t = [1000.0]
    return aps.ClienteAPS('ID', 'SEGREDO', urlopen=servidor, relogio=lambda: t[0], dormir=lambda s: t.__setitem__(0, t[0] + s))


def test_fluxo_completo_com_servidor_falso(tmp_path):
    rvt = tmp_path / 'p.rvt'
    rvt.write_bytes(b'R' * (7 * 1024 * 1024))                    # 7 MB → duas partes (5 MB + 2 MB)
    srv = ServidorFalso()
    cli = _cliente(srv)
    r = aps.rvt_para_ifc(str(rvt), str(tmp_path / 'p.ifc'), cli, str(tmp_path / 'cache'), progresso=lambda _m: None)
    assert r['cache'] is False and r['bytes'] == len(srv.ifc) and r['urn']
    assert (tmp_path / 'p.ifc').read_bytes() == srv.ifc
    assert srv.partes == [5 * 1024 * 1024, 2 * 1024 * 1024]
    assert srv.tokens == 1                                        # um token para o fluxo todo
    metodos = [m for m, _u in srv.chamadas]
    assert metodos.count('GET') >= 4 and ('POST', f'{HOST}/modelderivative/v2/designdata/job') in srv.chamadas
    # ficou no cache: a segunda vez não toca na rede
    sha = aps.sha256_arquivo(str(rvt))
    assert (tmp_path / 'cache' / f'{sha}.ifc').read_bytes() == srv.ifc
    srv2 = ServidorFalso()
    r2 = aps.rvt_para_ifc(str(rvt), str(tmp_path / 'p2.ifc'), _cliente(srv2), str(tmp_path / 'cache'), progresso=lambda _m: None)
    assert r2['cache'] is True and srv2.chamadas == [] and (tmp_path / 'p2.ifc').read_bytes() == srv.ifc


def test_fallback_download_direto_e_renovacao_do_token(tmp_path):
    rvt = tmp_path / 'p.rvt'; rvt.write_bytes(b'x' * 100)
    srv = ServidorFalso(cookies=False)
    cli = _cliente(srv)
    aps.rvt_para_ifc(str(rvt), str(tmp_path / 'p.ifc'), cli, None, progresso=lambda _m: None)
    assert (tmp_path / 'p.ifc').read_bytes() == srv.ifc
    assert any(u.endswith('/signedcookies') for _m, u in srv.chamadas)
    # token expirado é renovado sozinho
    cli._expira = 0
    cli.token()
    assert srv.tokens == 2


def test_erros_com_a_causa_e_sem_o_segredo(tmp_path):
    rvt = tmp_path / 'p.rvt'; rvt.write_bytes(b'x')
    with pytest.raises(SystemExit, match='token recusado') as e:
        _cliente(ServidorFalso(token_ok=False)).token()
    assert 'SEGREDO' not in str(e.value)
    with pytest.raises(SystemExit, match='não aceitou o arquivo'):
        aps.rvt_para_ifc(str(rvt), str(tmp_path / 'p.ifc'), _cliente(ServidorFalso(job_ok=False)), None, progresso=lambda _m: None)
    falhou = ServidorFalso(manifestos=[{'status': 'failed', 'progress': 'complete',
                                        'derivatives': [{'outputType': 'ifc', 'status': 'failed', 'messages': [{'message': 'Revit version not supported'}]}]}])
    with pytest.raises(SystemExit, match='Revit version not supported'):
        aps.rvt_para_ifc(str(rvt), str(tmp_path / 'p.ifc'), _cliente(falhou), None, progresso=lambda _m: None)
    with pytest.raises(SystemExit, match='não traduz .rfa'):
        aps.rvt_para_ifc(str(tmp_path / 'f.rfa'), str(tmp_path / 'p.ifc'), _cliente(ServidorFalso()), None)
    with pytest.raises(SystemExit, match='sem credenciais'):
        aps.credenciais(None, env={})
    (tmp_path / 'c.json').write_text('{"client_id": "a", "client_secret": "b"}')
    assert aps.credenciais(str(tmp_path / 'c.json'), env={}) == ('a', 'b')
    assert aps.credenciais(None, env={'APS_CLIENT_ID': 'x', 'APS_CLIENT_SECRET': 'y'}) == ('x', 'y')


# ─── ifc_elementos sem ifcopenshell ───────────────────────────────────────────

def test_familia_e_tipo():
    f = ifc_elementos.familia_e_tipo
    assert f('Fam_Caixa:500 L:1840925', 'Fam_Caixa:500 L', '500 L') == ('Fam_Caixa', '500 L')     # exportador da Autodesk
    assert f('Fam_Caixa:500 L', None, None) == ('Fam_Caixa', '500 L')
    assert f('x', 'y', 'z', {'Identity Data': {'Family Name': 'F', 'Type Name': 'T'}}) == ('F', 'T')   # psets mandam
    assert f('Parede', None, 'Genérica 200') == ('Parede', 'Genérica 200')
    assert f('Só nome', None, None) == ('Só nome', 'Só nome')
    assert f('A:B:C:12', None, None) == ('A:B', 'C')


def test_specs_de_filtra_instancia_guid_e_na():
    el = {'classe': 'IfcFlowFitting', 'tipo_ifc': '500 L',
          'psets': {'Identity Data': {'Manufacturer': 'Empresa', 'Type Name': '500 L', 'Mark': '491', 'URL': 'https://x', 'Acabamento': 'n/a'},
                    'Constraints': {'Level': 'Level: 1', 'Host': 'L', 'Offset': 0.0},
                    'Mechanical': {'Loss Method': '3bf616f9-6b98-4a2b-9c0e-000000000000', 'Vazão': 12.5, 'Ativo': True},
                    'Outro': {'Manufacturer': 'Outra'}}}
    s = ifc_elementos.specs_de(el)
    assert s == {'Manufacturer': 'Empresa', 'Type Name': '500 L', 'URL': 'https://x', 'Vazão': '12.5', 'Ativo': 'Sim',
                 'Outro · Manufacturer': 'Outra', 'Classe IFC': 'IfcFlowFitting', 'Tipo IFC': '500 L'}


# ─── com ifcopenshell: IFC sintético ──────────────────────────────────────────

def _ifc_sintetico(caminho):
    """Três IfcFlowStorageDevice: dois do tipo "Caixa:500 L" em posições diferentes e um "Caixa:1000 L", com psets."""
    ifcopenshell = pytest.importorskip('ifcopenshell')
    import ifcopenshell.api
    import numpy as np
    f = ifcopenshell.api.run('project.create_file', version='IFC4')
    proj = ifcopenshell.api.run('root.create_entity', f, ifc_class='IfcProject', name='P')
    ifcopenshell.api.run('unit.assign_unit', f)
    ctx = ifcopenshell.api.run('context.add_context', f, context_type='Model')
    body = ifcopenshell.api.run('context.add_context', f, context_type='Model', context_identifier='Body', target_view='MODEL_VIEW', parent=ctx)
    site = ifcopenshell.api.run('root.create_entity', f, ifc_class='IfcSite', name='S')
    ifcopenshell.api.run('aggregate.assign_object', f, products=[site], relating_object=proj)
    tipo = ifcopenshell.api.run('root.create_entity', f, ifc_class='IfcFlowStorageDeviceType', name='500 L')
    for i, (nome, dims, x, vol) in enumerate([('Caixa:500 L:101', (0.9, 0.9, 1.0), 0, '500 L'), ('Caixa:500 L:102', (0.9, 0.9, 1.0), 3, '500 L'),
                                              ('Caixa:1000 L:103', (1.2, 1.2, 1.3), 6, '1000 L')]):
        e = ifcopenshell.api.run('root.create_entity', f, ifc_class='IfcFlowStorageDevice', name=nome)
        e.ObjectType = nome.rsplit(':', 1)[0]
        m = np.eye(4); m[0, 3] = x
        ifcopenshell.api.run('geometry.edit_object_placement', f, product=e, matrix=m)
        rep = ifcopenshell.api.run('geometry.add_wall_representation', f, context=body, length=dims[0], height=dims[2], thickness=dims[1])
        ifcopenshell.api.run('geometry.assign_representation', f, product=e, representation=rep)
        ifcopenshell.api.run('spatial.assign_container', f, products=[e], relating_structure=site)
        if i < 2:
            ifcopenshell.api.run('type.assign_type', f, related_objects=[e], relating_type=tipo)
        pset = ifcopenshell.api.run('pset.add_pset', f, product=e, name='Identity Data')
        ifcopenshell.api.run('pset.edit_pset', f, pset=pset, properties={'Volume útil': vol, 'Manufacturer': 'Empresa', 'Mark': str(100 + i), 'Category': 'Plumbing Fixtures'})
    f.write(str(caminho))
    return str(caminho)


def test_elementos_locais_agrupados_por_tipo(tmp_path):
    ifc = _ifc_sintetico(tmp_path / 'p.ifc')
    els = list(ifc_elementos.elementos(ifc))
    assert len(els) == 3 and {e['classe'] for e in els} == {'IfcFlowStorageDevice'}
    assert [(e['familia'], e['tipo']) for e in els] == [('Caixa', '500 L'), ('Caixa', '500 L'), ('Caixa', '1000 L')]
    a, b, c = els
    assert (a['verts'] == b['verts']).all()                        # geometria LOCAL: instâncias em x=0 e x=3 dão a mesma malha
    assert a['tipo_ifc'] == '500 L' and c['tipo_ifc'] is None
    grupos = ifc_elementos.por_tipo(els)
    assert [(k, g['instancias']) for k, g in grupos.items()] == [(('Caixa', '500 L'), 2), (('Caixa', '1000 L'), 1)]
    geo = ifc_elementos.geo_do_viewer(c)
    contratos.validar('geometria', geo)
    pos = geo['pos']
    assert max(pos[1::3]) - min(pos[1::3]) == pytest.approx(1.3, abs=1e-6)       # altura (Z-up) virou Y do viewer
    assert ifc_elementos.specs_de(a)['Volume útil'] == '500 L' and 'Mark' not in ifc_elementos.specs_de(a)


class ClienteFalso:
    """O que `rvt_para_ifc` usa de um `ClienteAPS`, sem rede: 'traduz' copiando um IFC pronto."""

    def __init__(self, ifc):
        self.ifc, self.jobs = ifc, 0

    def bucket(self): return 'b'
    def enviar(self, caminho, bucket, progresso=None): return f'urn:adsk.objects:os.object:b/{os.path.basename(caminho)}'
    urn = staticmethod(aps.ClienteAPS.urn)
    def traduzir(self, urn, formato='ifc'): self.jobs += 1; return {'result': 'success'}
    def esperar(self, urn, progresso=None, timeout_s=0): return {'status': 'success', 'derivatives': [{'outputType': 'ifc', 'children': [{'urn': 'x/a.ifc'}]}]}
    derivados = staticmethod(aps.ClienteAPS.derivados)
    def baixar(self, urn, durn, destino):
        import shutil; shutil.copyfile(self.ifc, destino); return os.path.getsize(destino)


def test_projeto_via_ifc_irmao_e_via_aps(tmp_path):
    ifc = _ifc_sintetico(tmp_path / 'irmao' / 'Modelo_Empresa.ifc') if (tmp_path / 'irmao').mkdir() is None else None
    (tmp_path / 'irmao' / 'Modelo_Empresa.rvt').write_bytes(b'nao e OLE')
    d = fr.descobrir(str(tmp_path / 'irmao'))
    assert d['familias'] == [] and d['projetos'][0]['ifc'].endswith('Modelo_Empresa.ifc')
    r = fr.catalogo_de_familias([], str(tmp_path / 'geo'), titulo='Caixas', projetos=d['projetos'], progresso=lambda _m: None)
    contratos.validar('catalogo', r)
    prods = r['catalog']['produtos']
    assert [(p['serie'], p['nome']) for p in prods] == [('Caixa', '500 L'), ('Caixa', '1000 L')]
    p = prods[0]
    assert p['specs']['Instâncias no projeto'] == '2' and p['specs']['Categoria Revit'] == 'Plumbing Fixtures' and 'Category' not in p['specs']
    assert p['specs']['Fonte 3D'].startswith('IFC do projeto (') and p['specs']['Projeto Revit'] == 'Modelo_Empresa'
    assert p['specs']['Família Revit'] == 'Caixa' and p['specs']['Tipo Revit'] == '500 L' and p['conexoes'] == 'Plumbing Fixtures'
    assert r['config']['fabricante'] == 'Empresa' and r['n_geometrias'] == 2 and r['hints']['origem']['projetos'] == {
        'projetos': 1, 'traduzidos_aps': 0, 'do_cache': 0, 'ifc_irmao': 1, 'fora': 0, 'produtos': 2}
    for q in prods:
        contratos.validar('geometria', json.loads((tmp_path / 'geo' / q['geo']).read_text()))
    # sem IFC irmão e sem APS: fora, com a explicação; com APS falsa: traduzido
    (tmp_path / 'so').mkdir(); (tmp_path / 'so' / 'Modelo.rvt').write_bytes(b'x')
    d2 = fr.descobrir(str(tmp_path / 'so'))
    r2 = fr.catalogo_de_familias([], str(tmp_path / 'geo2'), projetos=d2['projetos'], progresso=lambda _m: None)
    assert r2['catalog']['produtos'] == [] and 'Autodesk Platform Services' in r2['diag']['avisos'][0]
    falso = ClienteFalso(ifc)
    r3 = fr.catalogo_de_familias([], str(tmp_path / 'geo3'), projetos=d2['projetos'], aps={'cliente': falso, 'cache': str(tmp_path / 'cache')},
                                 trabalho=str(tmp_path / 'trab'), progresso=lambda _m: None)
    assert len(r3['catalog']['produtos']) == 2 and falso.jobs == 1
    assert r3['catalog']['produtos'][0]['specs']['Fonte 3D'] == 'IFC do projeto traduzido pela Autodesk Platform Services'
    assert r3['hints']['origem']['projetos']['traduzidos_aps'] == 1
    # segunda vez: do cache, zero jobs
    r4 = fr.catalogo_de_familias([], str(tmp_path / 'geo4'), projetos=d2['projetos'], aps={'cliente': falso, 'cache': str(tmp_path / 'cache')},
                                 trabalho=str(tmp_path / 'trab2'), progresso=lambda _m: None)
    assert falso.jobs == 1 and r4['hints']['origem']['projetos']['do_cache'] == 1


@pytest.mark.skipif(not PROJETO_REAL, reason='fixture "rvt_projeto" não configurada (tests/fixtures.py)')
def test_projeto_real_pela_cli_com_cache(tmp_path):
    pytest.importorskip('ifcopenshell')
    cache = os.path.join(RAIZ, FIXTURAS['rvt_projeto'].get('aps_cache', 'storage/bim/aps'))
    r = subprocess.run([sys.executable, '-m', 'bim_pipeline.cli.familias_revit', 'inspecionar', PROJETO_REAL], capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stderr[-2000:]
    info = json.loads(r.stdout.strip().splitlines()[-1])
    contratos.validar('info-familias-revit', info)
    assert info['n_projetos'] >= 1 and info['projetos'][0]['formato']
    (tmp_path / 'c.json').write_text('{"client_id": "cache-only", "client_secret": "cache-only"}')
    saida = tmp_path / 'cat.json'
    r = subprocess.run([sys.executable, '-m', 'bim_pipeline.cli.familias_revit', 'importar', PROJETO_REAL, '--geo-dir', str(tmp_path / 'geo'),
                        '--saida', str(saida), '--aps-credenciais', str(tmp_path / 'c.json'), '--aps-cache', cache], capture_output=True, text=True, timeout=1200)
    if 'IFC do cache' not in r.stderr:
        pytest.skip('IFC do projeto não está no cache da APS — a suíte não gasta jobs')
    assert r.returncode == 0, r.stderr[-2000:]
    res = json.loads(saida.read_text(encoding='utf8'))
    contratos.validar('catalogo', res)
    assert res['hints']['origem']['projetos']['do_cache'] >= 1 and res['catalog']['produtos']
    for p in res['catalog']['produtos']:
        contratos.validar('geometria', json.loads((tmp_path / 'geo' / p['geo']).read_text(encoding='utf8')))
        assert p['specs']['Fonte 3D'].startswith('IFC do projeto') and p['specs']['Instâncias no projeto']
