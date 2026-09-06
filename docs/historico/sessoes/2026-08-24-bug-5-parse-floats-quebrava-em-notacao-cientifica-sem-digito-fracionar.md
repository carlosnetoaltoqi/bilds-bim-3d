# 2026-08-24 — Bug 5: parse_floats quebrava em notação científica sem dígito fracionário (commit 8d0d8ec)

**Data:** 2026-08-24 · Registro **extraído do `CLAUDE.md`** em 2026-09-04 (S7.8, I22) — esta
sessão não tinha arquivo próprio; o texto abaixo é o que havia lá, sem alteração.

---

Coordenadas IFC exportadas pelo CATIA usam formato `-4.E-16` e `1.E+00` — notação científica
sem dígitos entre o ponto decimal e o expoente. A regex `[0-9]*\.?[0-9]+` exigia ao menos
um dígito após o ponto, então `-4.E-16` era extraído como dois números: `-4` e `-16`.

Resultado: sub-peças com esse valor de coordenada (INTERMEDIARIA, MOTOR) apareciam
deslocadas exatamente em 16m do corpo da bomba.

Bombas afetadas: 105-50 TJM, 51-30W TJM, 109_40 TJM.

```python
# Regex corrigida — aceita ponto sem dígito fracionário
r'[-+]?(?:[0-9]+\.?[0-9]*|[0-9]*\.[0-9]+)(?:[eE][-+]?[0-9]+)?'
```
