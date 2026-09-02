#!/usr/bin/env python3
"""
pdf_coords.py — extrai o texto do PDF da Akato COM COORDENADAS, célula a célula.

POR QUE NÃO USAR extract_text()
-------------------------------
O PDF foi gerado no Adobe Illustrator: cada célula das tabelas é um operador
`Tj` independente, posicionado em coordenadas absolutas. O `extract_text()` do
pypdf agrupa fragmentos vizinhos por heurística de proximidade e, nessas
tabelas de quatro colunas estreitas, cola células de colunas diferentes:

    célula 21055 (x=87)  +  400 (x=278)  +  50mm (x=154)  +  10 (x=221)
    vira o fragmento único  '21055 40050mm 10'

Perde-se qual número é EMB. e qual é MASTER, e a descrição fica grudada.

A camada de operadores não tem esse problema — `21055` chega sozinho, com
x=87.4 e y=367.3. Esta ferramenta lê nesse nível, via
`visitor_operand_before`, e devolve uma célula por operador de texto.

DETALHES QUE IMPORTAM
---------------------
- **Posição real = tm × cm.** O `tm` é a matriz de texto e o `cm` a matriz
  gráfica corrente. Usar só `tm` põe fora do lugar todo texto dentro de um
  grupo transformado — na página 6 apareciam células em `y = -63`.
- **Encoding cp1252.** Os operandos vêm como bytes; `REDU\\xc7\\xc3O` é
  `REDUÇÃO` em cp1252. Mesma armadilha do `.aq` — ver a skill
  `leitor-biblioteca-aq`. Latin-1 decodifica sem erro mas erra a faixa
  0x80–0x9F, onde estão travessão e aspas curvas.
- **Arrays TJ** trazem ajustes de kerning entre pedaços da mesma palavra
  (`[b'CUR', 18, b'T', 92, b'A']` → `CURVA`). Concatenar as partes de texto e
  ignorar os números é o certo: os saltos de coluna não acontecem dentro de um
  TJ neste PDF, cada coluna tem o seu próprio operador.
- **A ordem de desenho é o sinal mais confiável de estrutura**, mais até que o
  `y`. O Illustrator desenha cada tabela por blocos de coluna — o bloco dos
  códigos, depois o dos masters, depois o cabeçalho, depois o das descrições,
  depois o das embalagens — e cada bloco é um objeto de texto com o seu próprio
  entrelinhamento. Nas tabelas de seis linhas da página 6 os blocos **não
  compartilham as linhas de base**: o código `21004` sai em `y = 381,8` e a sua
  descrição em `y = 277,6`; uma embalagem chega a cair em `y = −63`, fora da
  página. Agrupar por `y` monta linhas erradas. Já a ordem dentro de cada bloco
  espelha exatamente a ordem visual das linhas, então o casamento certo é por
  **ordinal dentro da coluna**, e o campo `ordem` é o que permite fazer isso.

Uso:
    python3 pdf_coords.py <catalogo.pdf> <saida.json>

Somente leitura.
"""
import json
import sys

from pypdf import PdfReader


def _decode(b):
    """cp1252 com fallback — a mesma cascata do leitor de .aq."""
    if isinstance(b, str):
        return b
    try:
        return bytes(b).decode('cp1252')
    except (UnicodeDecodeError, TypeError):
        return bytes(b).decode('latin-1', 'replace')


def _texto_do_operando(operands, operador):
    """String de um Tj/TJ/'/\" — nos arrays, só as partes de texto."""
    if not operands:
        return ''
    alvo = operands[0]
    if operador == b'TJ':
        partes = []
        for item in alvo:
            if isinstance(item, (int, float)):
                continue
            partes.append(_decode(item.get_original_bytes()
                                  if hasattr(item, 'get_original_bytes')
                                  else item))
        return ''.join(partes)
    if hasattr(alvo, 'get_original_bytes'):
        return _decode(alvo.get_original_bytes())
    return _decode(alvo)


def celulas_da_pagina(pagina, num):
    """[{pagina,x,y,corpo,texto}] — uma célula por operador de texto."""
    achadas = []

    def antes(operador, operands, cm, tm):
        if operador not in (b'Tj', b'TJ', b"'", b'"'):
            return
        texto = _texto_do_operando(operands, operador).strip()
        if not texto:
            return
        # Posição de dispositivo: aplica cm ao ponto de origem do texto.
        tx, ty = tm[4], tm[5]
        x = tx * cm[0] + ty * cm[2] + cm[4]
        y = tx * cm[1] + ty * cm[3] + cm[5]
        # Corpo efetivo da fonte: escala vertical de tm composta com cm.
        corpo = abs(tm[3] * cm[3]) or abs(tm[3])
        achadas.append({
            'pagina': num,
            'ordem': len(achadas),   # ordem de desenho — ver nota abaixo
            'x': round(x, 2),
            'y': round(y, 2),
            'corpo': round(corpo, 2),
            'texto': texto,
        })

    pagina.extract_text(visitor_operand_before=antes)
    return achadas


def main():
    if len(sys.argv) < 3:
        sys.exit('Uso: pdf_coords.py <catalogo.pdf> <saida.json>')
    pdf_path, out_path = sys.argv[1], sys.argv[2]

    reader = PdfReader(pdf_path)
    paginas = []
    for i, pagina in enumerate(reader.pages, start=1):
        celulas = celulas_da_pagina(pagina, i)
        caixa = pagina.mediabox
        paginas.append({
            'pagina': i,
            'largura': float(caixa.width),
            'altura': float(caixa.height),
            'celulas': celulas,
        })
        print(f'  página {i:2}: {len(celulas):4} células')

    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump({'origem': pdf_path, 'paginas': paginas}, f,
                  ensure_ascii=False, indent=1)
    total = sum(len(p['celulas']) for p in paginas)
    print(f'{total} células em {len(paginas)} páginas → {out_path}')


if __name__ == '__main__':
    main()
