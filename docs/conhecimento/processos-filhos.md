# Processos filhos — como um serviço roda Python e Node sem deixar órfão

Todo trabalho pesado — parse de uma biblioteca, tesselagem de um CAD, render de miniaturas — roda
num processo filho separado do serviço que o chamou: uma CLI Python (`bim_pipeline`) ou o
`thumbs.mjs` da biblioteca, no próprio Node do serviço. O contrato entre pai e filho tem quatro
partes.

## O filho morre com o pai via EOF do stdin

O problema que isso resolve: um `SIGKILL` no processo pai (não dá chance de rodar handler nenhum)
não pode deixar um Python de minutos ou um Chromium para trás, gravando arquivos que ninguém vai
registrar no banco. A solução não depende do pai conseguir avisar ninguém — depende só de como o
SO fecha descritores de arquivo quando um processo morre.

O pai abre o filho com o `stdin` em **pipe**, não `ignore` nem herdado. Enquanto o pai está vivo, o
outro lado desse pipe existe; quando o pai morre — de qualquer forma, incluindo `SIGKILL` — o
kernel fecha o pipe, e o filho vê **EOF** ao tentar ler o stdin. Cada lado implementa a vigia à sua
maneira:

```python
# processo.py (Python) — thread daemon que só espera o EOF
def vigiar_stdin(mensagem='...'):
    def _espera():
        while sys.stdin.read(4096):
            pass                    # bloqueia até fechar; read() devolve '' no EOF
        os._exit(2)
    threading.Thread(target=_espera, daemon=True).start()
```

```javascript
// thumbs.mjs (Node) — mesma ideia, orientada a evento
if (sairComStdin) {
  process.stdin.on('end', () => { abortado = true })
  process.stdin.on('close', () => { abortado = true })
  process.stdin.resume()
}
```

A flag que liga isso — `--sair-com-stdin` no Python, `sairComStdin` no JSON de configuração do
Node — só é passada quando quem chama é um serviço. Fora de um serviço (terminal, CI), o stdin é
um TTY ou `/dev/null` e nunca "fecha" no meio de uma execução normal; ligar a vigia ali prenderia
uma thread esperando um EOF que só chegaria com um Ctrl-D explícito.

## stdout é resultado, stderr é progresso

Convenção fixa nos dois lados: uma linha de progresso (uma peça convertida, uma miniatura pronta)
vai para **stderr**; o resultado final estruturado vai para **stdout**, geralmente como a última
linha em JSON. Quem chama lê stdout e stderr linha a linha e entrega cada um para o callback
correspondente (`onStdout`/`onStderr`) assim que a linha chega — não espera o processo terminar
para começar a mostrar progresso.

## Códigos de saída: 0, 1 e 2 têm significado diferente

| Código | Significado |
|---|---|
| `0` | sucesso — tudo que foi pedido terminou |
| `1` | erro de infraestrutura: dependência ausente, arquivo de entrada inválido, algo que impede sequer começar |
| `2` | ou "o pai morreu" (EOF do stdin — ver acima), ou "terminou, mas parte do lote falhou" (uma miniatura entre várias, por exemplo) — o chamador decide se `2` é aceitável dado o que pediu |

Quem chama declara explicitamente quais códigos conta como sucesso (`aceitarCodigos`, padrão só
`[0]`); um filho de render de miniaturas passa `[0, 2]` porque uma falha parcial ainda produz
resultado utilizável. Qualquer código fora dessa lista, ou um sinal, vira uma exceção com o motivo
e as últimas linhas do stderr anexadas — nunca uma promise que nunca resolve.

## Timeout total × timeout de ociosidade são checagens diferentes

Um cronômetro só de tempo total mata um processo saudável que só demora (um IFC grande, uma
biblioteca com milhares de peças) na mesma régua de um processo travado. Por isso existem dois
relógios independentes:

- **Timeout total** — mata o filho depois de X minutos, não importa o que aconteça. É o teto
  absoluto (30 minutos, por padrão, tanto para o Python quanto para o Chromium).
