import { NextRequest, NextResponse } from 'next/server';
import {
  ACCESS_COOKIE_NAME,
  accessSessionTtlSeconds,
  createAccessCookieValue,
  isAccessPasswordConfigured,
  isValidAccessPassword,
} from '@/lib/accessPassword';

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => null);
  const password = (body as { password?: unknown } | null)?.password;

  if (!isAccessPasswordConfigured()) {
    return NextResponse.json(
      { error: 'ACCESS_PASSWORD is not configured.' },
      { status: 500 },
    );
  }

  if (!isValidAccessPassword(password)) {
    return NextResponse.json(
      { error: 'Incorrect access password.' },
      { status: 401 },
    );
  }

  const response = NextResponse.json({ ok: true });
  response.cookies.set({
    name: ACCESS_COOKIE_NAME,
    value: createAccessCookieValue(),
    httpOnly: true,
    sameSite: 'lax',
    secure: process.env.NODE_ENV === 'production',
    path: '/',
    maxAge: accessSessionTtlSeconds(),
  });
  return response;
}
