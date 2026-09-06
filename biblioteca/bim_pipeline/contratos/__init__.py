"""
bim_pipeline.contratos — os JSON Schema deste diretório e a validação (opcional) contra eles (ADR-015).

A biblioteca não valida em produção (custo e dependência); valida em teste, para provar que o que
emite bate com o contrato que os serviços leem. `jsonschema` é dependência de dev.
"""
import json
import os

AQUI = os.path.dirname(os.path.abspath(__file__))
NOMES = ('catalogo', 'geometria', 'manifesto-catalogo-aq', 'resumo-miniaturas', 'info-plugin')


def carregar(nome):
    """O schema `nome` como dict."""
    with open(os.path.join(AQUI, f'{nome}.schema.json'), encoding='utf-8') as f:
        return json.load(f)


def validar(nome, obj):
    """Lança `jsonschema.ValidationError` se `obj` não segue o contrato `nome`."""
    import jsonschema
    jsonschema.Draft202012Validator(carregar(nome)).validate(obj)
    return obj
