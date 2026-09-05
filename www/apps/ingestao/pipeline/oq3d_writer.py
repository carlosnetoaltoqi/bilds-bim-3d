#!/usr/bin/env python3
"""
oq3d_writer.py — ESCREVE o formato binário OQ3D. O inverso do `www/apps/ingestao/pipeline/oq3d.py`.

O `www/apps/ingestao/pipeline/oq3d.py` do projeto é um leitor TOLERANTE: varre à procura de
`0x5B`/`0x5D` e consome por inteiro apenas os três blocos de tamanho conhecido
(malha, cor, transform). Todo o resto ele pula. Um escritor não tem essa
liberdade — o AltoQi Builder vai ler o que gravarmos e ele conhece o formato
inteiro. Então aqui **nada é inventado**: a moldura é copiada byte a byte de uma
subárvore real, com buracos só onde estão os dados que controlamos.

O gabarito veio da `SIMBOLOGIA_3D` 169 da biblioteca Amanco (`DN150 -
QUADRADA`, schema 595), a menor malha das 12 bibliotecas disponíveis, e o seu
primeiro objeto-raiz é justamente a forma canônica: uma instância com a
definição embutida, uma malha, uma cor e os dois transforms.

ANATOMIA DE UM ARQUIVO OQ3D
---------------------------
Cabeçalho, 37 bytes, idêntico nas 12 bibliotecas e nas 6 versões de schema
(552 a 607):

    3a 01 01 00 00                     5 bytes opacos, sempre estes
    'OQ3D 3D Objects File'             20 bytes de assinatura
    u32 2                              versão do arquivo
    u32 N                              NÚMERO DE OBJETOS-RAIZ
    u32 0

O campo `N` foi confirmado contra o parser em 22 das 24 amostras medidas; nas
duas que divergem (`Intelbras Cont_Acesso` e `PPCI`) o parser conta dois nós a
mais, e a diferença é do leitor tolerante — um `0x5D` dentro de um double
desempilha um nível e promove dois nós filhos a raiz —, não do campo.

Depois vem um objeto-raiz por vez, cada um precedido de um byte `0x02`
("segue item"). Um objeto abre com

    0x5B <u32 tamanho_do_nome> <nome da classe em ASCII>

e fecha com `0x5D`. A árvore que este escritor emite, uma por malha:

    TQi3DReusedObject                  instância
      TQi3DReusableObject                definição embutida
        TQi3DTriangleMesh
          TCoatingColor                    cor uniforme da malha
          TQi3DIndexedTriangleMeshData     vértices e triângulos
        TCoordinateTransformation3D        origem (identidade)
      TCoordinateTransformation3D        alvo — posiciona a instância

É a mesma forma que o leitor espera: `_collect` toma o ÚLTIMO transform filho
direto como o que posiciona, e a cor desce da `TQi3DTriangleMesh` para a malha.

O QUE ESTE ESCRITOR NÃO FAZ
---------------------------
Emite uma malha por objeto-raiz, sempre com a definição embutida
(discriminador `0x02`). Não gera `TQi3DReusedObject` por referência
(discriminador `0x01`), que é como o AltoQi economiza espaço quando a mesma
malha aparece muitas vezes, nem `TQi3DObjectGroup`. Para N malhas saem N
raízes — exatamente o que a Amanco faz na `SIMBOLOGIA_3D` 169, que tem 3
malhas em 3 raízes.

UNIDADES
--------
Centímetros e Z-up, como o formato. Se a geometria vem de um viewer
(metros, Y-up), converta ANTES: `x, y=-z, z=y`, dividido por 0,01.
"""
import struct
import uuid

MAGIC = b'OQ3D 3D Objects File'

# Os 5 bytes que antecedem a assinatura. Constantes nas 12 bibliotecas medidas
# e em todas as 6 versões de schema. Não sabemos o que significam; sabemos que
# não variam, e por isso são copiados literalmente.
PREAMBULO = bytes.fromhex('3a 01 01 00 00')

VERSAO_ARQUIVO = 2
ITEM_SEGUE = b'\x02'
FECHA = b'\x5d'

DISC_INLINE = b'\x02'

# Blocos opacos do gabarito, na ordem em que aparecem. Cada um foi conferido
# byte a byte contra a subárvore de origem — ver `eng-reversa/estudo/`.
#
# TQi3DReusedObject: os 28 bytes antes do tamanho do GUID.
REUSED_CABECA = bytes.fromhex(
    '02 00 00 00'              # u32 versão do objeto = 2
    '02 00 00 00'              # u32 = 2
    '{indice}'                 # u32 índice da instância — preenchido em código
    '00 00 00 ff'              # 4 bytes, cor de fallback (preto opaco)
    '01 00 00 00'              # u32 = 1
    '00 00 00 00 00 00 f0 3f'  # double 1.0
    .replace('{indice}', '00 00 00 00'))
