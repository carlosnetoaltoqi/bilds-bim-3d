'use client';

import { useEffect, useRef, useState } from 'react';

type ImportStatus = 'recebido' | 'parseando' | 'gravando' | 'publicado' | 'vazio' | 'falhou';

interface ImportState {
  importId: string;
  status: ImportStatus;
  productCount: number | null;
  error: string | null;
  note: string | null;
  catalogId: string | null;
}

const TERMINAL: ImportStatus[] = ['publicado', 'vazio', 'falhou'];
const POLL_INTERVAL_MS = 3000;

const STATUS_LABELS: Record<ImportStatus, string> = {
  recebido: 'Arquivo recebido',
  parseando: 'Lendo arquivo .aq…',
  gravando: 'Gravando geometrias e catálogo…',
  publicado: 'Publicado',
  vazio: 'Arquivo sem geometrias',
  falhou: 'Falhou',
};

const STATUS_STEPS: ImportStatus[] = ['recebido', 'parseando', 'gravando', 'publicado'];

function formatElapsed(s: number): string {
  if (s < 60) return `há ${s}s`;
  const m = Math.floor(s / 60);
  return `há ${m}m ${(s % 60).toString().padStart(2, '0')}s`;
}

export default function ImportarPage() {
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadPct, setUploadPct] = useState(0);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [imp, setImp] = useState<ImportState | null>(null);
  const [pageLoading, setPageLoading] = useState(true);
  const [elapsed, setElapsed] = useState(0);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startRef = useRef<number>(0);

  // Recovery: ao carregar a página, busca a última importação no banco
  useEffect(() => {
    fetch('/api/importacoes/ultima')
      .then((r) => r.json())
      .then((data) => {
        if (data?.importId) setImp(data as ImportState);
      })
      .catch(() => {})
      .finally(() => setPageLoading(false));
  }, []);

  // Polling quando há importação não-terminal
  useEffect(() => {
    if (!imp) return;
    if (TERMINAL.includes(imp.status)) {
      if (pollRef.current) clearInterval(pollRef.current);
      return;
    }

    pollRef.current = setInterval(async () => {
      try {
        const r = await fetch(`/api/importacoes/${imp.importId}`);
        if (!r.ok) return;
        const data = await r.json();
        setImp(data as ImportState);
        if (TERMINAL.includes(data.status)) {
          clearInterval(pollRef.current!);
        }
      } catch {
        // mantém polling mesmo com falha de rede
      }
    }, POLL_INTERVAL_MS);

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [imp?.importId, imp?.status]);

  // Reseta cronômetro quando começa novo import
  useEffect(() => {
    if (!imp) return;
    startRef.current = Date.now();
    setElapsed(0);
  }, [imp?.importId]);

  // Tick a cada segundo enquanto não-terminal
  useEffect(() => {
    if (!imp || TERMINAL.includes(imp.status)) return;
    const t = setInterval(() => setElapsed(Math.round((Date.now() - startRef.current) / 1000)), 1000);
    return () => clearInterval(t);
  }, [imp?.importId, imp?.status]);

  function handleUpload(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;

    setUploading(true);
    setUploadPct(0);
    setUploadError(null);

    // Obtém token primeiro, depois faz o upload via XHR para ter progresso real
    fetch('/api/auth/token')
      .then((r) => r.ok ? r.json() : Promise.reject('session'))
      .then(({ token }) => new Promise<{ importId: string; status: string }>((resolve, reject) => {
        const form = new FormData();
        form.append('file', file);

        const xhr = new XMLHttpRequest();
        xhr.open('POST', 'http://localhost:4000/importacoes');
        xhr.setRequestHeader('Authorization', `Bearer ${token}`);

        xhr.upload.onprogress = (ev) => {
          if (ev.lengthComputable) setUploadPct(Math.round((ev.loaded / ev.total) * 100));
        };

        xhr.onload = () => {
          const data = JSON.parse(xhr.responseText);
          if (xhr.status >= 200 && xhr.status < 300) resolve(data);
          else reject(data.message ?? 'Erro ao enviar arquivo');
        };
        xhr.onerror = () => reject('Erro de rede ao enviar arquivo');
        xhr.send(form);
      }))
      .then((data) => {
        setImp({ importId: data.importId, status: data.status as ImportStatus, productCount: null, error: null, note: null, catalogId: null });
        setFile(null);
      })
      .catch((err) => setUploadError(typeof err === 'string' ? err : 'Erro ao enviar arquivo'))
      .finally(() => { setUploading(false); setUploadPct(0); });
  }

  function reset() {
    setImp(null);
    setFile(null);
    setUploadError(null);
  }

  if (pageLoading) {
    return <main style={s.main}><p style={s.muted}>Carregando…</p></main>;
  }

  return (
    <main style={s.main}>
      <div style={s.card}>
        <div style={s.topRow}>
          <a href="/empresa" style={s.back}>← Empresa</a>
          <h1 style={s.title}>Subir biblioteca .aq</h1>
        </div>

        {!imp && (
          <form onSubmit={handleUpload} style={s.form}>
            <label style={s.label}>
              Arquivo <code style={s.code}>.aq</code>
              <input
                type="file"
                accept=".aq"
                style={s.fileInput}
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                disabled={uploading}
              />
            </label>

            {file && (
              <p style={s.fileName}>{file.name} ({(file.size / 1024 / 1024).toFixed(1)} MB)</p>
            )}

            {uploadError && <p style={s.errorText}>{uploadError}</p>}

            {uploading && (
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.3rem' }}>
                  <span style={{ fontSize: '0.8rem', color: '#1e40af', fontWeight: 500 }}>
                    {uploadPct < 100 ? 'Enviando arquivo…' : 'Processando…'}
                  </span>
                  <span style={{ fontSize: '0.8rem', color: '#6b7280' }}>{uploadPct}%</span>
                </div>
                <div style={{ height: 6, background: '#e5e7eb', borderRadius: 3, overflow: 'hidden' }}>
                  <div style={{
                    height: '100%',
                    width: `${uploadPct}%`,
                    background: 'linear-gradient(90deg, #1e40af, #3b82f6)',
                    borderRadius: 3,
                    transition: 'width 0.3s ease',
                  }} />
                </div>
              </div>
            )}

            <button type="submit" disabled={!file || uploading} style={s.btnPrimary}>
              {uploading ? (uploadPct < 100 ? `Enviando… ${uploadPct}%` : 'Processando…') : 'Enviar'}
            </button>
          </form>
        )}

        {imp && (
          <div style={s.statusWrap}>
            <StatusDisplay imp={imp} onReset={reset} elapsed={elapsed} />
          </div>
        )}
      </div>
    </main>
  );
}

