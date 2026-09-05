import { NextRequest, NextResponse } from 'next/server';
import { API_URL as API } from '@/lib/api';


export async function POST(req: NextRequest) {
  const token = req.cookies.get('session')?.value;
  if (!token) return NextResponse.json({ error: 'unauthorized' }, { status: 401 });

  // Forward multipart form directly
  const formData = await req.formData();
  const body = new FormData();
  for (const [key, value] of formData.entries()) {
    body.append(key, value);
  }

  const apiRes = await fetch(`${API}/empresas`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body,
  });

  const data = await apiRes.json().catch(() => ({}));
  return NextResponse.json(data, { status: apiRes.status });
}
