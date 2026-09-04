# Templates HTML e Three.js dos catálogos

> Movido do `CLAUDE.md` em 2026-09-04 (S7.8, item I22 da auditoria). O conteúdo é o que estava lá,
> com as afirmações desatualizadas de I23 corrigidas no lugar; onde diz "este arquivo", "acima" ou
> "no histórico", leia-se o `CLAUDE.md` antigo — o histórico está em `docs/sessoes/`. **Manter aqui**
> a partir de agora: o `CLAUDE.md` só aponta para este arquivo.

### Three.js self-hosted — obrigatório

CSP da Vercel bloqueia `cdn.jsdelivr.net`, `unpkg.com`, `cdnjs.cloudflare.com`
silenciosamente. Sempre self-host em `templates/vendor/` e copiar para `output/preview/vendor/`.
Nenhum dos dois está no git — `scripts/setup_vendor.sh` é obrigatório em clone novo.

### Padrão de thumbnail estática + click-to-3D

Não inicializar todos os viewers simultaneamente — GPU explode com 10+ contextos WebGL.
- `IntersectionObserver` com `rootMargin:'120px'` para lazy load
- `renderer.render()` uma vez → thumbnail estática
- OrbitControls + loop de animação só ao clicar

### Cache de geometria

```javascript
const geoCache = new Map(); // filename → data
async function fetchGeo(geo) {
  if (geoCache.has(geo)) return geoCache.get(geo);
  const data = await fetch('./data/' + geo).then(r => r.json());
  geoCache.set(geo, data); return data;
}
```

Quando o modal abre, o JSON já está em memória se o thumbnail foi carregado.

### vertexColors no Three.js

```javascript
const hasCol = data.col && data.col.length > 0;
const mat = new THREE.MeshStandardMaterial({
  vertexColors: hasCol,
  color: hasCol ? 0xffffff : 0x8896AA,  // branca com vertexColors (multiplicação), cinza sem
});
if (data.idx) geom.setIndex(data.idx);  // guard — ausente em geo expandida
```

### Escape no template — nomes vêm do fabricante

Série, título e descrição saem do `.aq` e chegam ao HTML por Jinja2. A Komeco tem séries
`1" x 1"`; a Maxbar, `MAXBAR CMAX - "T" Horizontal`. Com `autoescape=False` o chip
`data-filter="{{ f }}" onclick="filterBy('{{ f }}')"` era truncado e o `onclick` virava
erro de sintaxe que só aparecia ao clicar — 6 catálogos publicados assim, sem aviso no
build. Desde S7.4 o `Environment` tem `autoescape=True` e o handler é
`filterBy(this.dataset.filter, this)`. `| tojson | safe` continua correto: sob autoescape o
`tojson` escapa `<`, `>` e `&` em `\uXXXX`, o que também protege o `<script>` de um nome
com `</script>`. Não desligar o autoescape para "consertar" um `&#34;` visível — o lugar
de decodificar é o DOM, e ele já faz isso.

### Design tokens bilds.com

```css
--orange: #FF4F1F   /* só em botão CTA primário */
--blue:   #1E40AF   /* botão secundário, link */
--radius: 4px       /* universal; badge é exceção: 9999px */
```
Fontes: **Fira Sans** (título de seção, hero) + **Inter** (todo o resto).
Ícones: Lucide SVG, stroke 2px, outline, currentColor.
Sombra: só no hover de cards clicáveis. Cards sem borda de hover por padrão.
