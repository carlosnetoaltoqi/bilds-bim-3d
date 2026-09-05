"""
processo.py — comportamento comum aos processos filhos do serviço de ingestão.

`vigiar_stdin()` faz o processo sair (código 2) quando o `stdin` fecha. O serviço
(`apps/ingestao`) abre cada filho com o `stdin` em pipe: se a API morrer — inclusive
por SIGKILL, que não dá chance de matar filhos — o pipe fecha e o filho para em vez
de terminar um parse de minutos e gravar centenas de JSONs que ninguém vai registrar
(o mesmo problema do I29, resolvido antes pelo `disconnect` do IPC do `fork`).

Fora do serviço (terminal, testes) o `stdin` é um TTY ou /dev/null e nunca "fecha"
no meio — a thread fica bloqueada e morre com o processo (é daemon).
"""
import os
import sys
import threading


def vigiar_stdin(mensagem='o processo pai fechou o stdin — saindo (2)'):
    """Sai com 2 assim que o stdin chegar ao fim. Idempotente; ignora stdin ausente."""
    if getattr(vigiar_stdin, '_ativo', False):
        return
    vigiar_stdin._ativo = True

    def _espera():
        try:
            # read() devolve '' no EOF; um TTY só chega lá com Ctrl-D
            while sys.stdin.read(4096):
                pass
        except Exception:
            return
        sys.stderr.write(mensagem + '\n')
        sys.stderr.flush()
        os._exit(2)

    if sys.stdin is None or sys.stdin.closed:
        return
    threading.Thread(target=_espera, daemon=True, name='vigiar-stdin').start()
