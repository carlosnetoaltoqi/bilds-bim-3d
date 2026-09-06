"""
catalogo.py — o `.aq` vira catálogo: produtos, séries e um JSON de geometria por
simbologia. É o miolo do pipeline (era `build_catalog_from_aq` em `scripts/build.py`
até 2026-09-05; movido para o serviço de ingestão na etapa E2 de
docs/arquitetura-www-servico-de-ingestao.md).

Quem usa: `scripts/build.py` (pipeline estático → ZIP) e `catalogo_de_aq.py` (CLI que
o serviço `apps/ingestao` executa). Os dois produzem o MESMO catálogo a partir do
mesmo `.aq` — por isso isto mora num lugar só.
"""
import json
import os
import re
import unicodedata
import warnings

AQUI = os.path.dirname(os.path.abspath(__file__))
if AQUI not in __import__('sys').path:
    __import__('sys').path.insert(0, AQUI)

from bim_pipeline.aq import oq3d
from bim_pipeline.geometria.dedup import dedup           # noqa: E402
from bim_pipeline.aq.read_aq import extract as extract_aq, extract_simbologias   # noqa: E402


def slugify(s):
    s = unicodedata.normalize('NFD', s or '')
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')


def tokenize(s):
    """Tokens alfanuméricos em minúsculas extraídos de qualquer string."""
    return set(re.findall(r'[a-z0-9]+', s.lower()))


def _potencia_de(nome_gp, peca):
    """Potência em CV a partir do nome do grupo ou dos dados da peça."""
    m = re.search(r'(\d+(?:[.,]\d+)?)\s*CV', nome_gp or '', re.IGNORECASE)
    if m:
        return float(m.group(1).replace(',', '.'))
    return peca.get('potencia_cv')


def diag_vazio():
    return {
        'pecas_sem_simbologia': 0, 'pecas_sim_descartada': 0,
        'sim_sem_blob': 0, 'sim_nao_oq3d': 0,
        'sim_ilegivel': [], 'sim_vazia': [], 'avisos': [],
    }