function StatusDisplay({ imp, onReset, elapsed }: { imp: ImportState; onReset: () => void; elapsed: number }) {
  const isTerminal = TERMINAL.includes(imp.status);
  const isFailed = imp.status === 'falhou';
  const isEmpty = imp.status === 'vazio';
  const isDone = imp.status === 'publicado';

  return (
    <div>
      {!isFailed && !isEmpty && <StepTracker status={imp.status} />}

      <div style={{ marginTop: '1.5rem' }}>
        {isDone && (
          <div style={s.successBox}>
            <p style={s.successTitle}>Catálogo publicado!</p>
            {imp.productCount != null && (
              <p style={s.muted}>{imp.productCount} produto{imp.productCount !== 1 ? 's' : ''} com geometria</p>
            )}
            {imp.note && <p style={{ ...s.muted, fontSize: '0.8rem', marginTop: '0.5rem' }}>{imp.note}</p>}
          </div>
        )}

        {isEmpty && (
          <div style={s.warnBox}>
            <p style={s.warnTitle}>Nenhuma geometria encontrada</p>
            <p style={s.muted}>O arquivo foi lido com sucesso, mas não contém peças com geometria 3D (tubos e kits não têm forma fixa).</p>
          </div>
        )}

        {isFailed && (
          <div style={s.errorBox}>
            <p style={s.errorTitle}>Falha na importação</p>
            {imp.error && <p style={s.errorDetail}>{imp.error}</p>}
          </div>
        )}

        {!isTerminal && (
          <div style={s.progressBox}>
            <Spinner />
            <div>
              <p style={s.progressText}>{STATUS_LABELS[imp.status]}</p>
              {elapsed > 2 && (
                <p style={{ margin: 0, color: '#93c5fd', fontSize: '0.75rem', marginTop: '0.15rem' }}>
                  {formatElapsed(elapsed)}
                </p>
              )}
            </div>
          </div>
        )}
      </div>

      {(isTerminal) && (
        <button onClick={onReset} style={{ ...s.btnSecondary, marginTop: '1.5rem' }}>
          {isFailed || isEmpty ? 'Tentar novamente' : 'Subir outra biblioteca'}
        </button>
      )}
    </div>
  );
}

