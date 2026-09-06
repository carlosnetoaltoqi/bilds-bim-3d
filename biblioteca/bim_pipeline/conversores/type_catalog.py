#!/usr/bin/env python3
"""
type_catalog.py — o *type catalog* de uma família Revit: o `.txt` com o mesmo nome do `.rfa`.

Quando uma família tem muitos tipos (perfis, tubos, luminárias), o fabricante não grava os tipos
dentro do `.rfa` — grava só um tipo-molde e distribui um `.txt` ao lado, que o Revit lê na hora de
carregar a família e oferece como lista de tipos. É por isso que um `PartAtom` pode declarar UM
tipo enquanto o `.txt` traz cento e sessenta: **o `.txt` é a fonte dos tipos** quando existe.

Formato (CSV, separador vírgula — ou TAB, que algumas ferramentas gravam —, decimal ponto):

    ,Largura##SECTION_PROPERTY##MILLIMETERS,Peso nominal##WEIGHT_PER_UNIT_LENGTH##KILOGRAMS_FORCE_PER_METER,Descrição##OTHER##
    Tubo ret 25 x 15 x 0.75,15,0.44,"Perfil, retangular"

  * primeira célula do cabeçalho vazia (ou o nome da família); cada coluna é `NOME##TIPO##UNIDADE`;
  * `TIPO` é o tipo de dado do Revit (LENGTH, SECTION_PROPERTY, NUMBER, INTEGER, TEXT, MATERIAL, YESNO,
    URL, OTHER, WEIGHT_PER_UNIT_LENGTH, AREA_FORCE, LINEAR_FORCE, ANGLE, AREA, VOLUME…);
  * `UNIDADE` é a unidade em que a coluna está escrita (MILLIMETERS, CENTIMETERS, METERS, INCHES,
    FEET, KILOGRAMS_FORCE_PER_METER…); vazia para texto. Comprimento sem unidade é **pé** (a unidade
    interna do Revit);
  * a primeira coluna de cada linha é o nome do tipo; célula com vírgula vai entre aspas;
  * codificação: ANSI da máquina que gravou (cp1252 no Windows em português) na maioria; alguns
    vêm em UTF-16 ou UTF-8 com BOM. Decidimos pelo BOM e, sem BOM, tentamos UTF-8 estrito antes
    de cair no cp1252.

Saída de `ler()`:

    {'colunas': [{'nome', 'tipo', 'unidade'}],
     'tipos':   [{'titulo', 'parametros': {nome: {'valor': str, 'tipo': str, 'unidade': str|None, 'mm': float|None}}}]}

`mm` é o valor convertido para milímetro quando a coluna é de comprimento (LENGTH ou SECTION_PROPERTY
com unidade de comprimento); nas demais é None. `valor` é o texto como está no arquivo.
"""
import csv
import io
import re

# unidade Revit → fator para milímetro (só as de comprimento)
MM_POR_UNIDADE = {
    'MILLIMETERS': 1.0, 'CENTIMETERS': 10.0, 'DECIMETERS': 100.0, 'METERS': 1000.0,
    'INCHES': 25.4, 'FEET': 304.8, 'FEET_FRACTIONAL_INCHES': 304.8, 'FRACTIONAL_INCHES': 25.4,
    'USSURVEYFEET': 304.8006,
}
TIPOS_DE_COMPRIMENTO = ('LENGTH', 'SECTION_PROPERTY', 'SECTION_DIMENSION', 'REINFORCEMENT_LENGTH',
                        'PIPE_SIZE', 'DUCT_SIZE', 'BAR_DIAMETER', 'CRACK_WIDTH', 'DISPLACEMENT_DEFLECTION',
                        'CABLE_TRAY_SIZE', 'CONDUIT_SIZE', 'WIRE_SIZE')

