"""`pacotes/base/src/upload.ts`: o nome do arquivo enviado volta a UTF-8 (`nomeOriginalUtf8`), com
guarda de ida e volta. Roda `tests/paridade/upload_nome.mts` no Node; precisa das dependências do
workspace (`multer`), por isso vive na camada de serviços. Marcador `paridade`."""
import json
import subprocess

import pytest

from conftest import ROOT, node_para_ts

pytestmark = pytest.mark.paridade


def test_nome_do_arquivo_enviado_volta_a_utf8():
    """O multer lê o `filename` do multipart como latin1 e não conhece `defParamCharset`; `upload.ts`
    refaz a decodificação com guarda de ida e volta."""
    node = node_para_ts()
    if not node:
        pytest.skip('precisa de Node >= 22')
    proc = subprocess.run([node, '--no-warnings', '--experimental-strip-types', str(ROOT / 'tests' / 'paridade' / 'upload_nome.mts')],
                          capture_output=True, text=True, cwd=ROOT, timeout=60)
    assert proc.returncode == 0, proc.stderr[-2000:]
    r = json.loads(proc.stdout)
    assert r == {
        'mojibake_corrigido': 'pecas_fabricante_aquecimento_agua_a_gás.aq',
        'ascii_intacto': 'pecas_fabricante_bombas_incendio_2026_04.1.aq',
        'ja_correto_intacto': 'peça — gás.stp',
        'fora_do_latin1_intacto': 'peça — x.ifc',
        'ausente_usa_padrao': 'upload.aq',
        'vazio_usa_padrao': 'upload.aq',
    }
