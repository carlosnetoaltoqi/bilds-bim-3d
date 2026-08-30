import { NextRequest, NextResponse } from 'next/server';

const API = process.env.API_URL ?? 'http://localhost:4000';

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ importId: string }> },
) {
  const token = req.cookies.get('session')?.value;
  if (!token) return NextResponse.json({ error: 'unauthorized' }, { status: 401 });

  const { importId } = await params;
  const apiRes = await fetch(`${API}/importacoes/${importId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  const data = await apiRes.json().catch(() => ({}));
  return NextResponse.json(data, { status: apiRes.status });
}
