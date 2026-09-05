import { NextRequest, NextResponse } from 'next/server';
import { API_URL as API } from '@/lib/api';


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
