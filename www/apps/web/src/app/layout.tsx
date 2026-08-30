import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'bilds BIM 3D — POC',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <head>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </head>
      <body>{children}</body>
    </html>
  );
}
