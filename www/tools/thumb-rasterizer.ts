/**
 * thumb-rasterizer.ts — Abordagem B de S2.4
 *
 * Rasterizador software que reproduz o mesmo enquadramento do Three.js harness
 * (templates/thumbs/harness.html), sem browser. Saída: Buffer WebP via ffmpeg.
 *
 * Fidelidade vs. harness:
 *   - Câmera e posição do mesh: idênticos
 *   - Iluminação: aproximação de MeshStandardMaterial (sem PBR completo)
 *   - Anti-aliasing: ausente
 *   - Cores vertex: usadas diretamente como albedo difuso
 *   Divergência é esperada e documentada em ADR-003.
 */

import { spawn } from 'node:child_process';

export interface RasterBuffers {
  pos: number[];
  col: number[];
  idx: number[];
}

export const THUMB_W = 448;
export const THUMB_H = 324;

// Fundo #F3F4F6
const BG_R = 243, BG_G = 244, BG_B = 246;

// Câmera — cópia literal do harness.html
const FOV_Y_DEG = 38;
const NEAR = 0.001;
const FAR = 500;

// Iluminação — cópia literal do harness.html
const AMB_I = 0.7;
const KEY_DIR = norm3([2, 3, 2]);
const KEY_I = 0.9;
const FILL_DIR = norm3([-2, 1, -1]);
const FILL_I = 0.35;
const FILL_R = 0xc8 / 255, FILL_G = 0xd8 / 255, FILL_B = 0xf0 / 255;
// Cor padrão: 0x8896aa (quando sem vertex colors)
const DEF_R = 0x88 / 255, DEF_G = 0x96 / 255, DEF_B = 0xaa / 255;

function norm3(v: [number, number, number]): [number, number, number] {
  const l = Math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]);
  return [v[0] / l, v[1] / l, v[2] / l];
}

