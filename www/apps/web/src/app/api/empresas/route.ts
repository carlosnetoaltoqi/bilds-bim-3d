import { NextRequest, NextResponse } from 'next/server';

const API = process.env.API_URL ?? 'http://localhost:4000';

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