# Os 15 bytes entre o fim do GUID e o discriminador (bloco da versão 2).
REUSED_BLOCO = bytes.fromhex('00 00 00 00 00 01 00 00 00 00 00 00 00 00 00')

# TQi3DReusableObject: payload inteiro.
REUSABLE_PAYLOAD = bytes.fromhex('02 00 00 00 02')

# TQi3DTriangleMesh: o que vem antes e depois da cor RGBA no payload.
MALHA_ANTES = bytes.fromhex('02 00 00 00 02 00 00 00 ff ff ff ff')
MALHA_DEPOIS = bytes.fromhex(
    '01 00 00 00'              # u32 = 1
    '00 00 00 00 00 00 f0 3f'  # double 1.0
    '00 00 00 00'              # u32 = 0
    '00 00 00 00 00'           # 5 zeros
    '01 00 00 00'              # u32 = 1
    '01 00 00 00'              # u32 = 1
    '02')                      # segue item (a TCoatingColor)

# TCoatingColor: o payload é versão, flag e RGBA; depois vem `5d 00 02`, que
# fecha a cor e anuncia a malha indexada.
COR_ANTES = bytes.fromhex('02 00 00 00 02 00 00 00')
COR_DEPOIS = bytes.fromhex('5d 00 02')

# Depois do último índice da malha: 16 zeros, fecha a malha, fecha a
# TQi3DTriangleMesh, e um 0x00 antes do transform de origem.
MALHA_CAUDA = bytes.fromhex('00' * 16 + '5d 5d 00')

# Entre o transform de origem e o de alvo: fecha o transform, fecha a
# TQi3DReusableObject.
ENTRE_TRANSFORMS = bytes.fromhex('5d 5d')

# Depois do transform de alvo: fecha o transform, dois u32 = 1, fecha a
# TQi3DReusedObject.
RAIZ_CAUDA = bytes.fromhex('5d 01 00 00 00 01 00 00 00 5d')

IDENTIDADE = ((1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0), (0.0, 0.0, 0.0))


def _marcador(nome):
    """`0x5B <u32 tamanho> <nome>` — a abertura de um objeto."""
    bruto = nome.encode('ascii')
    return b'\x5b' + struct.pack('<I', len(bruto)) + bruto


def _transform(xform):
    """
    Um `TCoordinateTransformation3D` completo.

    A rotação vai para o arquivo em COLUNAS: o elemento (i, j) mora em
    `r[j*3 + i]`. `xform` chega em linhas, que é a convenção do
    `www/apps/ingestao/pipeline/oq3d.py` — ele já transpõe na leitura. Gravar sem transpor de
    volta produz a matriz transposta, e toda instância com rotação não
    simétrica sai do lugar sem mudar a contagem de triângulos, que é
    justamente o bug que passou despercebido até a sessão S5.1.
    """
    linhas, trans = xform
    colunas = (linhas[0], linhas[3], linhas[6],
               linhas[1], linhas[4], linhas[7],
               linhas[2], linhas[5], linhas[8])
    return (_marcador('TCoordinateTransformation3D')
            + struct.pack('<I', 2)
            + struct.pack('<12d', *colunas, *trans))


def _malha_indexada(verts, tris):
    """Um `TQi3DIndexedTriangleMeshData` com os vértices e os triângulos."""
    coords = [c for v in verts for c in v]
    indices = [i for t in tris for i in t]
    if len(coords) % 3:
        raise ValueError('vértices precisam ter 3 coordenadas cada')
    if len(indices) % 3:
        raise ValueError('triângulos precisam ter 3 índices cada')
    limite = len(verts)
    if indices and max(indices) >= limite:
        raise ValueError(
            f'índice {max(indices)} fora dos {limite} vértices da malha')
    return (_marcador('TQi3DIndexedTriangleMeshData')
            + struct.pack('<3I', 2, len(coords), 0)
            + struct.pack(f'<{len(coords)}d', *coords)
            + struct.pack('<2I', len(indices), 0)
            + struct.pack(f'<{len(indices)}I', *indices))


def _raiz(verts, tris, rgba, xform, indice, guid=None):
    """Um objeto-raiz: uma instância com definição embutida e uma malha."""
    if len(rgba) != 4:
        raise ValueError('rgba precisa ter 4 componentes 0..255')
    cor = bytes(rgba)
    # O GUID é único por instância e nunca serve de chave — o leitor resolve
    # instâncias repetidas pelo índice de serialização, não por ele.
    texto_guid = (guid or str(uuid.uuid4())).upper().encode('ascii')
    if len(texto_guid) != 36:
        raise ValueError('GUID precisa ter 36 caracteres')

    cabeca = bytearray(REUSED_CABECA)
    struct.pack_into('<I', cabeca, 8, indice)

    return (
        ITEM_SEGUE
        + _marcador('TQi3DReusedObject')
        + bytes(cabeca)
        + struct.pack('<I', len(texto_guid)) + texto_guid
        + REUSED_BLOCO
        + DISC_INLINE
        + _marcador('TQi3DReusableObject') + REUSABLE_PAYLOAD
        + _marcador('TQi3DTriangleMesh')
        + MALHA_ANTES + cor + MALHA_DEPOIS
        + _marcador('TCoatingColor') + COR_ANTES + cor + COR_DEPOIS
        + _malha_indexada(verts, tris) + MALHA_CAUDA
        + _transform(IDENTIDADE) + ENTRE_TRANSFORMS
        + _transform(xform or IDENTIDADE) + RAIZ_CAUDA
    )


