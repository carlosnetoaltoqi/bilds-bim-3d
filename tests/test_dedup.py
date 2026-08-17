"""
Tests para scripts/dedup.py.

Cobre deduplicação de vértices expandidos → indexados, entrada já indexada,
quantização float32 e casos de borda.
"""

import pytest
from dedup import dedup


class TestDedup:
    def test_removes_duplicate_vertices(self):
        """Dois vértices idênticos devem virar um."""
        data = {
            'pos': [0., 0., 0.,  1., 0., 0.,  0., 0., 0.],
            'col': [1., 0., 0.,  0., 1., 0.,  1., 0., 0.],
        }
        result, orig, dedup_n, pct = dedup(data)
        assert orig == 3
        assert dedup_n == 2
        assert result['idx'] == [0, 1, 0]

    def test_all_unique_vertices_no_reduction(self):
        data = {
            'pos': [0., 0., 0.,  1., 0., 0.,  0., 1., 0.],
            'col': [1., 0., 0.,  0., 1., 0.,  0., 0., 1.],
        }
        result, orig, dedup_n, pct = dedup(data)
        assert orig == 3
        assert dedup_n == 3
        assert pct == pytest.approx(0.0)
        assert len(result['idx']) == 3

    def test_all_identical_vertices(self):
        data = {
            'pos': [0.5, 0.5, 0.5] * 4,
            'col': [1., 0., 0.] * 4,
        }
        result, orig, dedup_n, pct = dedup(data)
        assert orig == 4
        assert dedup_n == 1
        assert all(i == 0 for i in result['idx'])

    def test_already_indexed_input_is_expanded_then_rededuped(self):
        """Entrada com 'idx' deve ser expandida antes da dedup."""
        data = {
            'pos': [0., 0., 0.,  1., 0., 0.],
            'col': [1., 0., 0.,  0., 1., 0.],
            'idx': [0, 1, 0],  # 3 verts lógicos, 2 únicos
        }
        result, orig, dedup_n, pct = dedup(data)
        assert orig == 3   # 3 verts expandidos
        assert dedup_n == 2

    def test_without_color_uses_position_only_key(self):
        """Sem 'col', a chave de dedup é só a posição."""
        data = {
            'pos': [0., 0., 0.,  1., 0., 0.,  0., 0., 0.],
        }
        result, orig, dedup_n, pct = dedup(data)
        assert dedup_n == 2
        assert result['col'] == []

    def test_same_position_different_color_not_merged(self):
        """Mesmo ponto mas cor diferente → dois vértices distintos."""
        data = {
            'pos': [0., 0., 0.,  0., 0., 0.],
            'col': [1., 0., 0.,  0., 0., 1.],  # vermelho vs azul
        }
        result, orig, dedup_n, pct = dedup(data)
        assert dedup_n == 2

    def test_output_has_required_keys(self):
        data = {'pos': [0., 0., 0.,  1., 0., 0.,  0., 1., 0.], 'col': []}
        result, _, _, _ = dedup(data)
        assert 'pos' in result
        assert 'col' in result
        assert 'idx' in result

    def test_reduction_percentage_correct(self):
        """4 verts com 2 únicos → 50% de redução."""
        data = {
            'pos': [0., 0., 0.,  1., 0., 0.,  0., 0., 0.,  1., 0., 0.],
            'col': [1., 0., 0.,  0., 1., 0.,  1., 0., 0.,  0., 1., 0.],
        }
        _, orig, dedup_n, pct = dedup(data)
        assert orig == 4
        assert dedup_n == 2
        assert pct == pytest.approx(50.0)

    def test_float32_quantization_merges_near_equal(self):
        """Vértices que diferem apenas além da precisão float32 devem ser fundidos."""
        import struct
        # Valor e seu representante float32 mais próximo
        v = 1.0000001  # além da precisão float32 em relação a 1.0
        v_f32 = struct.unpack('f', struct.pack('f', v))[0]

        data = {
            'pos': [1.0, 0., 0.,  v, 0., 0.],
            'col': [1., 0., 0.,   1., 0., 0.],
        }
        _, _, dedup_n, _ = dedup(data)
        # Se v == v_f32 após quantização, os dois verts são fundidos
        if v_f32 == struct.unpack('f', struct.pack('f', 1.0))[0]:
            assert dedup_n == 1
        else:
            assert dedup_n == 2  # não fundidos se realmente distintos em float32

    def test_index_values_within_range(self):
        """Todos os índices devem referenciar verts existentes."""
        data = {
            'pos': [0., 0., 0.,  1., 0., 0.,  0., 1., 0.,
                    0., 0., 0.,  1., 0., 0.],
            'col': [1., 0., 0.] * 5,
        }
        result, _, dedup_n, _ = dedup(data)
        for i in result['idx']:
            assert 0 <= i < dedup_n
