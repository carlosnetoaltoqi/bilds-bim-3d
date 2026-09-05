import { NextRequest, NextResponse } from 'next/server';
import { API_URL as API } from '@/lib/api';


export async function GET(req: NextRequest) {
  const token = req.cookies.get('session')?.value;
  if (!token) return NextResponse.json({ error: 'unauthorized' }, { status: 401 });

  const apiRes = await fetch(`${API}/empresas/minha`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  const data = await apiRes.json().catch(() => ({}));
  return NextResponse.json(data, { status: apiRes.status });
}
