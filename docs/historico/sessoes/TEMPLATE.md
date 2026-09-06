# S<id> — <título da sessão>

> Copie este arquivo para `docs/sessoes/S<id>-<slug>.md` ao **encerrar** a sessão.
> Ele é a única coisa que a sessão seguinte vai ler além do plano e do `CLAUDE.md`.
> Escreva para alguém que não estava aqui e não pode perguntar nada.

**Data:** AAAA-MM-DD · **Sessão do plano:** S\<id\> · **Status:** concluída | concluída com ressalva | bloqueada
**Commits:** `<sha>` … (só os desta sessão)

---

## 1. O que era para fazer

O entregável e o critério de "pronto quando", copiados da seção 10 do plano.

## 2. O que foi feito

O que existe no repositório agora que não existia antes. Caminhos de arquivo, não
adjetivos. Se rodou algum comando que produziu artefato, escreva o comando.

## 3. O que foi verificado — e como

Qual comando ou consulta prova que funciona, e o que ele imprimiu. Sem isso, a sessão
seguinte tem de refazer a verificação do zero.

## 4. Decisões tomadas

Cada uma com o porquê. As de arquitetura também vão para a seção 9 do plano (ADR); aqui
fica o raciocínio completo, lá fica a decisão.

## 5. O que NÃO foi feito, e por quê

Escopo cortado, caminho abandonado, tentativa que falhou. **Especialmente as tentativas
que falharam** — sem isso a próxima sessão repete o erro.

## 6. Surpresas — onde a documentação estava errada

O plano ou o `CLAUDE.md` afirmavam algo que não se confirmou (regra R2). Diga o que
estava escrito, o que era de fato, e **confirme que corrigiu no documento de origem**.

## 7. Onde a próxima sessão começa

- Qual sessão do plano vem a seguir
- O que precisa estar rodando/instalado antes de começar
- Armadilhas concretas que você encontrou e ela vai encontrar
- Perguntas em aberto que ficaram para ela

## 8. Estado verificável ao encerrar

Uma foto do que dá para conferir em segundos — para a sessão seguinte cumprir a R2 sem
adivinhar o que olhar.

| O quê | Estado | Como conferir |
|---|---|---|
| ex.: coleção `bim_geometries` | 47 documentos | `node www/tools/...` |