function StepTracker({ status }: { status: ImportStatus }) {
  const currentIdx = STATUS_STEPS.indexOf(status);
  const progressPct = Math.round((currentIdx / (STATUS_STEPS.length - 1)) * 100);

  return (
    <div>
      <div style={s.steps}>
        {STATUS_STEPS.map((step, i) => {
          const done = i < currentIdx;
          const active = i === currentIdx;
          return (
            <div key={step} style={s.stepItem}>
              {/* wrapper para posicionar o anel de pulso */}
              <div style={{ position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                {active && (
                  <div style={{
                    position: 'absolute',
                    width: 28,
                    height: 28,
                    borderRadius: '50%',
                    background: '#1e40af',
                    animation: 'pulse-ring 1.8s ease-out infinite',
                  }} />
                )}
                <div style={{
                  ...s.stepDot,
                  position: 'relative',
                  background: done ? '#16a34a' : active ? '#1e40af' : '#e5e7eb',
                  border: active ? '2px solid #1e40af' : done ? '2px solid #16a34a' : '2px solid #e5e7eb',
                }}>
                  {done && <span style={s.checkmark}>✓</span>}
                </div>
              </div>
              <span style={{
                ...s.stepLabel,
                color: done ? '#16a34a' : active ? '#1e40af' : '#9ca3af',
                fontWeight: active ? 600 : 400,
              }}>
                {STATUS_LABELS[step]}
              </span>
              {i < STATUS_STEPS.length - 1 && (
                <div style={{ ...s.stepLine, background: done ? '#16a34a' : '#e5e7eb' }} />
              )}
            </div>
          );
        })}
      </div>

      {/* barra de progresso linear */}
      <div style={{ marginTop: '1.25rem', height: 4, background: '#e5e7eb', borderRadius: 2, overflow: 'hidden' }}>
        <div style={{
          height: '100%',
          width: `${progressPct}%`,
          background: 'linear-gradient(90deg, #16a34a, #1e40af)',
          borderRadius: 2,
          transition: 'width 0.7s ease',
        }} />
      </div>
    </div>
  );
}

function Spinner() {
  return (
    <div style={s.spinner} />
  );
}

const s: Record<string, React.CSSProperties> = {
  main: {
    minHeight: '100vh',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: '#f3f4f6',
    fontFamily: 'Inter, system-ui, sans-serif',
    padding: '1rem',
  },
  card: {
    background: '#fff',
    borderRadius: 8,
    padding: '2rem',
    width: '100%',
    maxWidth: 560,
    boxShadow: '0 1px 3px rgba(0,0,0,.12)',
  },
  topRow: { display: 'flex', alignItems: 'baseline', gap: '1rem', marginBottom: '1.5rem' },
  back: { color: '#6b7280', fontSize: '0.875rem', textDecoration: 'none' },
  title: { margin: 0, fontSize: '1.25rem', fontWeight: 700, color: '#111' },
  form: { display: 'flex', flexDirection: 'column', gap: '1rem' },
  label: { display: 'flex', flexDirection: 'column', gap: '0.375rem', fontSize: '0.875rem', color: '#374151', fontWeight: 500 },
  code: { fontFamily: 'monospace', fontSize: '0.8rem', background: '#f3f4f6', padding: '0.1rem 0.3rem', borderRadius: 3 },
  fileInput: { marginTop: '0.25rem', fontSize: '0.875rem' },
  fileName: { margin: 0, fontSize: '0.875rem', color: '#374151' },
  errorText: { margin: 0, color: '#dc2626', fontSize: '0.875rem' },
  muted: { margin: 0, color: '#6b7280', fontSize: '0.875rem' },
  btnPrimary: {
    padding: '0.625rem 1.25rem',
    background: '#1e40af',
    color: '#fff',
    border: 'none',
    borderRadius: 4,
    fontWeight: 600,
    fontSize: '0.875rem',
    cursor: 'pointer',
    alignSelf: 'flex-start',
    opacity: 1,
  },
  btnSecondary: {
    padding: '0.625rem 1.25rem',
    background: 'transparent',
    color: '#374151',
    border: '1px solid #d1d5db',
    borderRadius: 4,
    fontWeight: 600,
    fontSize: '0.875rem',
    cursor: 'pointer',
  },
  statusWrap: { marginTop: '0.5rem' },
  steps: { display: 'flex', alignItems: 'flex-start', gap: 0 },
  stepItem: { display: 'flex', flexDirection: 'column', alignItems: 'center', position: 'relative', flex: 1 },
  stepDot: {
    width: 28, height: 28, borderRadius: '50%',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    position: 'relative', zIndex: 1,
  },
  checkmark: { color: '#fff', fontSize: '0.75rem', fontWeight: 700 },
  stepLabel: { marginTop: '0.375rem', fontSize: '0.7rem', textAlign: 'center', lineHeight: 1.3 },
  stepLine: {
    position: 'absolute',
    top: 14,
    left: '50%',
    width: '100%',
    height: 2,
    zIndex: 0,
  },
  progressBox: {
    display: 'flex', alignItems: 'center', gap: '0.75rem',
    padding: '1rem', borderRadius: 6,
    background: 'linear-gradient(90deg, #eff6ff 0%, #dbeafe 30%, #eff6ff 60%, #dbeafe 90%, #eff6ff 100%)',
    backgroundSize: '400px 100%',
    animation: 'shimmer 2.8s linear infinite',
  },
  progressText: { margin: 0, color: '#1e40af', fontSize: '0.9rem', fontWeight: 500 },
  successBox: {
    padding: '1rem', background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 6,
  },
  successTitle: { margin: '0 0 0.25rem', color: '#16a34a', fontWeight: 700, fontSize: '1rem' },
  warnBox: {
    padding: '1rem', background: '#fffbeb', border: '1px solid #fde68a', borderRadius: 6,
  },
  warnTitle: { margin: '0 0 0.5rem', color: '#92400e', fontWeight: 700, fontSize: '1rem' },
  errorBox: {
    padding: '1rem', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 6,
  },
  errorTitle: { margin: '0 0 0.5rem', color: '#dc2626', fontWeight: 700, fontSize: '1rem' },
  errorDetail: { margin: 0, color: '#7f1d1d', fontSize: '0.8rem', fontFamily: 'monospace', wordBreak: 'break-word' },
  spinner: {
    width: 18, height: 18, borderRadius: '50%',
    border: '2px solid #bfdbfe',
    borderTopColor: '#1e40af',
    animation: 'spin 0.8s linear infinite',
    flexShrink: 0,
  },
};
