"""
Tests para scripts/build.py — funções puras.

Cobre _assert_safe_slug(), slugify(), find_aq_product(), build_catalog()
e scan_input(). Não testa funções que dependem de filesystem externo
(render_html, build_preview, build_zip) — essas exigem templates e dados reais.
"""

import copy
import pytest

from build import (
    _assert_safe_slug,
    slugify,
    find_aq_product,
    build_catalog,
    scan_input,
)


# ── _assert_safe_slug ─────────────────────────────────────────────────────────

class TestAssertSafeSlug:
    @pytest.mark.parametrize('value', [
        'bombas-incendio',
        'cam-w10',
        'cam_w10',
        'a',
        'a1',
        'abc123',
        'serie-rows',
        'catalogo-grid',
    ])
    def test_valid_slugs_pass(self, value):
        _assert_safe_slug(value, 'test')  # não deve levantar

    @pytest.mark.parametrize('value', [
        '',                  # vazio
        '-abc',              # começa com hífen
        'ABC',               # letras maiúsculas
        'with spaces',       # espaço
        'with/slash',        # barra
        '../evil',           # path traversal
        'has.dot',           # ponto
        'has@special',       # caractere especial
    ])
    def test_invalid_slugs_raise_value_error(self, value):
        with pytest.raises(ValueError):
            _assert_safe_slug(value, 'test')

    def test_field_name_appears_in_error_message(self):
        with pytest.raises(ValueError, match='meu-campo'):
            _assert_safe_slug('../evil', 'meu-campo')


# ── slugify ───────────────────────────────────────────────────────────────────

class TestSlugify:
    def test_ascii_lowercase(self):
        assert slugify('bombas') == 'bombas'

    def test_uppercase_lowercased(self):
        assert slugify('Bombas') == 'bombas'

    def test_spaces_become_hyphens(self):
        assert slugify('bombas de incendio') == 'bombas-de-incendio'

    def test_portuguese_cedilla(self):
        """
        'Junção' → 'juncao'. Bug documentado nas specs: sem NFKD,
        'ç' não é representável em ASCII e vira '-', gerando 'jun-o'.
        """
        assert slugify('Junção') == 'juncao'

    def test_portuguese_tilde(self):
        assert slugify('Câmara') == 'camara'

    def test_portuguese_acute(self):
        assert slugify('Incêndio') == 'incendio'

    def test_full_portuguese_phrase(self):
        assert slugify('Bombas de Incêndio') == 'bombas-de-incendio'

    def test_hyphens_in_input_preserved(self):
        assert slugify('CAM-W10') == 'cam-w10'

    def test_multiple_spaces_single_hyphen(self):
        assert slugify('a  b') == 'a-b'

    def test_leading_trailing_stripped(self):
        assert slugify('  bombas  ') == 'bombas'

    def test_alphanumeric_preserved(self):
        assert slugify('CAM-W10 1CV') == 'cam-w10-1cv'

    def test_empty_string(self):
        assert slugify('') == ''


# ── find_aq_product ───────────────────────────────────────────────────────────

class TestFindAqProduct:
    PRODUCT_MAP = {
        'CAM-W10': {
            'serie': 'CAM-W10',
            'pecas': [{'id': 1, 'nome': '1CV T 220V', 'conexoes': '', 'specs': {}, 'curva_pts': None}],
        },
        'TJM': {
            'serie': 'TJM',
            'pecas': [{'id': 2, 'nome': '50CV T 220V', 'conexoes': '', 'specs': {}, 'curva_pts': None}],
        },
    }

    def test_exact_prefix_match(self):
        result = find_aq_product('cam-w10', self.PRODUCT_MAP)
        assert result is not None
        nome_gp, peca = result
        assert nome_gp == 'CAM-W10'
        assert peca['id'] == 1

    def test_tjm_match(self):
        result = find_aq_product('tjm', self.PRODUCT_MAP)
        assert result is not None
        nome_gp, _ = result
        assert nome_gp == 'TJM'

    def test_no_match_returns_none(self):
        result = find_aq_product('xyz-unknown', self.PRODUCT_MAP)
        assert result is None

    def test_empty_product_map_returns_none(self):
        result = find_aq_product('cam-w10', {})
        assert result is None

    def test_returns_first_peca_of_group(self):
        """Deve retornar a primeira peça do grupo correspondente."""
        pm = {
            'CAM-W10': {
                'serie': 'CAM-W10',
                'pecas': [
                    {'id': 1, 'nome': 'Peca A', 'conexoes': '', 'specs': {}, 'curva_pts': None},
                    {'id': 2, 'nome': 'Peca B', 'conexoes': '', 'specs': {}, 'curva_pts': None},
                ],
            }
        }
        _, peca = find_aq_product('cam-w10', pm)
        assert peca['id'] == 1  # primeira peça


