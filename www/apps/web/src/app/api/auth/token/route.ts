import { NextRequest, NextResponse } from 'next/server';

// Expõe o JWT para o client JS usar no upload direto à API.
// Aceitável na POC (usuário único). Em produção: usar proxy server-side
// com stream, sem esse endpoint.
export async function GET(req: NextRequest) {
  const token = req.cookies.get('session')?.value;
  if (!token) return NextResponse.json({ error: 'unauthorized' }, { status: 401 });
  return NextResponse.json({ token });
}
