"""
Tests para scripts/parse_ifc.py.

Cobre todos os utilitários STEP, álgebra matricial e parsing IFC4 —
com ênfase nos casos de borda documentados em docs/specs/leitor-ifc.md
que já quebraram em produção.
"""

import math
import pytest

from parse_ifc import (
    split_top,
    parse_floats,
    parse_ints,
    mat_identity,
    mat_mul,
    apply_matrix,
    normalize,
    cross,
    dot,
    build_entity_index,
    ifc_to_threejs,
    emit_colored,
    emit_uniform,
    build_face_color_map,
    parse_ifc_file,
)
import parse_ifc as _parse_ifc_module


# ── split_top ─────────────────────────────────────────────────────────────────

class TestSplitTop:
    def test_simple_split(self):
        assert split_top('#1,#2,#3') == ['#1', '#2', '#3']

    def test_nested_parens_not_split(self):
        assert split_top('#1,(#2,#3),#4') == ['#1', '(#2,#3)', '#4']

    def test_string_with_comma_not_split(self):
        """Vírgula dentro de string STEP não é separador de campo."""
        result = split_top("'MOTOR WEG 3,0CV T 220V',#42")
        assert result == ["'MOTOR WEG 3,0CV T 220V'", '#42']

    def test_empty_string(self):
        assert split_top('') == ['']

    def test_single_value(self):
        assert split_top('#99') == ['#99']

    def test_dollar_sign(self):
        assert split_top('$,$,#10') == ['$', '$', '#10']

    def test_deeply_nested(self):
        result = split_top('((1,2,3),(4,5,6)),#99')
        assert result == ['((1,2,3),(4,5,6))', '#99']

    def test_two_strings_with_commas(self):
        result = split_top("'A,B','C,D'")
        assert result == ["'A,B'", "'C,D'"]

    def test_strips_whitespace(self):
        result = split_top(' #1 , #2 ')
        assert result == ['#1', '#2']

    def test_nested_and_string_combined(self):
        """Combinação de parênteses e string com vírgula interna."""
        result = split_top("'Name,With,Commas',(#1,#2)")
        assert result == ["'Name,With,Commas'", '(#1,#2)']


# ── parse_floats ──────────────────────────────────────────────────────────────

class TestParseFloats:
    def test_basic_floats(self):
        assert parse_floats('1.0,2.5,-3.14') == pytest.approx([1.0, 2.5, -3.14])

    def test_integer_like(self):
        assert parse_floats('1,2,3') == pytest.approx([1.0, 2.0, 3.0])

    def test_scientific_notation(self):
        result = parse_floats('1.2E3,-4.5e-2')
        assert result == pytest.approx([1200.0, -0.045])

    def test_step_mantissa_no_digits_after_point(self):
        """
        Caso crítico documentado nas specs: STEP permite '-4.E-16' (mantissa
        sem dígitos após o ponto). Uma regex incorreta produz [-4.0, -16.0]
        em vez de [-4e-16], o que deslocava fragmentos de peça 4–16m no viewer.
        """
        result = parse_floats('-4.E-16')
        assert len(result) == 1
        assert result[0] == pytest.approx(-4e-16, abs=1e-20)

    def test_step_mantissa_positive_exponent(self):
        result = parse_floats('2.E+05')
        assert len(result) == 1
        assert result[0] == pytest.approx(2e5)

    def test_mixed_normal_and_step_mantissa(self):
        """Três floats, um deles em formato STEP problemático — deve dar 3 valores, não 4."""
        result = parse_floats('-0.07485,-4.E-16,1.2E-15')
        assert len(result) == 3
        assert result[0] == pytest.approx(-0.07485)
        assert result[1] == pytest.approx(-4e-16, abs=1e-20)
        assert result[2] == pytest.approx(1.2e-15, abs=1e-20)

    def test_leading_dot(self):
        assert parse_floats('.5') == pytest.approx([0.5])

    def test_negative_values(self):
        assert parse_floats('-1.5,-2.5') == pytest.approx([-1.5, -2.5])

    def test_ifc_coordinate_tuple(self):
        """Formato típico de coordenada IFC: '(1.,0.,0.)'."""
        result = parse_floats('(1.,0.,0.)')
        assert result == pytest.approx([1.0, 0.0, 0.0])


# ── parse_ints ────────────────────────────────────────────────────────────────

class TestParseInts:
    def test_basic(self):
        assert parse_ints('1,2,3') == [1, 2, 3]

    def test_from_face_index(self):
        assert parse_ints('(1,2,3)') == [1, 2, 3]

    def test_ignores_non_digits(self):
        assert parse_ints('abc 42 xyz 7') == [42, 7]