# ── build_catalog ─────────────────────────────────────────────────────────────

PRODUCT_MAP_WITH_CURVE = {
    'CAM-W10': {
        'serie': 'CAM-W10',
        'pecas': [{
            'id': 1,
            'nome': '1CV T 220/380V',
            'conexoes': '1.5" x 1.5"',
            'diametro_cm': 3.8,
            'comprimento_cm': 30.0,
            'altura_cm': 20.0,
            'largura_cm': 20.0,
            'specs': {'Tensao': 'Trifasico 220/380V'},
            'curva_pts': [[0, 30, 1.0, 55], [3, 25, 1.1, 60]],
        }]
    }
}

BASE_CONFIG = {
    'slug': 'bombas-teste',
    'titulo': 'Bombas de Teste',
    'fabricante': 'TestFab',
    'descricao': 'Desc curta',
    'layout': 'series-rows',
    'file_map': {'CAM-W10.IFC': 'cam-w10'},
    'products_override': [],
}


class TestBuildCatalog:
    def test_basic_structure(self):
        catalog = build_catalog(BASE_CONFIG, PRODUCT_MAP_WITH_CURVE, {'cam-w10'})

        assert catalog['slug'] == 'bombas-teste'
        assert catalog['titulo'] == 'Bombas de Teste'
        assert catalog['fabricante'] == 'TestFab'
        assert catalog['layout'] == 'series-rows'
        assert 'produtos' in catalog
        assert 'filtros' in catalog
        assert 'tem_curva_qh' in catalog

    def test_produto_fields(self):
        catalog = build_catalog(BASE_CONFIG, PRODUCT_MAP_WITH_CURVE, {'cam-w10'})
        assert len(catalog['produtos']) == 1
        p = catalog['produtos'][0]

        assert p['id'] == 'cam-w10'
        assert p['nome'] == '1CV T 220/380V'
        assert p['geo'] == 'cam-w10.json'

    def test_tem_curva_qh_true_when_any_product_has_curve(self):
        catalog = build_catalog(BASE_CONFIG, PRODUCT_MAP_WITH_CURVE, {'cam-w10'})
        assert catalog['tem_curva_qh'] is True

    def test_tem_curva_qh_false_when_no_curves(self):
        """
        Catálogos sem curva Q-H (ex: conexões PVC) não devem mostrar a seção
        de curva no modal — 'Curva não disponível' vazio em todo produto
        é confuso quando o conceito não se aplica ao tipo de peça.
        """
        pm = copy.deepcopy(PRODUCT_MAP_WITH_CURVE)
        pm['CAM-W10']['pecas'][0]['curva_pts'] = None
        catalog = build_catalog(BASE_CONFIG, pm, {'cam-w10'})
        assert catalog['tem_curva_qh'] is False

    def test_filtros_sorted_alphabetically(self):
        pm = {
            'TJM': {'serie': 'TJM', 'pecas': [{'id': 2, 'nome': 'X', 'conexoes': '', 'specs': {}, 'curva_pts': None}]},
            'CAM-W': {'serie': 'CAM-W', 'pecas': [{'id': 1, 'nome': 'Y', 'conexoes': '', 'specs': {}, 'curva_pts': None}]},
        }
        config = {**BASE_CONFIG, 'file_map': {'TJM.IFC': 'tjm', 'CAM-W.IFC': 'cam-w'}}
        catalog = build_catalog(config, pm, {'tjm', 'cam-w'})
        assert catalog['filtros'] == sorted(catalog['filtros'])

    def test_skips_products_missing_geo(self):
        """Produto sem geo JSON correspondente deve ser omitido do catálogo."""
        catalog = build_catalog(BASE_CONFIG, PRODUCT_MAP_WITH_CURVE, set())  # geo_files vazio
        assert len(catalog['produtos']) == 0

    def test_uses_override_instead_of_aq(self):
        """products_override deve ser usado diretamente, sem passar pelo product_map."""
        config = {
            **BASE_CONFIG,
            'file_map': {'CAM-89.IFC': 'cam-89'},
            'products_override': [{
                'id': 'cam-89',
                'nome': 'CAM 89-62 TJM 50CV',
                'serie': 'TJM',
                'curva': None,
                'specs': {},
            }],
        }
        catalog = build_catalog(config, {}, {'cam-89'})  # product_map vazio — deve usar override
        assert len(catalog['produtos']) == 1
        assert catalog['produtos'][0]['nome'] == 'CAM 89-62 TJM 50CV'
        assert catalog['produtos'][0]['geo'] == 'cam-89.json'

    def test_tem_curva_qh_with_override_no_curve(self):
        config = {
            **BASE_CONFIG,
            'file_map': {'CAM-89.IFC': 'cam-89'},
            'products_override': [{'id': 'cam-89', 'nome': 'X', 'serie': 'TJM', 'curva': None, 'specs': {}}],
        }
        catalog = build_catalog(config, {}, {'cam-89'})
        assert catalog['tem_curva_qh'] is False

    def test_stub_product_when_not_in_aq(self):
        """Produto no IFC mas ausente no .aq deve gerar stub mínimo (não abortar)."""
        config = {**BASE_CONFIG, 'file_map': {'UNKNOWN.IFC': 'unknown'}}
        catalog = build_catalog(config, {}, {'unknown'})  # product_map vazio → stub
        assert len(catalog['produtos']) == 1
        p = catalog['produtos'][0]
        assert p['id'] == 'unknown'
        assert p['geo'] == 'unknown.json'
        assert p['curva'] is None


