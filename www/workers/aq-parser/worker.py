import os
import sys
import json
import uuid
import time
import tempfile
import tracemalloc
import resource
from datetime import datetime, timezone

# Add scripts/ to sys.path (repo root is 3 levels above this file)
_REPO_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'scripts'))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '../..', '.env'))

import read_aq
import oq3d

from flask import Flask, request, jsonify
import pymongo

app = Flask(__name__)

_STORAGE_PATH = os.environ.get('STORAGE_PATH', '')
_MONGODB_URI = os.environ.get('MONGODB_URI', '')
_MONGODB_DB = os.environ.get('MONGODB_DB', 'bilds-bim-3d')


class DiskGeometryStore:
    def __init__(self, base_dir):
        self.base_dir = os.path.realpath(base_dir)

    def _validate(self, key):
        full = os.path.realpath(os.path.join(self.base_dir, key))
        if not full.startswith(self.base_dir + os.sep):
            raise ValueError(f'Key escapes storage root: {key}')
        return full

    def put(self, key, data: bytes):
        full = self._validate(key)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, 'wb') as f:
            f.write(data)


@app.route('/health')
def health():
    return jsonify({'status': 'ok'})


@app.route('/parse', methods=['POST'])
def parse():
    if not request.data:
        return jsonify({'status': 'failed', 'error': 'empty body'}), 400

    import_id = request.headers.get('X-Import-Id', str(uuid.uuid4()))
    company_id = request.headers.get('X-Company-Id', '')
    catalog_id = request.headers.get('X-Catalog-Id', str(uuid.uuid4()))
    file_name = request.headers.get('X-File-Name', 'upload.aq')

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.aq')
    tmp.write(request.data)
    tmp_path = tmp.name
    tmp.close()

    rss_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    tracemalloc.start()
    t0 = time.time()

    try:
        simbologias, por_peca = read_aq.extract_simbologias(tmp_path)
        aq_data = read_aq.extract(tmp_path)

        grupos_by_id = {g['ID_GRUPO_PECA']: g for g in aq_data['grupos']}

        curves_by_peca = {}
        for pt in aq_data['curvas']:
            pid = pt['ID_PECA']
            if pid not in curves_by_peca:
                curves_by_peca[pid] = []
            curves_by_peca[pid].append([
                round(float(pt['vazao']), 3),
                round(float(pt['altura']), 3),
                round(float(pt['potencia_ponto'] or 0), 3),
                round(float(pt['rendimento'] or 0), 1),
            ])

        props_by_peca = {}
        for p in aq_data['propriedades']:
            pid = p['ID_PECA']
            if pid not in props_by_peca:
                props_by_peca[pid] = {}
            props_by_peca[pid][p['propriedade']] = p['VALOR']

        store = DiskGeometryStore(_STORAGE_PATH)

        mongo_client = pymongo.MongoClient(_MONGODB_URI)
        db = mongo_client[_MONGODB_DB]

        docs = []
        for peca in aq_data['pecas']:
            pid = peca['ID_PECA']
            sid = por_peca.get(pid)
            if sid is None or sid not in simbologias:
                continue
            blob = simbologias[sid]['blob']
            if not blob or not oq3d.is_oq3d(blob):
                continue

            geo_data = oq3d.to_buffers(blob)
            product_uuid = str(uuid.uuid4())
            geo_key = f'geo/{import_id}/{product_uuid}.json'
            store.put(geo_key, json.dumps(geo_data).encode('utf-8'))

            gid = peca.get('ID_GRUPO_PECA')
            grupo = grupos_by_id.get(gid, {})

            docs.append({
                '_id': product_uuid,
                'catalogId': catalog_id,
                'importId': import_id,
                'id': str(pid),
                'nome': peca.get('NOME_PECA', ''),
                'serie': grupo.get('NOME_GP', ''),
                'specs': props_by_peca.get(pid, {}),
                'curva': curves_by_peca.get(pid),
                'conexoes': peca.get('DESCRICAO_DADOS', ''),
                'potencia': None,
                'geoKey': geo_key,
                'thumbKey': None,
                'createdAt': datetime.now(timezone.utc),
            })

        _, peak_trace = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        rss_after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        peak_rss_kb = max(0, rss_after - rss_before)

        product_count = len(docs)
        status = 'ok' if product_count > 0 else 'empty'

        if docs:
            db['bim_catalogs'].update_one(
                {'_id': catalog_id},
                {
                    '$set': {
                        'companyId': company_id,
                        'fileName': file_name,
                        'productCount': product_count,
                        'updatedAt': datetime.now(timezone.utc),
                    },
                    '$setOnInsert': {'createdAt': datetime.now(timezone.utc)},
                },
                upsert=True,
            )
            db['bim_products'].insert_many(docs)

        mongo_client.close()

        return jsonify({
            'status': status,
            'productCount': product_count,
            'peakMemoryMb': round(peak_rss_kb / 1024, 2),
            'peakTraceMb': round(peak_trace / 1024 / 1024, 2),
            'elapsedMs': round((time.time() - t0) * 1000),
        })

    except Exception as exc:
        tracemalloc.stop()
        return jsonify({'status': 'failed', 'error': str(exc)}), 500

    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


if __name__ == '__main__':
    port = int(os.environ.get('WORKER_PORT', '5001'))
    app.run(host='127.0.0.1', port=port)