def build_catalog_from_aq(config, aq_path, geo_dir, progresso=None):
    """
    Gera o catálogo e os JSONs de geometria direto do .aq — sem IFC.

    O vínculo peça → geometria vem de PECA_SIMBOLOGIA_3D (chave estrangeira),
    então não há file_map nem matching por nome. Peças sem simbologia 3D são
    puladas: na prática são tubos (cilindro paramétrico gerado pelo AltoQi) e
    kits de aparelho sanitário, que não têm forma fixa.

    `config` traz slug/titulo/fabricante/descricao/layout (ver `inferencia.auto_config`).
    `progresso(mensagem)`, se dado, recebe uma linha a cada etapa e a cada 50
    geometrias — o serviço de ingestão mostra isso ao usuário.

    Retorna (catalog, n_geometrias, diag). `diag` separa o que antes era um único
    número "peças sem 3D (tubos/kits)":

      pecas_sem_simbologia   peça sem linha em PECA_SIMBOLOGIA_3D — tubo ou kit,
                             comportamento esperado;
      pecas_sim_descartada   peça cuja simbologia existe mas foi descartada por um
                             dos motivos abaixo — ISSO é defeito de dado ou de parser;
      sim_sem_blob           SIMBOLOGIA_3D com BLOB nulo/vazio;
      sim_nao_oq3d           blob sem a assinatura OQ3D;
      sim_ilegivel           [(id, nome, erro)] — `OQ3DError` (truncado/corrompido);
      sim_vazia              [(id, nome)] — parse ok, mas nenhuma malha;
      avisos                 [(id, nome, mensagem)] — `OQ3DAvisoParse` coletados
                             durante o parse (hierarquia suspeita, bloco pulado).

    Use `resumo_diag()` para imprimir. Nada aqui é engolido: o operador vê cada
    categoria, e a suíte em tests/ cobre todas.
    """
    avisar = progresso or (lambda _m: None)

    aq_data = extract_aq(aq_path)
    simbologias, sim_por_peca = extract_simbologias(aq_path)
    avisar(f'{len(aq_data["pecas"])} peças, {len(simbologias)} simbologias lidas do .aq')

    grupos_by_id = {g['ID_GRUPO_PECA']: g for g in aq_data['grupos']}

    props_by_peca = {}
    for p in aq_data['propriedades']:
        props_by_peca.setdefault(p['ID_PECA'], {})[p['propriedade']] = p['VALOR']

    curvas_by_peca = {}
    for pt in aq_data['curvas']:
        curvas_by_peca.setdefault(pt['ID_PECA'], []).append([
            round(pt['vazao'], 3), round(pt['altura'], 3),
            round(pt['potencia_ponto'] or 0, 3), round(pt['rendimento'] or 0, 1),
        ])

    os.makedirs(geo_dir, exist_ok=True)

    # Uma geometria por simbologia; várias peças podem compartilhá-la.
    # O nome da simbologia costuma ser só a dimensão ("100MM"), que se repete
    # entre grupos — por isso o grupo entra no slug quando há colisão.
    geo_por_sim = {}
    usados = set()
    diag = diag_vazio()
    for i, sid in enumerate(sorted(simbologias), 1):
        sim = simbologias[sid]
        blob = sim['blob']
        if not blob:
            diag['sim_sem_blob'] += 1
            continue
        if not oq3d.is_oq3d(blob):
            diag['sim_nao_oq3d'] += 1
            continue
        # `warnings.warn` sozinho não chega ao operador: o filtro padrão mostra só
        # a primeira ocorrência por linha de código e o texto vai para o stderr
        # sem dizer de qual simbologia é. Coleta-se por simbologia e imprime-se
        # no resumo (resumo_diag).
        with warnings.catch_warnings(record=True) as capturados:
            warnings.simplefilter('always', oq3d.OQ3DAvisoParse)
            try:
                data = oq3d.to_buffers(blob)
            except oq3d.OQ3DError as e:
                diag['sim_ilegivel'].append((sid, sim['nome'], str(e)))
                continue
        for w in capturados:
            if issubclass(w.category, oq3d.OQ3DAvisoParse):
                diag['avisos'].append((sid, sim['nome'], str(w.message)))
        if not data['pos']:
            diag['sim_vazia'].append((sid, sim['nome']))
            continue

        name = slugify(sim['nome'])[:60]
        if not name or name in usados:
            name = slugify(f"{sim['grupo']} {sim['nome']}")[:60]
        if not name:
            name = f'sim-{sid}'
        base = name
        n = 2
        while name in usados:
            name = f'{base}-{n}'
            n += 1
        usados.add(name)

        # Mesma deduplicação do caminho IFC: o OQ3D indexa dentro de cada malha,
        # mas as malhas de uma peça repetem vértices entre si (~79% de redução).
        data, _, _, _ = dedup(data)
        with open(os.path.join(geo_dir, name + '.json'), 'w', encoding='utf-8') as f:
            json.dump(data, f, separators=(',', ':'))
        geo_por_sim[sid] = name
        if len(geo_por_sim) % 50 == 0:
            avisar(f'{len(geo_por_sim)} geometrias gravadas ({i}/{len(simbologias)} simbologias)')

    # O nome da peça só recebe o prefixo do grupo quando sozinho é ambíguo —
    # e a decisão é POR GRUPO, para todas as peças dele saírem no mesmo padrão.
    # "100mm" se repete entre Cap/Luva/Joelho e "3CV T 220/380V" entre as séries
    # CAM: ambos precisam do grupo. Já "Interruptor inteligente 1 tecla - EWS
    # 1001 BR" é único, e prefixar com a categoria ("Pontos de comando") só
    # poluiria o nome exibido.
    grupos_por_nome = {}
    for p in aq_data['pecas']:
        n = (p['NOME_PECA'] or '').strip().lower()
        grupos_por_nome.setdefault(n, set()).add(p['ID_GRUPO_PECA'])

    grupo_precisa_prefixo = set()
    for p in aq_data['pecas']:
        n = (p['NOME_PECA'] or '').strip()
        if len(n) < 4 or len(grupos_por_nome.get(n.lower(), ())) > 1:
            grupo_precisa_prefixo.add(p['ID_GRUPO_PECA'])

    produtos = []
    series_set = set()
    ids_usados = set()

    for p in aq_data['pecas']:
        pid = p['ID_PECA']
        sid = sim_por_peca.get(pid)
        if sid is None or sid not in simbologias:
            diag['pecas_sem_simbologia'] += 1      # tubo/kit: esperado
            continue
        geo = geo_por_sim.get(sid)
        if not geo:
            diag['pecas_sim_descartada'] += 1     # simbologia existe e falhou
            continue

        nome_gp = grupos_by_id.get(p['ID_GRUPO_PECA'], {}).get('NOME_GP', '')
        nome_peca = (p['NOME_PECA'] or '').strip()
        if (nome_gp and p['ID_GRUPO_PECA'] in grupo_precisa_prefixo
                and nome_gp.lower() not in nome_peca.lower()):
            nome_peca = f'{nome_gp} {nome_peca}'.strip()
        if not nome_peca:
            nome_peca = nome_gp or f'Peça {pid}'

        pid_slug = slugify(nome_peca) or f'peca-{pid}'
        base_slug = pid_slug
        n = 2
        while pid_slug in ids_usados:
            pid_slug = f'{base_slug}-{n}'
            n += 1
        ids_usados.add(pid_slug)

        serie = nome_gp or 'Outros'
        produtos.append({
            'id': pid_slug,
            'nome': nome_peca,
            'serie': serie,
            'geo': f'{geo}.json',
            'potencia': _potencia_de(nome_gp, p),
            'conexoes': p.get('DESCRICAO_DADOS') or '',
            'specs': props_by_peca.get(pid, {}),
            'curva': curvas_by_peca.get(pid),
        })
        series_set.add(serie)

    catalog = {
        'slug': config['slug'],
        'titulo': config['titulo'],
        'fabricante': config['fabricante'],
        'descricao': config.get('descricao', ''),
        'layout': config.get('layout', 'catalog-grid'),
        'filtros': sorted(s for s in series_set if s),
        'produtos': produtos,
    }
    avisar(f'{len(produtos)} produtos, {len(geo_por_sim)} geometrias')
    return catalog, len(geo_por_sim), diag