def escrever(malhas):
    """
    Serializa um blob OQ3D pronto para `SIMBOLOGIA_3D.SIMBOLOGIA_3D`.

    `malhas` é uma lista de `(verts, tris, rgba, xform)`:
      verts  [(x, y, z)]  em CENTÍMETROS, Z-up
      tris   [(a, b, c)]  índices na lista de vértices
      rgba   (r, g, b, a) 0..255, cor UNIFORME da malha
      xform  ((r0..r8), (tx, ty, tz)) em LINHAS, ou None para identidade
    """
    partes = [PREAMBULO, MAGIC,
              struct.pack('<3I', VERSAO_ARQUIVO, len(malhas), 0)]
    for i, (verts, tris, rgba, xform) in enumerate(malhas, start=1):
        partes.append(_raiz(verts, tris, rgba, xform, i))
    return b''.join(partes)


# --- Geometria paramétrica ------------------------------------------------
#
# Um catálogo de PVC é feito de sólidos de revolução e de trechos retos. Estas
# primitivas geram malhas em centímetros, Z-up, com o eixo em Z — as unidades e
# a orientação que o OQ3D usa.

def cilindro(raio, altura, z0=0.0, lados=32, tampas=True):
    """
    Malha de um cilindro com eixo em Z, de `z0` a `z0 + altura`.

    Devolve `(verts, tris)` em centímetros. `tampas=False` deixa os topos
    abertos, para quando o cilindro é a parede de um tubo.
    """
    import math
    verts, tris = [], []
    for i in range(lados):
        a = 2 * math.pi * i / lados
        x, y = raio * math.cos(a), raio * math.sin(a)
        verts.append((x, y, z0))
        verts.append((x, y, z0 + altura))
    for i in range(lados):
        b0 = 2 * i
        b1 = 2 * ((i + 1) % lados)
        tris.append((b0, b1, b1 + 1))
        tris.append((b0, b1 + 1, b0 + 1))
    if tampas:
        base = len(verts)
        verts.append((0.0, 0.0, z0))
        verts.append((0.0, 0.0, z0 + altura))
        for i in range(lados):
            i1 = (i + 1) % lados
            tris.append((base, 2 * i1, 2 * i))
            tris.append((base + 1, 2 * i + 1, 2 * i1 + 1))
    return verts, tris


def tubo(raio_ext, raio_int, altura, z0=0.0, lados=32):
    """
    Malha de um tubo — dois cilindros e as duas coroas que os ligam.

    É a forma de um trecho de tubo de PVC e a base de luvas e caps.
    """
    import math
    verts, tris = [], []
    for raio in (raio_ext, raio_int):
        for i in range(lados):
            a = 2 * math.pi * i / lados
            x, y = raio * math.cos(a), raio * math.sin(a)
            verts.append((x, y, z0))
            verts.append((x, y, z0 + altura))
    ext, int_ = 0, 2 * lados
    for i in range(lados):
        i1 = (i + 1) % lados
        # parede externa, normal para fora
        tris.append((ext + 2 * i, ext + 2 * i1, ext + 2 * i1 + 1))
        tris.append((ext + 2 * i, ext + 2 * i1 + 1, ext + 2 * i + 1))
        # parede interna, normal para dentro
        tris.append((int_ + 2 * i1, int_ + 2 * i, int_ + 2 * i + 1))
        tris.append((int_ + 2 * i1, int_ + 2 * i + 1, int_ + 2 * i1 + 1))
        # coroa de baixo e coroa de cima
        tris.append((ext + 2 * i, int_ + 2 * i, int_ + 2 * i1))
        tris.append((ext + 2 * i, int_ + 2 * i1, ext + 2 * i1))
        tris.append((ext + 2 * i + 1, int_ + 2 * i1 + 1, int_ + 2 * i + 1))
        tris.append((ext + 2 * i + 1, ext + 2 * i1 + 1, int_ + 2 * i1 + 1))
    return verts, tris


def transladar(verts, dx=0.0, dy=0.0, dz=0.0):
    return [(x + dx, y + dy, z + dz) for x, y, z in verts]


def concatenar(*malhas):
    """Junta malhas numa só, reindexando os triângulos."""
    verts, tris = [], []
    for v, t in malhas:
        base = len(verts)
        verts.extend(v)
        tris.extend((a + base, b + base, c + base) for a, b, c in t)
    return verts, tris
