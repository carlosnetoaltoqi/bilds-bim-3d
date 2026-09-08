"""Malhas sintéticas para os testes de geometria — sem fixture, roda em qualquer máquina.

A forma que interessa é a **ponta de tubo**: um anel de triângulos coplanares fechando um
cilindro de parede fina, que é como a malha de fabricante marca um bocal
(`bim_pipeline.geometria.bocais`). O `cilindro_tampado` é o contra-exemplo: ponta fechada
por disco cheio, que não é bocal.
"""
import numpy as np


def _anel(z, n, r_int, r_ext):
    """2n vértices do anel no plano z: primeiro o círculo interno, depois o externo."""
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    dentro = np.stack([r_int * np.cos(a), r_int * np.sin(a), np.full(n, z)], axis=1)
    fora = np.stack([r_ext * np.cos(a), r_ext * np.sin(a), np.full(n, z)], axis=1)
    return np.concatenate([dentro, fora])


def _faixa(base_a, base_b, n, inverte=False):
    """Triângulos ligando dois círculos de n vértices, em bases distintas."""
    t = []
    for i in range(n):
        j = (i + 1) % n
        t.append([base_a + i, base_a + j, base_b + i])
        t.append([base_a + j, base_b + j, base_b + i])
    return [tri[::-1] for tri in t] if inverte else t


def tubo(r_int=0.9, r_ext=1.0, comprimento=6.0, n=24, planos_extra=(), inverte=False):
    """Tubo de parede fina fechado por face anelar nas duas pontas.

    `planos_extra` acrescenta anéis coplanares no meio do tubo — o friso/degrau que
    aparece nas nativas e que não é bocal.
    """
    zs = [0.0] + sorted(planos_extra) + [comprimento]
    V = np.concatenate([_anel(z, n, r_int, r_ext) for z in zs])
    F = []
    for k in range(len(zs) - 1):
        a, b = k * 2 * n, (k + 1) * 2 * n
        F += _faixa(a, b, n, inverte)                       # parede interna
        F += _faixa(a + n, b + n, n, not inverte)           # parede externa
    for k, _ in enumerate(zs):                              # face anelar de cada plano:
        base = k * 2 * n                                    # as pontas e os frisos do meio
        F += _faixa(base, base + n, n, inverte)
    return [(V, np.array(F, dtype=np.int64), (200, 200, 200, 255))]


def cilindro_tampado(raio=1.0, comprimento=6.0, n=24):
    """Cilindro maciço: as pontas são tampas cheias, sem anel."""
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    base = np.stack([raio * np.cos(a), raio * np.sin(a), np.zeros(n)], axis=1)
    topo = base + [0, 0, comprimento]
    centros = np.array([[0, 0, 0.0], [0, 0, comprimento]])
    V = np.concatenate([base, topo, centros])
    F = _faixa(0, n, n)
    for i in range(n):
        j = (i + 1) % n
        F.append([2 * n, i, j])
        F.append([2 * n + 1, n + j, n + i])
    return [(V, np.array(F, dtype=np.int64), (200, 200, 200, 255))]
