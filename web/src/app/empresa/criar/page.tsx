'use client';

import { useState, FormEvent, ChangeEvent } from 'react';
import { useRouter } from 'next/navigation';
import { CATALOGO_URL } from '@/servicos/catalogo';

export default function CriarEmpresaPage() {
  const router = useRouter();
  const [name, setName] = useState('');
  const [customUrl, setCustomUrl] = useState('');
  const [logo, setLogo] = useState<File | null>(null);
  const [preview, setPreview] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  function handleLogoChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0] ?? null;
    setLogo(file);
    if (file) {
      const reader = new FileReader();
      reader.onload = (ev) => setPreview(ev.target?.result as string);
      reader.readAsDataURL(file);
    } else {
      setPreview('');
    }
  }

  function slugify(s: string) {
    return s.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '');
  }

  function handleNameChange(e: ChangeEvent<HTMLInputElement>) {
    const v = e.target.value;
    setName(v);
    if (!customUrl || customUrl === slugify(name)) {
      setCustomUrl(slugify(v));
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const form = new FormData();
      form.append('name', name);
      form.append('customUrl', customUrl);
      if (logo) form.append('logo', logo);

      const res = await fetch(`${CATALOGO_URL}/empresas`, { method: 'POST', body: form });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(data.message ?? 'Erro ao criar empresa');
        return;
      }
      router.replace('/empresa');
    } catch {
      setError('Erro de conexão com a API');
    } finally {
      setLoading(false);
    }
  }

  return (
    <main style={styles.main}>
      <div style={styles.card}>
        <p className="text-[12px] text-gray-500 mb-4"><a href="/" className="hover:underline">← empresas e catálogos</a></p>
        <h1 style={styles.title}>Criar empresa</h1>
        <aside style={styles.help}>
          <p style={styles.helpItem}><strong style={styles.helpLabel}>Para que serve:</strong> todo catálogo pertence a uma empresa. Cadastre a empresa primeiro — depois importe bibliotecas e peças sob ela.</p>
          <p style={styles.helpItem}><strong style={styles.helpLabel}>URL pública:</strong> define o endereço dos catálogos da empresa (ex.: bilds.com/<em>url</em>/nome-do-catalogo). Use um identificador curto, sem espaços e sem acentos — ele não pode ser alterado depois.</p>
        </aside>
        <form onSubmit={handleSubmit} style={styles.form}>
          <label style={styles.label}>
            Nome da empresa
            <input
              type="text"
              value={name}
              onChange={handleNameChange}
              style={styles.input}
              required
            />
          </label>
          <label style={styles.label}>
            URL pública
            <div style={styles.urlRow}>
              <span style={styles.urlPrefix}>bilds.com/</span>
              <input
                type="text"
                value={customUrl}
                onChange={(e) => setCustomUrl(slugify(e.target.value))}
                style={{ ...styles.input, flex: 1 }}
                required
              />
            </div>
          </label>
          <label style={styles.label}>
            Logo (opcional)
            <input
              type="file"
              accept="image/*"
              onChange={handleLogoChange}
              style={styles.fileInput}
            />
          </label>
          {preview && (
            <img
              src={preview}
              alt="preview"
              style={{ width: 80, height: 80, objectFit: 'contain', borderRadius: 4, border: '1px solid #e5e7eb' }}
            />
          )}
          {error && <p style={styles.error}>{error}</p>}
          <button type="submit" disabled={loading} style={styles.btn}>
            {loading ? 'Criando…' : 'Criar empresa'}
          </button>
        </form>
      </div>
    </main>
  );
}

const styles: Record<string, React.CSSProperties> = {
  main: {
    minHeight: '100vh',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: '#f3f4f6',
    fontFamily: 'Inter, system-ui, sans-serif',
  },
  card: {
    background: '#fff',
    borderRadius: 8,
    padding: '2.5rem 2rem',
    width: '100%',
    maxWidth: 440,
    boxShadow: '0 1px 3px rgba(0,0,0,.12)',
  },
  title: { margin: '0 0 0.75rem', fontSize: '1.5rem', fontWeight: 700, color: '#111' },
  help: {
    background: '#f8fafc',
    border: '1px solid #e2e8f0',
    borderRadius: 6,
    padding: '0.75rem 1rem',
    marginBottom: '1.25rem',
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '0.4rem',
  },
  helpItem: { margin: 0, fontSize: '0.8125rem', color: '#4b5563', lineHeight: 1.5 },
  helpLabel: { fontWeight: 600, color: '#111' },
  form: { display: 'flex', flexDirection: 'column', gap: '1rem' },
  label: { display: 'flex', flexDirection: 'column', gap: 4, fontSize: '0.875rem', fontWeight: 500 },
  input: {
    padding: '0.5rem 0.75rem',
    border: '1px solid #d1d5db',
    borderRadius: 4,
    fontSize: '1rem',
    outline: 'none',
  },
  urlRow: { display: 'flex', alignItems: 'center', gap: 0 },
  urlPrefix: {
    padding: '0.5rem 0.5rem',
    background: '#f3f4f6',
    border: '1px solid #d1d5db',
    borderRight: 'none',
    borderRadius: '4px 0 0 4px',
    fontSize: '0.875rem',
    color: '#6b7280',
    whiteSpace: 'nowrap',
  },
  fileInput: { fontSize: '0.875rem' },
  error: { margin: 0, color: '#dc2626', fontSize: '0.875rem' },
  btn: {
    padding: '0.625rem',
    background: '#1e40af',
    color: '#fff',
    border: 'none',
    borderRadius: 4,
    fontSize: '1rem',
    fontWeight: 600,
    cursor: 'pointer',
    marginTop: '0.5rem',
  },
};
