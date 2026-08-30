'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';

interface Company {
  id: string;
  name: string;
  customUrl: string;
  logoUrl: string | null;
}

export default function EmpresaPage() {
  const router = useRouter();
  const [company, setCompany] = useState<Company | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/empresas/minha')
      .then((r) => {
        if (r.status === 404) {
          router.replace('/empresa/criar');
          return null;
        }
        if (!r.ok) {
          router.replace('/login');
          return null;
        }
        return r.json();
      })
      .then((data) => {
        if (data) setCompany(data);
      })
      .finally(() => setLoading(false));
  }, [router]);

  async function logout() {
    await fetch('/api/auth/logout', { method: 'POST' });
    router.replace('/login');
  }

  if (loading) return <main style={styles.main}><p>Carregando…</p></main>;

  return (
    <main style={styles.main}>
      <div style={styles.card}>
        <div style={styles.header}>
          {company?.logoUrl && (
            <img
              src={`http://localhost:4000${company.logoUrl}`}
              alt="logo"
              style={styles.logo}
            />
          )}
          <div>
            <h1 style={styles.title}>{company?.name}</h1>
            <p style={styles.url}>bilds.com/{company?.customUrl}</p>
          </div>
        </div>

        <div style={styles.actions}>
          <a href="/empresa/importar" style={styles.btnPrimary}>
            Subir biblioteca .aq
          </a>
          <button onClick={logout} style={styles.btnSecondary}>
            Sair
          </button>
        </div>
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
    maxWidth: 480,
    boxShadow: '0 1px 3px rgba(0,0,0,.12)',
  },
  header: { display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '2rem' },
  logo: { width: 64, height: 64, objectFit: 'contain', borderRadius: 4, border: '1px solid #e5e7eb' },
  title: { margin: 0, fontSize: '1.5rem', fontWeight: 700, color: '#111' },
  url: { margin: '0.25rem 0 0', color: '#6b7280', fontSize: '0.875rem' },
  actions: { display: 'flex', gap: '0.75rem', flexWrap: 'wrap' },
  btnPrimary: {
    padding: '0.625rem 1.25rem',
    background: '#1e40af',
    color: '#fff',
    borderRadius: 4,
    textDecoration: 'none',
    fontWeight: 600,
    fontSize: '0.875rem',
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
};
