# Diagnóstico rápido — sintoma → causa → o que fazer

Sintomas de **formato e algoritmo** da biblioteca (`.aq`/OQ3D, IFC, STEP/IGES, geometria,
miniaturas, ZIP). Sintomas operacionais de um serviço específico (rotas, banco, build, ambiente)
estão em `docs/conhecimento/servicos-web.md` — ver a seção final deste documento.

## OQ3D

| Sintoma | Causa | O que fazer |
|---|---|---|
| Uma peça isolada, "solta no ar", sem mudar a contagem de triângulos | Rotação do OQ3D lida como row-major — é column-major | Transpor a matriz antes de aplicar |
| Parafusos e detalhes faltando, malha bem mais pobre que o esperado | Instâncias por referência (objeto reaproveitado) não resolvidas | Resolver cada instância pelo objeto referenciado, não só pelo container — ver `oq3d.md`, "Instâncias repetidas" |
| Peças 100× maiores ou menores | OQ3D grava em **centímetros** | Multiplicar por 0,01 ao converter para metros |
| Joelhos e curvas aparecem retos no viewer | Transforms do OQ3D ignorados | Usar o parser de árvore completo, não só a malha de folha |
| Menos produtos que peças na origem | Peças sem geometria vinculada são tubos/kits, sem forma fixa | Comportamento esperado — pular ao montar o catálogo |

## `.aq` e cp1252

| Sintoma | Causa | O que fazer |
|---|---|---|
| `.aq` não abre como SQLite | Pode ser ZIP, ou arquivo corrompido | Tentar abrir como ZIP primeiro; se falhar, é corrompido. Caminho inexistente deve lançar erro explícito de arquivo ausente — nunca criar um `.aq` vazio no lugar |
| Texto com lixo no meio do nome | Lido como latin-1 ou UTF-8 | Ler sempre como **cp1252** — é o encoding real, mesmo o SQLite declarando UTF-8 |
| `WHERE NOME_x = 'algo acentuado'` volta vazio, sem erro | O `sqlite3` do Python vincula `str` como UTF-8; o texto armazenado é cp1252 | `CAST(? AS TEXT)` com o parâmetro já `.encode('cp1252')` |
| Diâmetro do mapa vale ~2× o esperado, ou vem um número enorme negativo | O campo de diâmetro é um **código**, não centímetro; o número enorme é a sentinela de NULL do formato | Tratar como código (índice numa escala), nunca como medida direta; filtrar a sentinela antes de qualquer conta |
| `no such column` numa tabela de entrada 3D | Coluna só existe em versões mais novas do schema do `.aq` | Checar a versão do schema antes de assumir a coluna |
| `.aq` gerado abre e valida, mas os nomes saem com caractere trocado | Texto gravado em UTF-8 em vez de cp1252 | Escrever sempre com bytes cp1252 |
| Geometria muito maior que o esperado ao gerar a partir do `.aq` | Faltou a deduplicação de vértices | Rodar a etapa de dedup — reduz da ordem de 79% dos vértices numa malha típica |
| `baixar .aq` falha dizendo que um caractere está fora do cp1252 | Nome de peça/série/spec tem caractere que cp1252 não representa (seta, emoji, travessão de outra fonte) | Editar o texto ofensivo e exportar de novo — o gerador não substitui por `?` de propósito |
| `.aq` exportado e reimportado mostra um nome mais curto que o exibido na tela | Não é perda: o nome gravado é o original, sem o prefixo de série que a tela acrescenta para exibição | Comportamento esperado; usar a opção de preservar o prefixo se o objetivo é manter o nome como aparece na tela |

## IFC

