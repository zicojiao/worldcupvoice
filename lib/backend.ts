export const BACKEND_SECRET_HEADER = 'X-WorldCupVoice-Backend-Secret';

export function getBackendUrl(): string {
  return (
    process.env.AGENT_BACKEND_URL ??
    process.env.NEXT_PUBLIC_AGENT_BACKEND_URL ??
    'http://localhost:8000'
  ).replace(/\/$/, '');
}

export function getBackendHeaders(): Record<string, string> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  const secret = process.env.BACKEND_API_SECRET?.trim();
  if (secret) {
    headers[BACKEND_SECRET_HEADER] = secret;
  }
  return headers;
}
