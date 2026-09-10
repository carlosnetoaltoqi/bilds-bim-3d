"""
As sete disciplinas do Builder existem em três arquivos. Este teste é o que impede que
divirjam.

A duplicata é deliberada e está explicada em cada arquivo: o Python é quem **grava** o `.aq`
(fonte da verdade), `pacotes/base` é o que os DTOs dos serviços validam, e o `web` tem a sua
cópia porque não depende de `@bim/base` — importar aquele pacote arrastaria o bootstrap do Nest
para dentro do bundle do Next e furaria a regra de porte de `docs/arquitetura.md` §4.

Uma lista fora de sincronia não quebra nada visivelmente: o formulário simplesmente deixa de
oferecer uma disciplina, ou oferece uma que o escritor recusa. É exatamente o tipo de defeito
silencioso que o ADR-024 existe para acabar.
"""
import re

from conftest import ROOT

from bim_pipeline.aq import cadastro

BASE_TS = ROOT / 'pacotes' / 'base' / 'src' / 'disciplinas.ts'
WEB_TS = ROOT / 'web' / 'src' / 'disciplinas.ts'

SLUG_ROTULO = re.compile(r"\{\s*slug:\s*'([a-z]+)',\s*rotulo:\s*'([^']+)'")


def _do_typescript(caminho):
    return SLUG_ROTULO.findall(caminho.read_text(encoding='utf-8'))


def test_as_tres_listas_de_disciplina_batem():
    do_python = [(slug, cfg['rotulo']) for slug, cfg in cadastro.DISCIPLINAS.items()]
    assert _do_typescript(BASE_TS) == do_python, (
        f'{BASE_TS.relative_to(ROOT)} divergiu de cadastro.DISCIPLINAS')
    assert _do_typescript(WEB_TS) == do_python, (
        f'{WEB_TS.relative_to(ROOT)} divergiu de cadastro.DISCIPLINAS')


def test_a_mascara_do_typescript_bate_com_a_do_python():
    """`pacotes/base` também traz a máscara, que é o valor gravado em PROJETO_APLICACAO."""
    mascaras = dict(zip(
        [s for s, _ in _do_typescript(BASE_TS)],
        [int(m) for m in re.findall(r'mascara:\s*(\d+)', BASE_TS.read_text(encoding='utf-8'))]))
    assert mascaras == {slug: cfg['mascara'] for slug, cfg in cadastro.DISCIPLINAS.items()}


def test_toda_disciplina_tem_vocabulario_e_generico():
    """Sem vocabulário a disciplina não classifica nada; sem genérico ela quebra no fallback."""
    for slug in cadastro.DISCIPLINAS:
        assert cadastro.VOCABULARIO.get(slug), f'{slug} sem vocabulário'
        assert cadastro.GENERICO_DA_DISCIPLINA.get(slug), f'{slug} sem aplicação genérica'


def test_toda_entidade_do_vocabulario_esta_na_tabela_ifc():
    """O vocabulário só pode citar entidade IFC cuja tripla foi medida no catálogo oficial."""
    for slug, regras in cadastro.VOCABULARIO.items():
        for chaves, ent, _sub, apl in regras:
            assert ent in cadastro.IFC, f'{slug}: entidade {ent} fora da tabela IFC ({chaves[0]})'
            assert 1 <= apl <= 84, f'{slug}: aplicação {apl} fora do enum ({chaves[0]})'