def resumo_diag(diag, indent='    ', max_itens=5, out=None):
    """
    Imprime o diagnóstico de build_catalog_from_aq e devolve True se houve algo
    além de tubos/kits — simbologia descartada ou aviso de parse.

    Tubos/kits são informativos. O resto sai como AVISO com id e nome da
    simbologia, para que o operador saiba QUAL geometria olhar. `out` é a função
    que recebe cada linha (padrão `print`).
    """
    emitir = out or print
    if diag['pecas_sem_simbologia']:
        emitir(f"{indent}{diag['pecas_sem_simbologia']} peça(s) sem simbologia 3D "
               f"(tubos/kits) puladas — esperado")

    descartadas = (diag['sim_sem_blob'] + diag['sim_nao_oq3d']
                   + len(diag['sim_ilegivel']) + len(diag['sim_vazia']))
    problema = False
    if descartadas:
        problema = True
        motivos = []
        if diag['sim_sem_blob']:
            motivos.append(f"{diag['sim_sem_blob']} sem blob")
        if diag['sim_nao_oq3d']:
            motivos.append(f"{diag['sim_nao_oq3d']} sem assinatura OQ3D")
        if diag['sim_ilegivel']:
            motivos.append(f"{len(diag['sim_ilegivel'])} ilegível(is)")
        if diag['sim_vazia']:
            motivos.append(f"{len(diag['sim_vazia'])} sem malha")
        emitir(f"{indent}AVISO: {descartadas} simbologia(s) descartada(s) — "
               f"{', '.join(motivos)}; {diag['pecas_sim_descartada']} peça(s) "
               f"ficaram sem 3D por isso")
        for sid, nome, erro in diag['sim_ilegivel'][:max_itens]:
            emitir(f'{indent}    sim {sid} {nome!r}: {erro[:90]}')
        for sid, nome in diag['sim_vazia'][:max_itens]:
            emitir(f'{indent}    sim {sid} {nome!r}: parse sem nenhuma malha')

    if diag['avisos']:
        problema = True
        por_sim = {}
        for sid, nome, msg in diag['avisos']:
            por_sim.setdefault((sid, nome), []).append(msg)
        emitir(f"{indent}AVISO: {len(por_sim)} simbologia(s) com aviso de parse "
               f"(geometria incompleta ou hierarquia suspeita)")
        for (sid, nome), msgs in list(por_sim.items())[:max_itens]:
            extra = f' (+{len(msgs) - 1})' if len(msgs) > 1 else ''
            emitir(f'{indent}    sim {sid} {nome!r}: {msgs[0][:90]}{extra}')
        if len(por_sim) > max_itens:
            emitir(f'{indent}    … e {len(por_sim) - max_itens} outra(s)')
    return problema


def diag_para_json(diag):
    """`diag` com listas de tuplas viram listas de objetos — o que o serviço grava no import."""
    return {
        'pecas_sem_simbologia': diag['pecas_sem_simbologia'],
        'pecas_sim_descartada': diag['pecas_sim_descartada'],
        'sim_sem_blob': diag['sim_sem_blob'],
        'sim_nao_oq3d': diag['sim_nao_oq3d'],
        'sim_ilegivel': [{'id': s, 'nome': n, 'erro': e} for s, n, e in diag['sim_ilegivel']],
        'sim_vazia': [{'id': s, 'nome': n} for s, n in diag['sim_vazia']],
        'avisos': [{'id': s, 'nome': n, 'mensagem': m} for s, n, m in diag['avisos']],
    }
