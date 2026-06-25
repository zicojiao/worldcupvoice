// Server-only access gate used while the live booth is in private preview.
// Do NOT import this from client components — it would leak the default
// password into the browser bundle. Route handlers only.

import { createHmac, timingSafeEqual } from 'crypto';

const DEFAULT_ACCESS_SESSION_TTL_SECONDS = 60 * 60 * 12;

export const ACCESS_COOKIE_NAME = 'worldcupvoice_access';

function expectedPassword(): string | null {
  const value = process.env.ACCESS_PASSWORD?.trim();
  return value ? value : null;
}

export function accessSessionTtlSeconds(): number {
  const raw = process.env.ACCESS_SESSION_TTL_SECONDS;
  const value = raw ? Number.parseInt(raw, 10) : DEFAULT_ACCESS_SESSION_TTL_SECONDS;
  return Number.isFinite(value) && value > 0
    ? value
    : DEFAULT_ACCESS_SESSION_TTL_SECONDS;
}

function accessCookieSecret(): string | null {
  const value = (
    process.env.ACCESS_SESSION_SECRET ??
    process.env.ACCESS_PASSWORD
  )?.trim();
  return value ? value : null;
}

function signAccessPayload(payload: string): string | null {
  const secret = accessCookieSecret();
  if (!secret) return null;
  return createHmac('sha256', secret)
    .update(payload)
    .digest('base64url');
}

export function isAccessPasswordConfigured(): boolean {
  return expectedPassword() !== null;
}

// Case-insensitive, trimmed comparison.
export function isValidAccessPassword(input: unknown): boolean {
  if (typeof input !== 'string') return false;
  const expected = expectedPassword();
  if (!expected) return false;
  const candidate = input.trim().toLowerCase();
  if (!candidate) return false;
  return candidate === expected.toLowerCase();
}

export function createAccessCookieValue(nowMs = Date.now()): string {
  const issuedAtSeconds = Math.floor(nowMs / 1000);
  const payload = String(issuedAtSeconds);
  const signature = signAccessPayload(payload);
  if (!signature) {
    throw new Error(
      'ACCESS_PASSWORD or ACCESS_SESSION_SECRET is required to create an access cookie.',
    );
  }
  return `${payload}.${signature}`;
}

export function isValidAccessCookie(value: unknown, nowMs = Date.now()): boolean {
  if (typeof value !== 'string') return false;
  const [issuedAtRaw, signature, extra] = value.split('.');
  if (!issuedAtRaw || !signature || extra) return false;

  const issuedAtSeconds = Number.parseInt(issuedAtRaw, 10);
  if (!Number.isFinite(issuedAtSeconds) || issuedAtSeconds <= 0) return false;

  const ageSeconds = Math.floor(nowMs / 1000) - issuedAtSeconds;
  if (ageSeconds < 0 || ageSeconds > accessSessionTtlSeconds()) return false;

  const expectedSignature = signAccessPayload(issuedAtRaw);
  if (!expectedSignature) return false;
  const expectedBuffer = Buffer.from(expectedSignature);
  const actualBuffer = Buffer.from(signature);
  return (
    expectedBuffer.length === actualBuffer.length &&
    timingSafeEqual(expectedBuffer, actualBuffer)
  );
}
