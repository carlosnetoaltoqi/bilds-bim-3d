# ADR-023 — `CONEXAO_VOLUMETRICA` é o "Pontos de ligação 3D" do Cadastro

**Status:** Aceita (2026-09-10) · **verificada no Builder em 2026-09-10**

## Decisão

Toda peça que recebe entrada sai com **`PECA.CONEXAO_VOLUMETRICA = 1`**. É a mesma escrita que já
anula a seção (ADR-022), agora em `entradas_aq.marcar_pontos_de_ligacao`, chamada de dentro do
`gravar` — vale nos dois escritores e na ferramenta `preencher_entradas_aq`, que conserta arquivo
já exportado. `validar_aq` falha se sobrar peça com entrada sem a marca.

## Por quê

Uma peça nossa com entradas desenhava os pontos de ligação no lugar certo (as bolinhas vermelhas) e
mesmo assim abria no Cadastro com **"Pontos de ligação 3D: Não"** — em biblioteca de válvulas e em
biblioteca de conexões, esta última com entrada em todas as peças. Ou seja: o Builder lê as
`ENTRADA_3D`, mas o rótulo é um campo à parte.

**A documentação do Builder** (`peca.htm`, propriedade *Pontos de ligação 3D*) diz o que o campo é:

> "Permite apresentar no lançamento, peças que possuem pontos de ligação distintos, isto é, quando
> definida como Sim, a ligação passa a ser efetuada em pontos apresentados nas peças, e não mais
> somente no centro das mesmas. (…) Algumas aplicações que geram desenhos apresentando volumes no
> croqui e detalhes, não permitem definir esta propriedade como Sim."

E que ele é alternativo à propriedade *Entradas*:

> "Quando a propriedade Pontos de ligação 3D estiver definida como Sim, a propriedade Entradas não é
> apresentada."

**Qual coluna é** sai por eliminação mais medição. A lista de propriedades da peça em `peca.htm`
bate uma a uma com as colunas da tabela `PECA` — Nome, Ativo, Descrição, Descrição simbologia,
Indicação, Aplicação, Posição, Posicionar campos, Posicionar simbologia, Desenhar simbologia,
Posicionar simbologia 3D, Bifilar realista, Incluir representação paramétrica — e sobra **um único
booleano** (`CONEXAO_VOLUMETRICA`) para **uma única propriedade booleana** (Pontos de ligação 3D).
No catálogo oficial do Builder (`Catalog.db`, schema 625, **31.611 peças**):

| | peças |
|---|---|
| `CONEXAO_VOLUMETRICA = 1` | 4.206 |
| …dessas, **com** `ENTRADA_3D` na simbologia | **4.206 (100 %)** |
| …dessas, **sem** `ENTRADA_PECA` | 3.820 (bate com "a propriedade Entradas não é apresentada") |
| …dessas, com as duas tabelas | 386 (logo ter as duas é legal) |

E na nativa de aquecedores usada como controle, que funciona no Builder, `CONEXAO_VOLUMETRICA = 1`
nas 12 peças. Nossos dois escritores gravavam `0` — fixo, desde sempre.

## Consequências

- A ida e volta dessa mesma nativa agora sai igual à origem no que importa: 12 peças, 7 simbologias,
  `CONEXAO_VOLUMETRICA = 1` em todas.
- Não paramos de escrever `ENTRADA_PECA` junto com `ENTRADA_3D`: a documentação diz que a interface
  esconde uma quando a outra está ligada, mas 386 peças do catálogo oficial têm as duas, e a
  `ENTRADA_PECA` é onde moram bitola e ângulo.
- **Ressalva honesta:** um changelog do Builder (2024-08) escreve "conexão volumétrica **e/ou** ponto
  de ligação 3D", o que sugere dois conceitos distintos. Contra isso pesam a ausência de qualquer
  propriedade chamada "conexão volumétrica" na tela da peça e a correlação de 4.206/4.206. O teste
  no Builder decide.
- Se o rótulo **acender**, cai também a suspeita de que a aplicação errada (ADR-024) fosse a causa —
  ela continua sendo um defeito, mas outro.

## Verificação no Builder (2026-09-10)

O usuário abriu no Cadastro as bibliotecas exportadas depois desta correção e mandou seis telas.
O que elas mostram, dentro de **uma mesma biblioteca nossa** (as válvulas e atuadores de HVAC
importados de famílias Revit):

- peça com entradas → **"Pontos de ligação 3D: Sim"**, e a linha *Entradas* **some** da lista de
  propriedades;
- peça sem entrada (`Entradas: 0`) → o campo aparece **desabilitado**, em cinza, com "Não".

O par confirma as duas metades: `CONEXAO_VOLUMETRICA = 1` acende o rótulo, e o campo é mesmo
**alternativo** à propriedade *Entradas*, como `peca.htm` dizia. As outras telas repetem o "Sim"
em peças de aquecedores a gás e de acessórios sanitários.

Vale registrar o que **não** foi verificado: os `.aq` do teste não estão mais em
`Downloads/teste-geometria-aq/` (foram importados e removidos), então não deu para cruzar peça a
peça o valor gravado com o rótulo na tela. A leitura acima se apoia em o contraste "Sim × Não
desabilitado" aparecer **dentro da mesma biblioteca**, que é nossa.

As mesmas telas trouxeram, de brinde, a prova visual do defeito do ADR-024: os atuadores de HVAC
e um aquecedor a gás aparecem com **"Aplicação: Conexão"**.