# ── Álgebra matricial ─────────────────────────────────────────────────────────

class TestMatrixAlgebra:
    def test_identity_shape(self):
        I = mat_identity()
        assert len(I) == 16
        for r in range(4):
            for c in range(4):
                assert I[r * 4 + c] == (1.0 if r == c else 0.0)

    def test_mat_mul_with_identity(self):
        I = mat_identity()
        A = [float(i) for i in range(16)]
        assert mat_mul(I, A) == pytest.approx(A)
        assert mat_mul(A, I) == pytest.approx(A)

    def test_translation_matrices_compose(self):
        """Duas translações compostas devem somar as translações."""
        def make_translation(tx, ty, tz):
            M = mat_identity()
            M[3], M[7], M[11] = tx, ty, tz
            return M

        T1 = make_translation(1, 2, 3)
        T2 = make_translation(4, 5, 6)
        T3 = mat_mul(T1, T2)
        result = apply_matrix(T3, [0, 0, 0])
        assert result == pytest.approx([5.0, 7.0, 9.0])

    def test_apply_matrix_identity(self):
        I = mat_identity()
        p = [3.0, 5.0, 7.0]
        assert apply_matrix(I, p) == pytest.approx(p)

    def test_apply_matrix_translation(self):
        M = mat_identity()
        M[3], M[7], M[11] = 10.0, 20.0, 30.0
        result = apply_matrix(M, [1.0, 2.0, 3.0])
        assert result == pytest.approx([11.0, 22.0, 33.0])

    def test_normalize_axis_vector(self):
        v = [3.0, 0.0, 0.0]
        assert normalize(v) == pytest.approx([1.0, 0.0, 0.0])

    def test_normalize_diagonal_has_unit_length(self):
        n = normalize([1.0, 1.0, 1.0])
        length = math.sqrt(sum(c ** 2 for c in n))
        assert length == pytest.approx(1.0)

    def test_cross_product_orthogonal(self):
        assert cross([1, 0, 0], [0, 1, 0]) == pytest.approx([0, 0, 1])  # x × y = z
        assert cross([0, 1, 0], [0, 0, 1]) == pytest.approx([1, 0, 0])  # y × z = x

    def test_dot_product(self):
        assert dot([1, 0, 0], [1, 0, 0]) == pytest.approx(1.0)
        assert dot([1, 0, 0], [0, 1, 0]) == pytest.approx(0.0)
        assert dot([1, 2, 3], [4, 5, 6]) == pytest.approx(32.0)


# ── build_entity_index ────────────────────────────────────────────────────────

class TestBuildEntityIndex:
    def test_basic_entity_parsed(self):
        content = "#42 = IFCLOCALPLACEMENT(#27,#46);"
        idx = build_entity_index(content)
        assert 42 in idx
        etype, args = idx[42]
        assert etype == 'IFCLOCALPLACEMENT'
        assert args == '#27,#46'

    def test_args_do_not_include_closing_paren_or_semicolon(self):
        """
        Bug crítico: regex com ')' opcional capturava ') ;' nos args.
        Isso fazia split_top('#27,#46) ;') retornar ['#27', '#46) ;'],
        e int('#46) ;') levantava ValueError — a entidade era ignorada.
        """
        content = "#43 = IFCLOCALPLACEMENT(#27,#46);"
        idx = build_entity_index(content)
        _, args = idx[43]
        assert ')' not in args
        assert ';' not in args

    def test_multiple_entities_on_separate_lines(self):
        content = "\n".join([
            "#1 = IFCBUILDINGELEMENTPROXY('G',#2,'Name',$,'T',#10,#20,$,$);",
            "#2 = IFCOWNERHISTORY(#3,$,'ADDED',$,$,$,$,0);",
            "#10 = IFCLOCALPLACEMENT($,#11);",
        ])
        idx = build_entity_index(content)
        assert 1 in idx
        assert 2 in idx
        assert 10 in idx

    def test_non_entity_lines_ignored(self):
        content = "ISO-10303-21;\nHEADER;\n/* comment */\n#1 = IFCTYPE(#2);"
        idx = build_entity_index(content)
        assert len(idx) == 1
        assert 1 in idx

    def test_nested_parens_in_args_preserved(self):
        content = "#31 = IFCCARTESIANPOINTLIST3D(((0.,0.,0.),(1.,0.,0.)));"
        idx = build_entity_index(content)
        assert 31 in idx
        _, args = idx[31]
        assert '0.,0.,0.' in args

    def test_entity_type_captured(self):
        content = "#99 = IFCTRIANGULATEDFACESET(#31,$,$,((1,2,3)),$);"
        idx = build_entity_index(content)
        etype, _ = idx[99]
        assert etype == 'IFCTRIANGULATEDFACESET'


