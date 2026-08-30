import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'bilds BIM 3D — POC',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <head>
        <style>{`
          @keyframes spin { to { transform: rotate(360deg); } }
          @keyframes pulse-ring {
            0% { transform: scale(1); opacity: 0.55; }
            100% { transform: scale(2.8); opacity: 0; }
          }
          @keyframes shimmer {
            0% { background-position: -400px 0; }
            100% { background-position: 400px 0; }
          }
        `}</style>
      </head>
      <body>{children}</body>
    </html>
  );
}