# ── scan_input ────────────────────────────────────────────────────────────────

class TestScanInput:
    def test_flat_mode_detects_ifc_files(self, tmp_path):
        (tmp_path / 'pump-a.ifc').touch()
        (tmp_path / 'pump-b.IFC').touch()
        (tmp_path / 'readme.txt').touch()

        entries, mode, aq_paths = scan_input(str(tmp_path))

        assert mode == 'flat'
        assert len(entries) == 2
        slugs = [e[1] for e in entries]
        assert 'pump-a' in slugs
        assert 'pump-b' in slugs

    def test_flat_mode_slug_from_filename(self, tmp_path):
        (tmp_path / 'CAM-W10-1CV.ifc').touch()
        entries, _, _ = scan_input(str(tmp_path))
        assert len(entries) == 1
        assert entries[0][1] == 'cam-w10-1cv'

    def test_subdir_mode_when_no_flat_ifcs(self, tmp_path):
        cat_dir = tmp_path / 'Categoria-A'
        cat_dir.mkdir()
        (cat_dir / 'variant01.ifc').touch()
        (cat_dir / 'variant02.ifc').touch()

        entries, mode, aq_paths = scan_input(str(tmp_path))

        assert mode == 'subdir'
        assert len(entries) == 1
        assert entries[0][1] == 'categoria-a'   # slugify do nome da pasta

    def test_subdir_mode_first_ifc_is_representative(self, tmp_path):
        """No modo subdir, entries[0][0] é o caminho relativo do 1º IFC."""
        cat_dir = tmp_path / 'Valvulas'
        cat_dir.mkdir()
        (cat_dir / 'v01.ifc').touch()
        (cat_dir / 'v02.ifc').touch()

        entries, mode, _ = scan_input(str(tmp_path))

        assert mode == 'subdir'
        first_ifc = entries[0][0]  # caminho relativo
        assert first_ifc.endswith('v01.ifc')

    def test_flat_mode_finds_aq_files(self, tmp_path):
        (tmp_path / 'pump.ifc').touch()
        (tmp_path / 'library.aq').touch()

        _, _, aq_paths = scan_input(str(tmp_path))

        assert len(aq_paths) == 1
        assert aq_paths[0].endswith('library.aq')

    def test_empty_directory_returns_empty(self, tmp_path):
        entries, mode, aq_paths = scan_input(str(tmp_path))
        assert entries == []
        assert mode == 'flat'
        assert aq_paths == []

    def test_nonexistent_directory_returns_empty(self, tmp_path):
        entries, mode, aq_paths = scan_input(str(tmp_path / 'nao-existe'))
        assert entries == []
        assert mode == 'flat'
        assert aq_paths == []

    def test_subdir_mode_count_in_label(self, tmp_path):
        """Label do subdir deve informar quantos IFCs a pasta contém."""
        cat_dir = tmp_path / 'Conexoes'
        cat_dir.mkdir()
        (cat_dir / 'v01.ifc').touch()
        (cat_dir / 'v02.ifc').touch()
        (cat_dir / 'v03.ifc').touch()

        entries, _, _ = scan_input(str(tmp_path))
        label = entries[0][2]  # 3º elemento: label de exibição
        assert '3' in label