# rótulo curto da unidade, para compor "350 mm" nas specs
ROTULO_UNIDADE = {
    'MILLIMETERS': 'mm', 'CENTIMETERS': 'cm', 'DECIMETERS': 'dm', 'METERS': 'm', 'INCHES': 'in', 'FEET': 'ft',
    'SQUARE_MILLIMETERS': 'mm²', 'SQUARE_CENTIMETERS': 'cm²', 'SQUARE_METERS': 'm²',
    'CUBIC_MILLIMETERS': 'mm³', 'CUBIC_CENTIMETERS': 'cm³', 'CUBIC_METERS': 'm³', 'LITERS': 'L',
    'KILOGRAMS_FORCE_PER_METER': 'kgf/m', 'KILONEWTONS_PER_METER': 'kN/m', 'NEWTONS_PER_METER': 'N/m',
    'KILOGRAMS_FORCE_PER_SQUARE_METER': 'kgf/m²', 'KILONEWTONS_PER_SQUARE_METER': 'kN/m²',
    'KILOGRAMS_PER_CUBIC_METER': 'kg/m³', 'KILOGRAMS': 'kg', 'KILOGRAMS_MASS': 'kg', 'KILOGRAMS_FORCE': 'kgf',
    'KILONEWTONS': 'kN', 'NEWTONS': 'N', 'DEGREES': '°', 'PERCENTAGE': '%', 'WATTS': 'W', 'KILOWATTS': 'kW',
    'VOLTS': 'V', 'AMPERES': 'A', 'PASCALS': 'Pa', 'KILOPASCALS': 'kPa', 'BARS': 'bar', 'CELSIUS': '°C',
    'LITERS_PER_SECOND': 'L/s', 'CUBIC_METERS_PER_HOUR': 'm³/h', 'LITERS_PER_MINUTE': 'L/min',
    'METERS_PER_SECOND': 'm/s', 'KILOGRAMS_PER_METER': 'kg/m',
}


def rotulo_unidade(unidade):
    """"MILLIMETERS" → "mm"; unidade desconhecida volta como está, em minúsculas; vazia → ''."""
    if not unidade:
        return ''
    return ROTULO_UNIDADE.get(unidade.upper(), unidade.lower())


def decodificar(dados):
    """bytes do `.txt` → str, pelo BOM; sem BOM, UTF-8 estrito e depois cp1252 (nunca falha)."""
    if dados[:2] in (b'\xff\xfe', b'\xfe\xff'):
        return dados.decode('utf-16')
    if dados[:3] == b'\xef\xbb\xbf':
        return dados[3:].decode('utf-8')
    try:
        return dados.decode('utf-8')
    except UnicodeDecodeError:
        return dados.decode('cp1252', errors='replace')


def _coluna(cabecalho):
    partes = cabecalho.split('##')
    nome = partes[0].strip()
    tipo = (partes[1].strip().upper() if len(partes) > 1 else '') or 'OTHER'
    unidade = (partes[2].strip().upper() if len(partes) > 2 else '') or None
    return {'nome': nome, 'tipo': tipo, 'unidade': unidade}


def para_mm(valor, tipo, unidade):
    """O número em milímetros, ou None se a coluna não é de comprimento ou o texto não é número."""
    if tipo not in TIPOS_DE_COMPRIMENTO:
        return None
    t = (valor or '').strip().rstrip('"″')
    m = re.fullmatch(r'(?:(-?\d+)\s+)?(\d+)/(\d+)', t)          # polegada fracionária: "1 1/2", "3/4"
    if m and int(m.group(3)):
        n = float(m.group(1) or 0) + float(m.group(2)) / float(m.group(3))
    else:
        m = re.search(r'-?\d+(?:[.,]\d+)?', t.replace(' ', ''))
        if not m:
            return None
        n = float(m.group(0).replace(',', '.'))
    return n * MM_POR_UNIDADE.get(unidade or 'FEET', 304.8)


def separador(texto):
    """Vírgula (o que o Revit grava) ou TAB (o que algumas ferramentas gravam): decidido pela linha de cabeçalho."""
    primeira = texto.lstrip('﻿').split('\n', 1)[0]
    return '\t' if '\t' in primeira and primeira.count('\t') >= primeira.count(',') else ','


def parsear(texto):
    """O texto do `.txt` → `{'colunas', 'tipos'}` (ver docstring do módulo). Linhas vazias são ignoradas."""
    texto = texto.lstrip('﻿')
    linhas = [l for l in csv.reader(io.StringIO(texto), delimiter=separador(texto)) if any(c.strip() for c in l)]
    if not linhas:
        return {'colunas': [], 'tipos': []}
    colunas = [_coluna(c) for c in linhas[0][1:]]
    tipos = []
    for linha in linhas[1:]:
        titulo = (linha[0] or '').strip()
        if not titulo:
            continue
        params = {}
        for i, col in enumerate(colunas):
            valor = linha[i + 1].strip() if i + 1 < len(linha) else ''
            params[col['nome']] = {'valor': valor, 'tipo': col['tipo'], 'unidade': col['unidade'],
                                   'mm': para_mm(valor, col['tipo'], col['unidade'])}
        tipos.append({'titulo': titulo, 'parametros': params})
    return {'colunas': colunas, 'tipos': tipos}


def ler(caminho):
    with open(caminho, 'rb') as f:
        return parsear(decodificar(f.read()))


def eh_type_catalog(texto):
    """Heurística barata para distinguir um type catalog de um `.txt` qualquer ao lado da família."""
    primeira = texto.lstrip('﻿').split('\n', 1)[0]
    return '##' in primeira and primeira.lstrip(' ').startswith((',', '\t', '"'))
