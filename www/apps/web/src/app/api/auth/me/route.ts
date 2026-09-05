import { NextRequest, NextResponse } from 'next/server';
import { API_URL as API } from '@/lib/api';


export async function GET(req: NextRequest) {
  const token = req.cookies.get('session')?.value;
  if (!token) return NextResponse.json({ error: 'unauthorized' }, { status: 401 });

  const apiRes = await fetch(`${API}/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!apiRes.ok) return NextResponse.json({ error: 'unauthorized' }, { status: 401 });
  return NextResponse.json(await apiRes.json());
}
