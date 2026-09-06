#!/usr/bin/env python3
"""
aps.py — Autodesk Platform Services (Model Derivative): um projeto Revit `.rvt` → IFC, na nuvem da Autodesk.

POR QUE EXISTE: a geometria de um `.rvt` (e de um `.rfa`) é um binário proprietário ilegível fora do Revit
(`docs/conhecimento/revit-familias.md`). O Model Derivative traduz `.rvt` para IFC — e é a ÚNICA das saídas
que a biblioteca já lê. Ele **não aceita `.rfa`** (verificado em `GET designdata/formats`: `rfa` não está
em nenhuma lista de entrada), então o caminho serve para PROJETOS — o que fabricantes distribuem quando
entregam as famílias já colocadas num modelo de amostra.

O FLUXO (APS v2; endpoints verificados em 2026-09):
    POST /authentication/v2/token          client_credentials, Basic <id:secret>, escopos data:read/write/create bucket:create/read
    POST /oss/v2/buckets                   {bucketKey, policyKey:'transient'}  (409 = já existe; o transient expira em 24 h)
    GET  /oss/v2/buckets/{b}/objects/{k}/signeds3upload?parts=N   → {uploadKey, urls[]}; PUT cada parte (≥ 5 MB, menos a última) na URL
    POST /oss/v2/buckets/{b}/objects/{k}/signeds3upload           {uploadKey} → {objectId}
    POST /modelderivative/v2/designdata/job                        {input:{urn: base64url(objectId)}, output:{formats:[{type:'ifc'}]}}
    GET  /modelderivative/v2/designdata/{urn}/manifest             status pending|inprogress|success|failed|timeout, progress
    GET  …/{urn}/manifest/{derivativeUrn}/signedcookies            → {url} + Set-Cookie (CloudFront); GET url com os cookies
                                                                   (fallback: GET …/manifest/{derivativeUrn}, o download direto antigo)

CUSTO E PRIVACIDADE: cada job de tradução consome tokens da conta APS e o arquivo sai desta máquina para a
Autodesk. Por isso o caminho é OPT-IN (quem importa marca "usar a APS") e há cache por SHA-256 do `.rvt`
(`cache_dir`): o mesmo projeto nunca é traduzido duas vezes. As credenciais chegam por arquivo JSON
(`{client_id, client_secret}`) ou pelas variáveis `APS_CLIENT_ID`/`APS_CLIENT_SECRET`; nunca são gravadas
em log — o segredo aparece só no cabeçalho Basic do token.

Uso (operador):
    APS_CLIENT_ID=… APS_CLIENT_SECRET=… python3 -m bim_pipeline.cli.aps projeto.rvt saida.ifc [--cache DIR]
"""
import argparse
import base64
import hashlib
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HOST = 'https://developer.api.autodesk.com'
ESCOPOS = 'data:read data:write data:create bucket:create bucket:read viewables:read'
PARTE_BYTES = 5 * 1024 * 1024          # o S3 exige partes de pelo menos 5 MB (menos a última)
INTERVALO_MANIFEST_S = 15
TIMEOUT_TRADUCAO_S = 40 * 60
ENTRADAS_ACEITAS = ('.rvt',)           # o que este módulo manda traduzir; `.rfa` NÃO é aceito pela APS


class APSError(SystemExit):
    def __init__(self, msg):
        super().__init__(f'aps: {msg}')


def avisar(msg):
    print(msg, file=sys.stderr, flush=True)


def credenciais(arquivo=None, env=os.environ):
    """`(client_id, client_secret)` do JSON `arquivo` ou das variáveis de ambiente; erro claro se faltar."""
    cid = sec = None
    if arquivo:
        with open(arquivo, encoding='utf-8') as f:
            d = json.load(f)
        cid, sec = d.get('client_id'), d.get('client_secret')
    cid = cid or env.get('APS_CLIENT_ID')
    sec = sec or env.get('APS_CLIENT_SECRET')
    if not cid or not sec:
        raise APSError('sem credenciais — passe --aps-credenciais <json> ou defina APS_CLIENT_ID e APS_CLIENT_SECRET')
    return cid, sec


