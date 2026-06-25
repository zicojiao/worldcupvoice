import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';

const projectRoot = process.cwd();
const defaultChannel = 'worldcup-live';
const defaultUid = '234567';
const defaultTtlSeconds = '2592000';

function loadEnvFile(filePath) {
  if (!fs.existsSync(filePath)) return;

  const lines = fs.readFileSync(filePath, 'utf8').split(/\r?\n/);
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;

    const match = trimmed.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);
    if (!match) continue;

    const [, key, rawValue] = match;
    if (process.env[key]) continue;

    process.env[key] = rawValue.trim().replace(/^['"]|['"]$/g, '');
  }
}

function readEnv(...names) {
  for (const name of names) {
    const value = process.env[name]?.trim();
    if (value) return value;
  }
  return undefined;
}

function fail(message) {
  console.error(message);
  console.error('');
  usage();
  process.exit(1);
}

function usage() {
  console.log(`Create an Agora Media Gateway RTMP stream key.

Usage:
  AGORA_CUSTOMER_ID=<id> AGORA_CUSTOMER_SECRET=<secret> pnpm run media-gateway:key

Reads .env.local automatically when present.

Optional:
  NEXT_PUBLIC_AGORA_APP_ID=<app-id>
  AGORA_MEDIA_GATEWAY_REGION=<region>
  NEXT_PUBLIC_LIVE_CHANNEL_NAME=${defaultChannel}
  NEXT_PUBLIC_MATCH_FEED_UID=${defaultUid}
  AGORA_MEDIA_GATEWAY_STREAM_KEY_TTL=${defaultTtlSeconds}

Choose the Media Gateway region closest to your encoder. Common values:
  eu, na, as, cn, jp, in

The generated key is for OBS/ffmpeg only. Do not commit it or put it in Vercel.
`);
}

if (process.argv.includes('--help') || process.argv.includes('-h')) {
  usage();
  process.exit(0);
}

loadEnvFile(path.join(projectRoot, '.env.local'));
loadEnvFile(path.join(projectRoot, '.env'));

const appId = readEnv('NEXT_PUBLIC_AGORA_APP_ID', 'AGORA_APP_ID');
const customerId = readEnv('AGORA_CUSTOMER_ID');
const customerSecret = readEnv('AGORA_CUSTOMER_SECRET');
const region = readEnv('AGORA_MEDIA_GATEWAY_REGION');
const channel = readEnv('NEXT_PUBLIC_LIVE_CHANNEL_NAME', 'LIVE_CHANNEL_NAME') || defaultChannel;
const uid = readEnv('NEXT_PUBLIC_MATCH_FEED_UID', 'MATCH_FEED_UID') || defaultUid;
const expiresAfter = Number.parseInt(
  readEnv('AGORA_MEDIA_GATEWAY_STREAM_KEY_TTL') || defaultTtlSeconds,
  10,
);

if (!appId) fail('Missing NEXT_PUBLIC_AGORA_APP_ID.');
if (!customerId) fail('Missing AGORA_CUSTOMER_ID.');
if (!customerSecret) fail('Missing AGORA_CUSTOMER_SECRET.');
if (!region) fail('Missing AGORA_MEDIA_GATEWAY_REGION. Choose the region closest to your encoder, for example eu, na, as, cn, jp, or in.');
if (!Number.isFinite(expiresAfter) || expiresAfter < 0) {
  fail('AGORA_MEDIA_GATEWAY_STREAM_KEY_TTL must be a non-negative integer.');
}

const endpoint = `https://api.agora.io/${region}/v1/projects/${appId}/rtls/ingress/streamkeys`;
const authorization = Buffer.from(`${customerId}:${customerSecret}`).toString('base64');
const requestId = crypto.randomUUID();
const body = {
  settings: {
    channel,
    uid: String(uid),
    expiresAfter,
  },
};

const response = await globalThis.fetch(endpoint, {
  method: 'POST',
  headers: {
    Accept: 'application/json',
    Authorization: `Basic ${authorization}`,
    'Content-Type': 'application/json',
    'X-Request-ID': requestId,
  },
  body: JSON.stringify(body),
});

const text = await response.text();
let payload;
try {
  payload = text ? JSON.parse(text) : {};
} catch {
  payload = { raw: text };
}

if (!response.ok || payload.status !== 'success' || !payload.data?.streamKey) {
  console.error(`Failed to create stream key. HTTP ${response.status}`);
  console.error(`X-Request-ID: ${response.headers.get('x-request-id') || requestId}`);
  console.error(JSON.stringify(payload, null, 2));
  process.exit(1);
}

const rtmpServer = `rtmp://rtls-ingress-prod-${region}.agoramdn.com/live`;
const { streamKey } = payload.data;

console.log('Agora Media Gateway stream key created.');
console.log('');
console.log(`Channel: ${payload.data.channel || channel}`);
console.log(`UID: ${payload.data.uid || uid}`);
console.log(`Expires after: ${payload.data.expiresAfter ?? expiresAfter} seconds`);
console.log('');
console.log(`RTMP server: ${rtmpServer}`);
console.log(`Stream key: ${streamKey}`);
console.log('');
console.log('Push the bundled sample clip:');
console.log(`RTMP_SERVER=${rtmpServer} RTMP_STREAM_KEY=${streamKey} pnpm run stream:sample`);