| Sintoma | Causa | O que fazer |
|---|---|---|
| Modelo ~1000× maior que o esperado | Conversão mm→m aplicada sem necessidade (ou pulada quando era necessária) | Verificar a magnitude das coordenadas brutas antes de decidir a escala — alguns exportadores declaram uma unidade e gravam em outra |
| Modelo cinza, mas o IFC de origem tem cor | Mapa de cor por face não construído, ou entidade de mapa de cor não encontrada | Conferir se o parser extrai o mapa de cor indexado; sem essa entidade não há cor por face |
| Zero cores extraídas de uma lista de cores RGB | Regex de parsing espera só inteiros; os valores têm casa decimal | Ajustar a regex para casar float |
| `col[]` presente na geometria, mas o viewer ignora e mostra tudo de uma cor | Material sem `vertexColors: true`, ou `color` diferente de branco (a cor do vértice é multiplicada pelo `color` do material) | `vertexColors: true` **e** `color: 0xffffff` juntos |
| Fragmentos da peça a vários metros do corpo principal | Um posicionamento local aberrante no arquivo de origem | Filtrar como outlier ao consolidar a malha, não tentar "corrigir" a transformação |
| Sub-partes separadas por metros, cada uma na própria origem | A hierarquia de posicionamento local não é acumulada recursivamente | Acumular a transformação por toda a cadeia, não só o nível mais próximo da peça |
| Peça exportada abre com a geometria em dobro | Uma montagem recebeu representação geométrica própria além dos elementos-folha | Só entidades de folha (proxies) carregam malha; montagens/assemblies não |
| Parser de IFC ignora um conjunto de faces existente no arquivo | A entidade está quebrada em várias linhas de texto | Casar entidade por unidade lógica completa (`#id=TIPO(args);`), não por linha física |
| Parte da peça exportada aparece rotacionada fora do lugar | Eixos do posicionamento 3D montados sem a conversão de sistema de coordenadas | Aplicar a conversão de eixo também em `Axis`/`RefDirection`, não só na posição |

## STEP e IGES

| Sintoma | Causa | O que fazer |
|---|---|---|
| Conversor morre com `Segmentation fault` | Referência morta da binding do OpenCASCADE — documento liberado com rótulos ainda em uso, ou iterador guardado além do escopo válido | Manter documento/leitor/sequência vivos durante todo o processamento; copiar formas pela função de cópia da API; rodar com rastreador de falhas do Python para achar a linha exata |
| Conversão falha dizendo que o módulo do OpenCASCADE não existe | A dependência nativa não está instalada para o Python que o conversor usa | Instalar o pacote do OpenCASCADE (com as flags que distribuições recentes exigem para instalar fora de venv) |
| STEP importado sai 1000× maior, ou deitado (eixos trocados) | Faltou a escala mm→m, ou a troca de eixo Y-up | Aplicar as duas conversões; conferir se a geometria passou mesmo pelo conversor |
| IFC importado no editor sai 1000× maior ou menor | A heurística de escala só dispara com unidade declarada em milímetro **e** bounding box bruta acima de um limiar — peça pequena em mm não dispara | Aplicar a escala manualmente pela ferramenta de escala global do editor |
| Importação de IFC devolve "não extraiu geometria" | Representação B-rep avançada sem a biblioteca de leitura de IFC disponível, ou arquivo só com curvas | Confirmar que a dependência de leitura de IFC está instalada |
| IFC grande importado sai todo cinza mesmo com material colorido na origem | No caminho de leitura via biblioteca nativa de IFC, o acesso à cor mudou de propriedade para método entre versões | Tratar as duas formas de acesso; se persistir cinza, o arquivo pode genuinamente não ter estilo de superfície definido |
| Peça IGES aparece escura/com faces pretas, ou o volume assinado da malha sai negativo | IGES não carrega sólido — faces soltas sem orientação consistente | Costurar as faces num sólido e inverter pelo sinal do volume; se persistir, conferir a contagem de arestas livres no JSON — casca que não fecha deixa arestas livres, e cor por face pode não sobreviver à costura |

## Geometria, miniaturas e ZIP