function dot3(a: [number, number, number], b: [number, number, number]): number {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

function cross3(
  a: [number, number, number],
  b: [number, number, number],
): [number, number, number] {
  return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
}

/**
 * Renderiza OQ3DBuffers e devolve um Buffer WebP.
 * Lança se ffmpeg não estiver em PATH ou falhar.
 */
export async function renderThumbTs(
  data: RasterBuffers,
  width = THUMB_W,
  height = THUMB_H,
): Promise<Buffer> {
  const { pos, col, idx } = data;
  const hasCol = col && col.length > 0;
  const nVerts = pos.length / 3;
  const nTris = idx.length / 3;

  // ── 1. Bounding box e centróide ─────────────────────────────────────────────
  let minX = Infinity, minY = Infinity, minZ = Infinity;
  let maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity;
  for (let i = 0; i < pos.length; i += 3) {
    if (pos[i] < minX) minX = pos[i];
    if (pos[i + 1] < minY) minY = pos[i + 1];
    if (pos[i + 2] < minZ) minZ = pos[i + 2];
    if (pos[i] > maxX) maxX = pos[i];
    if (pos[i + 1] > maxY) maxY = pos[i + 1];
    if (pos[i + 2] > maxZ) maxZ = pos[i + 2];
  }
  const cx = (minX + maxX) / 2;
  const cy = (minY + maxY) / 2;
  const cz = (minZ + maxZ) / 2;
  const dX = maxX - minX, dY = maxY - minY, dZ = maxZ - minZ;
  const size = Math.sqrt(dX * dX + dY * dY + dZ * dZ);

  // ── 2. Câmera — cópia de camera.position.set() do harness ───────────────────
  // Three.js: mesh.position = -centroid, câmera em (size*0.85, size*0.32, size*0.85)
  // Nós: subtraímos centróide dos vértices na projeção (equivalente)
  const camX = size * 0.85;
  const camY = size * 0.32;
  const camZ = size * 0.85;

  // Three.js lookAt: z_cam = normalize(eye - target) = normalize(cam)
  const camLen = Math.sqrt(camX * camX + camY * camY + camZ * camZ);
  const zcX = camX / camLen, zcY = camY / camLen, zcZ = camZ / camLen;

  // right = cross(worldUp=[0,1,0], z_cam)
  // cross([0,1,0], [zcX,zcY,zcZ]) = [zcZ, 0, -zcX]  (simplificado, zcY cancela)
  let rxX = zcZ, rxY = 0, rxZ = -zcX;
  const rxLen = Math.sqrt(rxX * rxX + rxZ * rxZ);
  rxX /= rxLen; rxZ /= rxLen;

  // up_cam = cross(z_cam, right)
  const ucX = zcY * rxZ - zcZ * rxY;
  const ucY = zcZ * rxX - zcX * rxZ;
  const ucZ = zcX * rxY - zcY * rxX;

  // View matrix: world → camera space
  // [ rx  ry  rz  -dot(r, cam) ]
  // [ uc  uy  uz  -dot(u, cam) ]
  // [ zc  zy  zz  -dot(z, cam) ]  ← z_cam aponta para longe do alvo (OpenGL -Z)
  const rDotC = rxX * camX + rxY * camY + rxZ * camZ;
  const uDotC = ucX * camX + ucY * camY + ucZ * camZ;
  const zDotC = zcX * camX + zcY * camY + zcZ * camZ;

  // ── 3. Projeção perspectiva ──────────────────────────────────────────────────
  const fovRad = (FOV_Y_DEG * Math.PI) / 180;
  const fProj = 1 / Math.tan(fovRad / 2);
  const aspect = width / height;

  // Projeta (wx,wy,wz) em espaço de câmera e depois em pixels
  // Retorna [sx, sy, ez_cam] ou null se fora do frustum/behind camera
  function project(wx: number, wy: number, wz: number): [number, number, number] | null {
    // Camera space
    const ex = rxX * wx + rxY * wy + rxZ * wz - rDotC;
    const ey = ucX * wx + ucY * wy + ucZ * wz - uDotC;
    const ez = zcX * wx + zcY * wy + zcZ * wz - zDotC; // > 0 = behind camera

    // Three.js usa eixo Z negativo → câmera vê objetos com ez < 0
    // mas nós construímos z_cam apontando PARA a câmera, então ez > 0 = atrás
    // Convertemos: ndcZ = usando -ez como profundidade positiva
    if (ez >= -NEAR) return null; // atrás do near plane

    const invD = 1 / (-ez);
    const ndcX = (fProj / aspect) * ex * invD;
    const ndcY = fProj * ey * invD;
    // Clipping loosely — permitimos fora do frame (será clipado pelo bbox)
    const sx = ((ndcX + 1) / 2) * width;
    const sy = ((1 - ndcY) / 2) * height;
    return [sx, sy, ez];
  }

  // ── 4. Pré-projetar todos os vértices ───────────────────────────────────────
  // vProj[i] = [sx, sy, ez] ou null
  const vProj: ([number, number, number] | null)[] = new Array(nVerts);
  for (let i = 0; i < nVerts; i++) {
    const wx = pos[i * 3] - cx;
    const wy = pos[i * 3 + 1] - cy;
    const wz = pos[i * 3 + 2] - cz;
    vProj[i] = project(wx, wy, wz);
  }

  // ── 5. Frame buffer ──────────────────────────────────────────────────────────
  const W = width, H = height;
  const rgba = new Uint8Array(W * H * 4);
  const zbuf = new Float32Array(W * H).fill(-Infinity);

  // Preenche com cor de fundo
  for (let i = 0; i < W * H; i++) {
    rgba[i * 4] = BG_R;
    rgba[i * 4 + 1] = BG_G;
    rgba[i * 4 + 2] = BG_B;
    rgba[i * 4 + 3] = 255;
  }

  // ── 6. Rasterização ──────────────────────────────────────────────────────────
  for (let t = 0; t < nTris; t++) {
    const i0 = idx[t * 3];
    const i1 = idx[t * 3 + 1];
    const i2 = idx[t * 3 + 2];

    const p0 = vProj[i0];
    const p1 = vProj[i1];
    const p2 = vProj[i2];
    // Se algum vértice está atrás da câmera, pula o triângulo inteiro
    // (clipping completo é complexo; para a medição, esta simplificação é aceitável)
    if (!p0 || !p1 || !p2) continue;

    const [sx0, sy0, ez0] = p0;
    const [sx1, sy1, ez1] = p1;
    const [sx2, sy2, ez2] = p2;

    // Bounding box em pixels
    const bxMin = Math.max(0, Math.floor(Math.min(sx0, sx1, sx2)));
    const bxMax = Math.min(W - 1, Math.ceil(Math.max(sx0, sx1, sx2)));
    const byMin = Math.max(0, Math.floor(Math.min(sy0, sy1, sy2)));
    const byMax = Math.min(H - 1, Math.ceil(Math.max(sy0, sy1, sy2)));
    if (bxMin > bxMax || byMin > byMax) continue;

    // Denominador baricêntrico 2D
    const denom = (sy1 - sy2) * (sx0 - sx2) + (sx2 - sx1) * (sy0 - sy2);
    if (Math.abs(denom) < 1e-9) continue;
    const invDenom = 1 / denom;

    // ── Normal da face (espaço mundo, centrado) ──
    const wx0 = pos[i0 * 3] - cx, wy0 = pos[i0 * 3 + 1] - cy, wz0 = pos[i0 * 3 + 2] - cz;
    const wx1 = pos[i1 * 3] - cx, wy1 = pos[i1 * 3 + 1] - cy, wz1 = pos[i1 * 3 + 2] - cz;
    const wx2 = pos[i2 * 3] - cx, wy2 = pos[i2 * 3 + 1] - cy, wz2 = pos[i2 * 3 + 2] - cz;
    let nx = (wy1 - wy0) * (wz2 - wz0) - (wz1 - wz0) * (wy2 - wy0);
    let ny = (wz1 - wz0) * (wx2 - wx0) - (wx1 - wx0) * (wz2 - wz0);
    let nz = (wx1 - wx0) * (wy2 - wy0) - (wy1 - wy0) * (wx2 - wx0);
    const nLen = Math.sqrt(nx * nx + ny * ny + nz * nz);
    if (nLen < 1e-12) continue;
    nx /= nLen; ny /= nLen; nz /= nLen;
    // Garante normal orientada para a câmera (equivalente ao computeVertexNormals do Three.js
    // que depois é usado para iluminação correta em ambos os lados)
    if (camX * nx + camY * ny + camZ * nz < 0) { nx = -nx; ny = -ny; nz = -nz; }

    // ── Iluminação flat (por triângulo) ──
    const keyDiff = Math.max(0, KEY_DIR[0] * nx + KEY_DIR[1] * ny + KEY_DIR[2] * nz);
    const fillDiff = Math.max(0, FILL_DIR[0] * nx + FILL_DIR[1] * ny + FILL_DIR[2] * nz);
    const litR = Math.min(1, AMB_I + KEY_I * keyDiff + FILL_I * FILL_R * fillDiff);
    const litG = Math.min(1, AMB_I + KEY_I * keyDiff + FILL_I * FILL_G * fillDiff);
    const litB = Math.min(1, AMB_I + KEY_I * keyDiff + FILL_I * FILL_B * fillDiff);

    // ── Cor base (média dos vértices ou default) ──
    let baseR: number, baseG: number, baseB: number;
    if (hasCol) {
      baseR = (col[i0 * 3] + col[i1 * 3] + col[i2 * 3]) / 3;
      baseG = (col[i0 * 3 + 1] + col[i1 * 3 + 1] + col[i2 * 3 + 1]) / 3;
      baseB = (col[i0 * 3 + 2] + col[i1 * 3 + 2] + col[i2 * 3 + 2]) / 3;
    } else {
      baseR = DEF_R; baseG = DEF_G; baseB = DEF_B;
    }

    const finalR = (litR * baseR * 255 + 0.5) | 0;
    const finalG = (litG * baseG * 255 + 0.5) | 0;
    const finalB = (litB * baseB * 255 + 0.5) | 0;

    // ── Varredura do bounding box ──
    for (let py = byMin; py <= byMax; py++) {
      for (let px = bxMin; px <= bxMax; px++) {
        const pcx = px + 0.5, pcy = py + 0.5;
        // Coordenadas baricêntricas
        const u = ((sy1 - sy2) * (pcx - sx2) + (sx2 - sx1) * (pcy - sy2)) * invDenom;
        const v = ((sy2 - sy0) * (pcx - sx2) + (sx0 - sx2) * (pcy - sy2)) * invDenom;
        const w = 1 - u - v;
        // Teste de interior (aceita frente e verso — sem backface culling — z-buffer resolve)
        const inside =
          (u >= 0 && v >= 0 && w >= 0) || (u <= 0 && v <= 0 && w <= 0);
        if (!inside) continue;

        // Profundidade interpolada (ez é negativo para objetos à frente)
        const depth = u * ez0 + v * ez1 + w * ez2;
        const bufIdx = py * W + px;
        // Mantém pixel mais próximo (menos negativo = mais próximo)
        if (depth <= zbuf[bufIdx]) continue;
        zbuf[bufIdx] = depth;

        const pIdx = bufIdx * 4;
        rgba[pIdx] = finalR;
        rgba[pIdx + 1] = finalG;
        rgba[pIdx + 2] = finalB;
        rgba[pIdx + 3] = 255;
      }
    }
  }

  // ── 7. Encode WebP via ffmpeg ─────────────────────────────────────────────
  return encodeWebP(Buffer.from(rgba.buffer), W, H);
}

function encodeWebP(rawRgba: Buffer, width: number, height: number): Promise<Buffer> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    // libwebp: -quality 85 equivale ao mime quality=0.85 do canvas
    const ff = spawn('ffmpeg', [
      '-f', 'rawvideo',
      '-vcodec', 'rawvideo',
      '-s', `${width}x${height}`,
      '-pix_fmt', 'rgba',
      '-i', 'pipe:0',
      // rawvideo + rgba: row 0 = topo, igual ao nosso buffer — sem vflip
      '-c:v', 'libwebp',
      '-quality', '85',
      '-f', 'image2pipe',
      '-frames:v', '1',
      'pipe:1',
    ], { stdio: ['pipe', 'pipe', 'pipe'] });

    ff.stdout.on('data', (c: Buffer) => chunks.push(c));
    ff.stderr.on('data', () => { /* suppress */ });
    ff.on('error', reject);
    ff.on('close', (code) => {
      if (code !== 0) return reject(new Error(`ffmpeg exited ${code}`));
      resolve(Buffer.concat(chunks));
    });
    ff.stdin.write(rawRgba);
    ff.stdin.end();
  });
}
