import { NextRequest, NextResponse } from 'next/server';
import { API_URL as API } from '@/lib/api';


export async function GET(req: NextRequest) {
  const token = req.cookies.get('session')?.value;
  if (!token) return NextResponse.json({ error: 'unauthorized' }, { status: 401 });

  const apiRes = await fetch(`${API}/importacoes/ultima`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (apiRes.status === 200) {
    const data = await apiRes.json().catch(() => null);
    return NextResponse.json(data, { status: 200 });
  }
  // null → empresa sem importações
  return NextResponse.json(null, { status: 200 });
}