def _redigir(texto, segredos):
    for s in segredos:
        if s:
            texto = texto.replace(s, '***')
    return texto


class ClienteAPS:
    """As chamadas HTTP do fluxo, com o token renovado quando expira. `urlopen` é injetável para teste."""

    def __init__(self, client_id, client_secret, urlopen=urllib.request.urlopen, relogio=time.time, dormir=time.sleep):
        self.cid, self.sec = client_id, client_secret
        self._urlopen, self._agora, self._dormir = urlopen, relogio, dormir
        self._token, self._expira = None, 0.0

    # ── HTTP ─────────────────────────────────────────────────────────────────
    def _req(self, metodo, url, dados=None, cabecalhos=None, form=False, bruto=False, autenticar=True, timeout=900):
        h = dict(cabecalhos or {})
        if autenticar:
            h['Authorization'] = f'Bearer {self.token()}'
        corpo = None
        if dados is not None:
            if isinstance(dados, (bytes, bytearray)):
                corpo = bytes(dados)
            elif form:
                corpo = urllib.parse.urlencode(dados).encode()
                h['Content-Type'] = 'application/x-www-form-urlencoded'
            else:
                corpo = json.dumps(dados).encode()
                h['Content-Type'] = 'application/json'
        try:
            with self._urlopen(urllib.request.Request(url, data=corpo, headers=h, method=metodo), timeout=timeout) as r:
                b = r.read()
                return r.status, (b if bruto else (json.loads(b) if b else {})), r.headers
        except urllib.error.HTTPError as e:
            b = e.read()
            return e.code, (b if bruto else _json_ou_texto(b)), e.headers
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise APSError(f'falha de rede em {metodo} {url.split("?")[0]}: {_redigir(str(e), (self.sec,))}')

    def token(self):
        if self._token and self._agora() < self._expira - 60:
            return self._token
        basic = base64.b64encode(f'{self.cid}:{self.sec}'.encode()).decode()
        st, r, _ = self._req('POST', f'{HOST}/authentication/v2/token', {'grant_type': 'client_credentials', 'scope': ESCOPOS},
                             {'Authorization': f'Basic {basic}'}, form=True, autenticar=False, timeout=60)
        if st != 200 or 'access_token' not in r:
            raise APSError(f'token recusado (HTTP {st}) — client id/secret inválidos ou app sem a API Model Derivative: {_redigir(str(r)[:300], (self.sec,))}')
        self._token, self._expira = r['access_token'], self._agora() + float(r.get('expires_in', 3600))
        return self._token

    # ── OSS ──────────────────────────────────────────────────────────────────
    def bucket(self):
        """Um bucket transiente por app (a chave leva o hash do client id — tem de ser única na APS inteira)."""
        chave = ('bilds-bim-3d-' + hashlib.sha1(self.cid.encode()).hexdigest()[:16]).lower()
        st, r, _ = self._req('POST', f'{HOST}/oss/v2/buckets', {'bucketKey': chave, 'policyKey': 'transient'}, timeout=60)
        if st not in (200, 409):
            raise APSError(f'bucket {chave}: HTTP {st} {str(r)[:300]}')
        return chave

    def enviar(self, caminho, bucket, progresso=avisar):
        """Upload por URLs S3 assinadas, em partes de 5 MB. Devolve o `objectId` (`urn:adsk.objects:os.object:…`)."""
        tamanho = os.path.getsize(caminho)
        with open(caminho, 'rb') as f:
            sha = hashlib.sha256()
            for bloco in iter(lambda: f.read(1 << 20), b''):
                sha.update(bloco)
        chave = sha.hexdigest()[:24] + os.path.splitext(caminho)[1].lower()
        n = max(1, (tamanho + PARTE_BYTES - 1) // PARTE_BYTES)
        base = f'{HOST}/oss/v2/buckets/{bucket}/objects/{chave}/signeds3upload'
        st, s3, _ = self._req('GET', f'{base}?parts={n}&minutesExpiration=60', timeout=60)
        if st != 200 or not s3.get('urls'):
            raise APSError(f'signeds3upload: HTTP {st} {str(s3)[:300]}')
        with open(caminho, 'rb') as f:
            for i, url in enumerate(s3['urls'][:n]):
                parte = f.read(PARTE_BYTES)
                with self._urlopen(urllib.request.Request(url, data=parte, method='PUT'), timeout=900) as r:
                    if r.status not in (200, 201):
                        raise APSError(f'PUT parte {i + 1}/{n}: HTTP {r.status}')
                progresso(f'    upload {min((i + 1) * PARTE_BYTES, tamanho) / 1e6:.0f}/{tamanho / 1e6:.0f} MB')
        st, obj, _ = self._req('POST', base, {'uploadKey': s3['uploadKey']}, timeout=120)
        if st != 200 or 'objectId' not in obj:
            raise APSError(f'conclusão do upload: HTTP {st} {str(obj)[:300]}')
        return obj['objectId']

    # ── Model Derivative ─────────────────────────────────────────────────────
    @staticmethod
    def urn(object_id):
        return base64.urlsafe_b64encode(object_id.encode()).decode().rstrip('=')

    def traduzir(self, urn, formato='ifc'):
        st, r, _ = self._req('POST', f'{HOST}/modelderivative/v2/designdata/job',
                             {'input': {'urn': urn}, 'output': {'formats': [{'type': formato}]}}, {'x-ads-force': 'true'}, timeout=120)
        if st not in (200, 201):
            raise APSError(f'job {formato}: HTTP {st} {str(r)[:300]} — o Model Derivative não aceitou o arquivo '
                           f'(formatos aceitos: GET designdata/formats; .rfa não é um deles)')
        return r

    def manifesto(self, urn):
        st, r, _ = self._req('GET', f'{HOST}/modelderivative/v2/designdata/{urn}/manifest', timeout=60)
        return (r if st == 200 else {'status': 'pending', 'progress': f'HTTP {st}'})

    def esperar(self, urn, progresso=avisar, timeout_s=TIMEOUT_TRADUCAO_S):
        t0 = self._agora()
        ultimo = None
        while True:
            man = self.manifesto(urn)
            estado = f"{man.get('status')} {man.get('progress') or ''}".strip()
            if estado != ultimo:
                progresso(f'    tradução: {estado}')
                ultimo = estado
            if man.get('status') in ('success', 'failed', 'timeout'):
                return man
            if self._agora() - t0 > timeout_s:
                raise APSError(f'tradução não terminou em {timeout_s / 60:.0f} min (status {man.get("status")})')
            self._dormir(INTERVALO_MANIFEST_S)

    @staticmethod
    def derivados(manifesto, formato='ifc', extensao='.ifc'):
        out = []
        for d in manifesto.get('derivatives') or []:
            if d.get('outputType') != formato:
                continue
            for c in d.get('children') or []:
                if str(c.get('urn', '')).lower().endswith(extensao):
                    out.append(c['urn'])
            if d.get('status') == 'failed':
                msgs = [m.get('message') for m in d.get('messages') or [] if m.get('message')]
                raise APSError(f'tradução para {formato} falhou: {"; ".join(str(m) for m in msgs)[:500] or "sem mensagem"}')
        return out

    def baixar(self, urn, derivado_urn, destino):
        q = urllib.parse.quote(derivado_urn, safe='')
        st, sc, hdr = self._req('GET', f'{HOST}/modelderivative/v2/designdata/{urn}/manifest/{q}/signedcookies', timeout=60)
        if st == 200 and sc.get('url'):
            cookies = '; '.join(v.split(';')[0] for v in (hdr.get_all('Set-Cookie') if hasattr(hdr, 'get_all') else []) or [])
            with self._urlopen(urllib.request.Request(sc['url'], headers={'Cookie': cookies}), timeout=1800) as r, open(destino, 'wb') as f:
                shutil.copyfileobj(r, f)
        else:
            st, b, _ = self._req('GET', f'{HOST}/modelderivative/v2/designdata/{urn}/manifest/{q}', bruto=True, timeout=1800)
            if st != 200:
                raise APSError(f'download do derivado: HTTP {st}')
            with open(destino, 'wb') as f:
                f.write(b)
        return os.path.getsize(destino)


def _json_ou_texto(b):
    try:
        return json.loads(b)
    except ValueError:
        return b[:500].decode('utf-8', 'replace')


def sha256_arquivo(caminho):
    h = hashlib.sha256()
    with open(caminho, 'rb') as f:
        for bloco in iter(lambda: f.read(1 << 20), b''):
            h.update(bloco)
    return h.hexdigest()


def rvt_para_ifc(caminho_rvt, destino_ifc, cliente, cache_dir=None, progresso=avisar):
    """
    `.rvt` → IFC em `destino_ifc`. Com `cache_dir`, `<sha256>.ifc` de uma tradução anterior é reaproveitado
    (zero jobs). Devolve `{'cache': bool, 'segundos': float, 'bytes': int, 'urn': str|None}`.
    """
    ext = os.path.splitext(caminho_rvt)[1].lower()
    if ext not in ENTRADAS_ACEITAS:
        raise APSError(f'{os.path.basename(caminho_rvt)}: a APS Model Derivative não traduz {ext} (aceita .rvt; .rfa não)')
    t0 = time.time()
    sha = sha256_arquivo(caminho_rvt)
    em_cache = os.path.join(cache_dir, f'{sha}.ifc') if cache_dir else None
    if em_cache and os.path.exists(em_cache) and os.path.getsize(em_cache) > 0:
        shutil.copyfile(em_cache, destino_ifc)
        progresso(f'  {os.path.basename(caminho_rvt)}: IFC do cache ({os.path.getsize(destino_ifc) / 1e6:.1f} MB) — sem job na APS')
        return {'cache': True, 'segundos': round(time.time() - t0, 1), 'bytes': os.path.getsize(destino_ifc), 'urn': None}
    progresso(f'  {os.path.basename(caminho_rvt)}: enviando à APS ({os.path.getsize(caminho_rvt) / 1e6:.1f} MB)')
    bucket = cliente.bucket()
    object_id = cliente.enviar(caminho_rvt, bucket, progresso)
    urn = cliente.urn(object_id)
    cliente.traduzir(urn, 'ifc')
    man = cliente.esperar(urn, progresso)
    alvos = cliente.derivados(man, 'ifc', '.ifc')          # levanta com as mensagens do manifesto se a tradução falhou
    if man.get('status') != 'success':
        raise APSError(f'{os.path.basename(caminho_rvt)}: tradução terminou em {man.get("status")}')
    if not alvos:
        raise APSError(f'{os.path.basename(caminho_rvt)}: manifesto sem derivado .ifc')
    tamanho = cliente.baixar(urn, alvos[0], destino_ifc)
    if em_cache:
        os.makedirs(cache_dir, exist_ok=True)
        shutil.copyfile(destino_ifc, em_cache)
    progresso(f'  {os.path.basename(caminho_rvt)}: IFC baixado ({tamanho / 1e6:.1f} MB) em {time.time() - t0:.0f} s')
    return {'cache': False, 'segundos': round(time.time() - t0, 1), 'bytes': tamanho, 'urn': urn}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('rvt')
    ap.add_argument('saida', help='caminho do .ifc a gravar')
    ap.add_argument('--credenciais', help='JSON {client_id, client_secret} (padrão: APS_CLIENT_ID/APS_CLIENT_SECRET)')
    ap.add_argument('--cache', help='pasta de cache por SHA-256 do .rvt')
    args = ap.parse_args()
    cid, sec = credenciais(args.credenciais)
    r = rvt_para_ifc(args.rvt, args.saida, ClienteAPS(cid, sec), args.cache)
    print(json.dumps(r))


if __name__ == '__main__':
    main()