# ── ifc_to_threejs ────────────────────────────────────────────────────────────

class TestIfcToThreejs:
    def test_z_up_to_y_up(self):
        """IFC Z-up → Three.js Y-up: x stays, IFC-z → THREE-y, IFC-y inverts → THREE-z."""
        assert ifc_to_threejs([1.0, 2.0, 3.0]) == pytest.approx([1.0, 3.0, -2.0])

    def test_origin_unchanged(self):
        assert ifc_to_threejs([0.0, 0.0, 0.0]) == pytest.approx([0.0, 0.0, 0.0])

    def test_ifc_y_becomes_negative_three_z(self):
        assert ifc_to_threejs([0.0, 1.0, 0.0]) == pytest.approx([0.0, 0.0, -1.0])

    def test_ifc_z_becomes_three_y(self):
        assert ifc_to_threejs([0.0, 0.0, 1.0]) == pytest.approx([0.0, 1.0, 0.0])


# ── emit_colored ──────────────────────────────────────────────────────────────

class TestEmitColored:
    def test_single_triangle_color_applied_to_all_three_verts(self):
        coord_list = [[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]]
        face_indices = [(1, 2, 3)]
        M = mat_identity()
        colours = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
        colour_indices = [1]  # tri 0 → cor 0 (vermelho)
        pos_out, col_out = [], []

        emit_colored(coord_list, face_indices, M, colours, colour_indices, pos_out, col_out)

        assert len(pos_out) == 9   # 3 verts × 3 floats
        assert len(col_out) == 9
        assert col_out[0:3] == pytest.approx([1.0, 0.0, 0.0])
        assert col_out[3:6] == pytest.approx([1.0, 0.0, 0.0])
        assert col_out[6:9] == pytest.approx([1.0, 0.0, 0.0])

    def test_two_triangles_get_different_colors(self):
        coord_list = [[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [0., 0., 1.]]
        face_indices = [(1, 2, 3), (1, 3, 4)]
        M = mat_identity()
        colours = [[1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]
        colour_indices = [1, 2]
        pos_out, col_out = [], []

        emit_colored(coord_list, face_indices, M, colours, colour_indices, pos_out, col_out)

        assert len(col_out) == 18   # 6 verts × 3
        assert col_out[0:3] == pytest.approx([1.0, 0.0, 0.0])   # tri 0: vermelho
        assert col_out[9:12] == pytest.approx([0.0, 0.0, 1.0])  # tri 1: azul

    def test_colour_index_out_of_range_uses_fallback_grey(self):
        """Índice fora do range da paleta → cor fallback de aço."""
        coord_list = [[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]]
        face_indices = [(1, 2, 3)]
        M = mat_identity()
        colours = [[1.0, 0.0, 0.0]]
        colour_indices = [99]   # fora do range
        pos_out, col_out = [], []

        emit_colored(coord_list, face_indices, M, colours, colour_indices, pos_out, col_out)

        assert col_out[0:3] == pytest.approx([0.72, 0.75, 0.80])

    def test_vertices_expanded_no_sharing(self):
        """emit_colored NÃO deve compartilhar vértices — cada triângulo tem 3 verts próprios."""
        coord_list = [[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]]
        face_indices = [(1, 2, 3)]
        M = mat_identity()
        colours = [[0.5, 0.5, 0.5]]
        colour_indices = [1]
        pos_out, col_out = [], []

        emit_colored(coord_list, face_indices, M, colours, colour_indices, pos_out, col_out)

        # Geometria expandida: sem idx, 1 triângulo = 3 verts individuais
        assert len(pos_out) == 9


# ── emit_uniform ──────────────────────────────────────────────────────────────

class TestEmitUniform:
    def test_builds_shared_vertex_index(self):
        coord_list = [[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]]
        face_indices = [(1, 2, 3)]
        M = mat_identity()
        default_rgb = [0.72, 0.75, 0.80]
        pos_out, col_out, idx_out = [], [], []

        emit_uniform(coord_list, face_indices, M, default_rgb, pos_out, col_out, idx_out)

        assert len(pos_out) == 9
        assert idx_out == [0, 1, 2]
        assert col_out[0:3] == pytest.approx([0.72, 0.75, 0.80])

    def test_base_offset_applied(self):
        """Quando pos_out já tem vértices, os novos índices devem usar base correto."""
        coord_list = [[5., 0., 0.], [6., 0., 0.], [5., 1., 0.]]
        face_indices = [(1, 2, 3)]
        M = mat_identity()
        pos_out = [0., 0., 0., 1., 0., 0.]  # 2 verts pré-existentes
        col_out = [0., 0., 0., 0., 0., 0.]
        idx_out = []

        emit_uniform(coord_list, face_indices, M, [0., 0., 0.], pos_out, col_out, idx_out)

        # base = 2, então índices devem ser [2, 3, 4]
        assert idx_out == [2, 3, 4]


# ── build_face_color_map ──────────────────────────────────────────────────────

class TestBuildFaceColorMap:
    def test_extracts_two_colour_palette(self):
        content = (
            "#33 = IFCCOLOURRGBLIST(((0.835,0.071,0.071),(1.,1.,1.)));\n"
            "#32 = IFCINDEXEDCOLOURMAP(#31, 1., #33,(1,1,2,2));\n"
            "#31 = IFCTRIANGULATEDFACESET(#40,$,$,((1,2,3),(1,3,4)),$);\n"
        )
        idx = build_entity_index(content)
        color_map = build_face_color_map(content, idx)

        assert 31 in color_map
        colours, indices = color_map[31]
        assert len(colours) == 2
        assert colours[0] == pytest.approx([0.835, 0.071, 0.071])
        assert colours[1] == pytest.approx([1.0, 1.0, 1.0])
        assert indices == [1, 1, 2, 2]

    def test_no_colour_map_when_absent(self):
        content = "#30 = IFCTRIANGULATEDFACESET(#31,$,$,((1,2,3)),$);\n"
        idx = build_entity_index(content)
        color_map = build_face_color_map(content, idx)
        assert color_map == {}

    def test_missing_colour_list_entity_skipped(self):
        """IFCCOLOURRGBLIST com ID ausente do índice deve ser ignorado silenciosamente."""
        content = "#32 = IFCINDEXEDCOLOURMAP(#31, 1., #999,(1,2));\n"
        idx = build_entity_index(content)
        color_map = build_face_color_map(content, idx)
        assert color_map == {}

    def test_three_colour_palette(self):
        """Paleta com 3 cores — ex: peça com corpo, logo e conector."""
        content = (
            "#50 = IFCCOLOURRGBLIST(((1.,0.,0.),(0.,1.,0.),(0.,0.,1.)));\n"
            "#49 = IFCINDEXEDCOLOURMAP(#48, 1., #50,(1,2,3,1));\n"
        )
        idx = build_entity_index(content)
        color_map = build_face_color_map(content, idx)
        colours, indices = color_map[48]
        assert len(colours) == 3
        assert indices == [1, 2, 3, 1]


# ── parse_ifc_file — integração ───────────────────────────────────────────────

# IFC mínimo com 1 triângulo, LP com translação de +1 no eixo X
MINIMAL_IFC = """\
#1 = IFCBUILDINGELEMENTPROXY('G1',#99,'Pump',$,'PType',#10,#20,$,$);
#10 = IFCLOCALPLACEMENT($,#11);
#11 = IFCAXIS2PLACEMENT3D(#12,$,$);
#12 = IFCCARTESIANPOINT((1.,0.,0.));
#20 = IFCPRODUCTDEFINITIONSHAPE($,$,(#21));
#21 = IFCSHAPEREPRESENTATION(#100,'Body','Tessellation',(#30));
#30 = IFCTRIANGULATEDFACESET(#31,$,$,((1,2,3)),$);
#31 = IFCCARTESIANPOINTLIST3D(((0.,0.,0.),(1.,0.,0.),(0.,1.,0.)));
"""

# IFC com IFCINDEXEDCOLOURMAP (geometria colorida, expandida)
COLORED_IFC = """\
#1 = IFCBUILDINGELEMENTPROXY('G1',#99,'Pump',$,'PType',#10,#20,$,$);
#10 = IFCLOCALPLACEMENT($,#11);
#11 = IFCAXIS2PLACEMENT3D(#12,$,$);
#12 = IFCCARTESIANPOINT((0.,0.,0.));
#20 = IFCPRODUCTDEFINITIONSHAPE($,$,(#21));
#21 = IFCSHAPEREPRESENTATION(#100,'Body','Tessellation',(#30));
#30 = IFCTRIANGULATEDFACESET(#31,$,$,((1,2,3)),$);
#31 = IFCCARTESIANPOINTLIST3D(((0.,0.,0.),(1.,0.,0.),(0.,1.,0.)));
#33 = IFCCOLOURRGBLIST(((1.,0.,0.)));
#32 = IFCINDEXEDCOLOURMAP(#30, 1., #33,(1));
"""


class TestParseIfcFile:
    def test_basic_geometry_structure(self, tmp_path):
        ifc_file = tmp_path / 'test.ifc'
        ifc_file.write_text(MINIMAL_IFC)
        result = parse_ifc_file(str(ifc_file))

        assert 'pos' in result
        assert 'col' in result
        n_verts = len(result['pos']) // 3
        assert n_verts == 3  # 1 triângulo = 3 verts compartilhados (geometria uniforme)

    def test_lp_translation_applied_to_vertices(self, tmp_path):
        """LP com translação (1,0,0) deve offset todos os vértices."""
        ifc_file = tmp_path / 'test.ifc'
        ifc_file.write_text(MINIMAL_IFC)
        result = parse_ifc_file(str(ifc_file))

        # Vértice 0: (0,0,0) IFC local + LP (1,0,0) = (1,0,0) world
        # ifc_to_threejs([1,0,0]) = [1, 0, 0]
        assert result['pos'][0:3] == pytest.approx([1.0, 0.0, 0.0])

    def test_lp_translation_custom_offset(self, tmp_path):
        """LP com translação (2,3,0) deve converter coordenadas corretamente."""
        ifc = MINIMAL_IFC.replace(
            '#12 = IFCCARTESIANPOINT((1.,0.,0.));',
            '#12 = IFCCARTESIANPOINT((2.,3.,0.));',
        )
        ifc_file = tmp_path / 'offset.ifc'
        ifc_file.write_text(ifc)
        result = parse_ifc_file(str(ifc_file))

        # Vértice 0: (0,0,0) + LP(2,3,0) = (2,3,0) IFC → Three.js [2, 0, -3]
        assert result['pos'][0:3] == pytest.approx([2.0, 0.0, -3.0])

    def test_uniform_geometry_has_idx(self, tmp_path):
        """Geometria sem cores deve ter 'idx' (indexada, vértices compartilhados)."""
        ifc_file = tmp_path / 'test.ifc'
        ifc_file.write_text(MINIMAL_IFC)
        result = parse_ifc_file(str(ifc_file))

        assert 'idx' in result
        assert result['idx'] == [0, 1, 2]

    def test_colored_geometry_has_no_idx(self, tmp_path):
        """Geometria com IFCINDEXEDCOLOURMAP deve ser expandida (sem 'idx')."""
        ifc_file = tmp_path / 'colored.ifc'
        ifc_file.write_text(COLORED_IFC)
        result = parse_ifc_file(str(ifc_file))

        assert 'idx' not in result
        # 1 triângulo expandido = 3 verts independentes
        n_verts = len(result['pos']) // 3
        assert n_verts == 3

    def test_colored_geometry_color_applied(self, tmp_path):
        """Cor IFC (1,0,0) deve aparecer nos vértices."""
        ifc_file = tmp_path / 'colored.ifc'
        ifc_file.write_text(COLORED_IFC)
        result = parse_ifc_file(str(ifc_file))

        assert result['col'][0:3] == pytest.approx([1.0, 0.0, 0.0])

    def test_empty_ifc_triggers_ifcopenshell_fallback(self, tmp_path, monkeypatch):
        """IFC sem IFCTRIANGULATEDFACESET deve invocar o fallback ifcopenshell."""
        fallback_calls = []

        def mock_fallback(ifc_path, default_rgb):
            fallback_calls.append(ifc_path)
            return {'pos': [], 'col': []}

        monkeypatch.setattr(_parse_ifc_module, '_parse_via_ifcopenshell', mock_fallback)

        ifc_file = tmp_path / 'empty.ifc'
        ifc_file.write_text("# sem geometria tessellada\n")

        _parse_ifc_module.parse_ifc_file(str(ifc_file))
        assert len(fallback_calls) == 1

    def test_default_color_is_steel_grey(self, tmp_path):
        """Geometria sem cor IFC deve ter a cor padrão de aço [0.72, 0.75, 0.80]."""
        ifc_file = tmp_path / 'test.ifc'
        ifc_file.write_text(MINIMAL_IFC)
        result = parse_ifc_file(str(ifc_file))

        assert result['col'][0:3] == pytest.approx([0.72, 0.75, 0.80])