| Sintoma | Causa | O que fazer |
|---|---|---|
| Sólido gerado por parâmetro mostra o interior por uma emenda | Perfil de revolução fecha em si mesmo sem soldar o último anel ao primeiro | Conferir arestas de borda — o dobro do número de lados do perfil como arestas de borda denuncia a emenda aberta |
| Peça gerada com partes soltas ou flutuando | Malhas corretas em posição relativa errada — não aparece em bbox nem em contagem de triângulos | Conferir visualmente (abrir o viewer), não só métricas agregadas |
| Editor mostra dezenas de partes numa peça só | Comportamento esperado — cada malha de origem no OQ3D vira ao menos um componente ao re-segmentar | Usar fundir ou re-segmentar depois de mover, não tratar como defeito |
| Uma parte no editor tem milhares de "arestas de borda" | Não é defeito — malha de fabricante é naturalmente não estanque (sopa de triângulos) | O alarme de arestas de borda só vale para malha **gerada** ou **costurada**, que deveria dar zero |
| Dois produtos mudam de geometria quando só um é editado | Bug de copy-on-write: a contagem de "quantos produtos usam esta geometria" foi pulada antes de decidir copiar | Conferir se essa contagem roda antes da decisão de copiar vs. sobrescrever |
| Apaguei uma peça e o arquivo de geometria continua no storage | Esperado — outro produto ainda compartilha a mesma geometria (uma por simbologia, não por produto) | O arquivo só sai com o último produto que o usa; a resposta da remoção lista o que de fato foi apagado |
| Miniatura chapada, sem relevo, visivelmente diferente do viewer | Está saindo de um rasterizador que não é o harness Playwright | Confirmar que a geração passa pelo harness (Chromium + o mesmo Three.js do viewer) — ver `miniaturas.md` |
| Geração de miniatura leva ~2 s cada e o import estoura o tempo | Geometria passada como **objeto** para `page.evaluate` | Passar como string JSON e fazer `JSON.parse` dentro da página — ~6× mais rápido |
| Processo de miniaturas não termina sozinho, ou o Chromium fica órfão | Faltou fechar browser e servidor HTTP antes do `process.exit` | Fechar os dois num `finally`, sempre antes de sair |
| Miniatura regenerada não aparece no browser | ETag deriva só da chave (que não muda), com cache `immutable` | Hard reload para confirmar; para valer em produção, derivar a ETag do conteúdo |
| Import com produtos, mas a etapa de miniaturas não gerou nada | Node incompatível, Playwright/Chromium ausentes, timeout do lote, ou WebGL sem os flags de software rendering | Conferir `thumbCount` contra a contagem de geometrias — menor que o esperado denuncia degradação; os flags de software rendering são obrigatórios sem GPU |
| Resolução do pacote `three` falha ao montar o harness | O pacote não expõe o caminho do build direto pelo mapa de `exports` | Resolver o caminho a partir da localização do próprio pacote instalado; uma variável de ambiente pode sobrepor quando necessário |
| Miniatura regenerada tem data nova mas a imagem é idêntica | A edição não mudou a forma projetada (escala uniforme, por exemplo) — a câmera enquadra pelo bbox | Não é defeito; para comparar de verdade, editar uma dimensão de forma não uniforme |
| Edição de geometria funciona mas o produto fica com erro de miniatura registrado | O serviço de miniaturas não respondeu — a escrita da geometria em si teve sucesso | A geometria já foi gravada; suba o serviço responsável e dispare a regeneração pontual daquele produto |

## Serviços e ferramentas

Sintomas de serviço HTTP, build e ambiente (não de formato/algoritmo) estão em
`docs/conhecimento/servicos-web.md`. As armadilhas mais recentes registradas lá:

- **Contrato JSON Schema recusado** — schemas em draft 2020-12 exigem a build `ajv/dist/2020`
  (`Ajv2020`); o construtor padrão do Ajv só conhece draft-07 e falha sem dizer isso claramente.
- **`tsc -b` "não vê" mudança depois de `rm -rf dist`** — sem `tsBuildInfoFile` apontando para
  dentro de `dist/`, o cache incremental sobrevive fora da pasta apagada.
- **Suíte de teste "passa" com menos testes do que deveria** — uma exclusão de diretório do
  coletor pode casar sem querer com uma pasta de teste inteira (por exemplo, uma pasta chamada
  igual a um nome excluído por outro motivo), e a suíte roda verde só porque boa parte dela nunca
  foi coletada. Só a contagem de coleta denuncia — conferir sempre quantos testes rodaram.
- **`git clean -fdq` apaga dado que ainda não está no `.gitignore`** — mover um diretório de dados
  para um lugar novo sem atualizar o ignore primeiro deixa o destino sem proteção nenhuma.

## Onde está no código

Cada linha deste documento aponta para o mesmo código descrito em detalhe nos documentos por
formato/algoritmo listados em "Ver também" — este arquivo é um índice de sintomas, não a fonte da
explicação.

## Ver também

- `docs/conhecimento/oq3d.md`, `docs/conhecimento/aq-formato.md`, `docs/conhecimento/aq-escrita.md`
- `docs/conhecimento/ifc.md`, `docs/conhecimento/ifc.md`, `docs/conhecimento/step-iges.md`
- `docs/conhecimento/geometria.md`, `docs/conhecimento/miniaturas.md`,
  `docs/conhecimento/catalogo-modelo.md`, `docs/conhecimento/zip-bilds-formato.md`
- `docs/conhecimento/processos-filhos.md`, `docs/conhecimento/servicos-web.md`