- **Ociosidade** — reinicia um contador toda vez que **qualquer** linha chega em stdout ou
  stderr; se passar um tempo sem nenhuma linha nova, o processo é considerado travado e morto,
  mesmo estando bem dentro do timeout total. Um Chromium que trava renderizando uma geometria
  específica não produz mais nenhuma linha de progresso — é isso que o timeout de ociosidade
  detecta, e o de tempo total não.

Cada motivo de morte (`timeout`, `ocioso`, código de saída fora da lista aceita, sinal, falha do
próprio `spawn`) vira um valor distinto no erro — quem trata o erro não precisa adivinhar qual dos
dois relógios disparou.

## `SIGKILL` sem órfãos

Matar um filho travado usa `SIGKILL`, não `SIGTERM`: um processo em C++ nativo preso numa syscall
(o Chromium, o OpenCASCADE) pode simplesmente ignorar `SIGTERM`. `SIGKILL` não dá chance de
handler — e é justamente por isso que a garantia de "sem órfão" não pode depender de um handler de
saída do **filho**; ela depende do mecanismo de EOF do stdin descrito acima, que funciona mesmo
quando quem morre é o **pai**.

## Flush do IPC antes do `exit` — a lição de uma implementação anterior

Uma implementação anterior deste mesmo contrato usava `fork` do Node com um canal IPC
(`process.send`/`disconnect`) em vez de pipes de stdin/stdout. Migrar para `spawn` + pipes trocou
esse `disconnect` pelo EOF do stdin, mas a lição sobre ordenar operações antes de sair sobrevive
qualquer que seja o mecanismo: fechar recursos (browser, servidor HTTP, conexão) **antes** de
`process.exit()`, nunca depois — o event loop não espera nada que ainda esteja pendente quando
`exit` é chamado, e uma mensagem ou um recurso que devia ter sido liberado primeiro simplesmente
não é.

## Contrato JSON por arquivo temporário, apagado no `finally`

Quando o payload de configuração é grande demais (ou tem estrutura demais) para caber numa linha
de argumento de linha de comando, o pai escreve um arquivo JSON temporário e passa só o **caminho**
como argumento:

```python
cfg_path = os.path.join(thumbs_dir, '.thumbs-config.json')
json.dump(cfg, open(cfg_path, 'w'))
try:
    subprocess.Popen([node, THUMBS_MJS, cfg_path], ...)
    ...
finally:
    if os.path.exists(cfg_path):
        os.remove(cfg_path)
```

O `finally` garante que o arquivo de configuração não sobrevive à chamada, tenha ela terminado
bem ou mal — nada no storage do serviço deve depender de um arquivo temporário de uma execução
anterior ainda estar lá.

## Onde está no código

- `biblioteca/bim_pipeline/processo.py` — `vigiar_stdin()`, o lado Python do contrato.
- `biblioteca/bim_pipeline/miniaturas/thumbs.mjs` — `sairComStdin`, o lado Node.
- `pacotes/base/src/processo.ts` — `executar()`: timeout total, ociosidade, sinais, códigos de
  saída aceitos, stdin em pipe do lado do pai.
- `pacotes/base/src/biblioteca-cli.ts` — `BibliotecaCli.rodar()`/`rodarThumbs()`: os timeouts e
  ociosidades padrão de cada tipo de filho, e como o resultado final em JSON é extraído da última
  linha do stdout.
- `biblioteca/bim_pipeline/miniaturas/render.py` — o arquivo de configuração temporário do
  `thumbs.mjs`.

## Ver também

- `docs/conhecimento/miniaturas.md` — por que o Chromium do `thumbs.mjs` precisa ser fechado
  antes do `process.exit`, e o que `--sair-com-stdin` evita nesse caso específico.
- `docs/decisoes/ADR-010-filhos-morrem-com-o-pai.md`.
- `docs/conhecimento/servicos-web.md` — o lado do serviço Nest que enfileira e observa esses
  processos.
