import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';

const projectRoot = process.cwd();
const samplesDir = path.join(projectRoot, 'samples');

// No video is bundled — the footage we tested with is copyrighted broadcast
// material, so it cannot be redistributed. Bring your own football clip:
// set RTMP_INPUT to its path, or drop any .mp4 into samples/.
function resolveInputClip() {
  const input = process.env.RTMP_INPUT?.trim();
  if (input) {
    return path.isAbsolute(input) ? input : path.join(projectRoot, input);
  }
  if (!fs.existsSync(samplesDir)) return null;
  const mp4 = fs
    .readdirSync(samplesDir)
    .filter((name) => name.toLowerCase().endsWith('.mp4'))
    .sort()[0];
  return mp4 ? path.join(samplesDir, mp4) : null;
}

function missingClipMessage() {
  return `No input clip found.

This repo does not ship a video — the footage we tested with is copyrighted
broadcast material, so it cannot be redistributed. Bring your own football clip:

  RTMP_STREAM_KEY=<key> RTMP_INPUT=/path/to/your-match.mp4 pnpm run stream:sample

Or drop any .mp4 into samples/ and it will be picked up automatically.
See samples/README.md for details.`;
}

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

function usage() {
  console.log(`Push a local football clip to Agora Media Gateway as a live RTMP source.

No video is bundled (copyright). Bring your own clip via RTMP_INPUT or samples/.

Usage:
  RTMP_STREAM_KEY=<your-key> RTMP_INPUT=/path/to/your-match.mp4 pnpm run stream:sample

Optional:
  RTMP_INPUT=<path-to-clip.mp4>   (defaults to the first .mp4 in samples/)
  RTMP_SERVER=rtmp://rtls-ingress-prod-<region>.agoramdn.com/live
  AGORA_MEDIA_GATEWAY_REGION=<region>
  STREAM_ONCE=1

If RTMP_SERVER is unset, this helper builds it from AGORA_MEDIA_GATEWAY_REGION.
Choose the region closest to your encoder or cloud RTMP source.

The stream key should be created with Agora Media Gateway REST API for:
  channel: worldcup-live
  uid: 234567

Create one with:
  pnpm run media-gateway:key
`);
}

if (process.argv.includes('--help') || process.argv.includes('-h')) {
  usage();
  process.exit(0);
}

loadEnvFile(path.join(projectRoot, '.env.local'));
loadEnvFile(path.join(projectRoot, '.env'));

const streamKey = process.env.RTMP_STREAM_KEY;
const region = readEnv('AGORA_MEDIA_GATEWAY_REGION');
const server =
  process.env.RTMP_SERVER || (region ? `rtmp://rtls-ingress-prod-${region}.agoramdn.com/live` : '');
const shouldLoop = process.env.STREAM_ONCE !== '1';

const samplePath = resolveInputClip();

if (!samplePath || !fs.existsSync(samplePath)) {
  console.error(missingClipMessage());
  process.exit(1);
}

if (!streamKey) {
  console.error('Missing RTMP_STREAM_KEY.');
  usage();
  process.exit(1);
}

if (!server) {
  console.error('Missing RTMP_SERVER or AGORA_MEDIA_GATEWAY_REGION.');
  usage();
  process.exit(1);
}

const publishUrl = `${server.replace(/\/+$/, '')}/${streamKey}`;
const args = [
  '-hide_banner',
  '-re',
  ...(shouldLoop ? ['-stream_loop', '-1'] : []),
  '-i',
  samplePath,
  '-map',
  '0:v:0',
  '-map',
  '0:a?',
  '-c:v',
  'libx264',
  '-preset',
  'veryfast',
  '-profile:v',
  'baseline',
  '-pix_fmt',
  'yuv420p',
  '-r',
  '30',
  '-g',
  '60',
  '-b:v',
  '5000k',
  '-maxrate',
  '5000k',
  '-bufsize',
  '10000k',
  '-c:a',
  'aac',
  '-ar',
  '48000',
  '-b:a',
  '128k',
  '-f',
  'flv',
  publishUrl,
];

console.log(`Pushing ${path.relative(projectRoot, samplePath)} to Agora Media Gateway...`);
console.log('Press Ctrl+C to stop streaming.');

const ffmpeg = spawn('ffmpeg', args, { stdio: 'inherit' });

ffmpeg.on('error', (error) => {
  if (error.code === 'ENOENT') {
    console.error('ffmpeg is not installed or not on PATH. Install it with: brew install ffmpeg');
    process.exit(1);
  }
  console.error(error);
  process.exit(1);
});

ffmpeg.on('exit', (code, signal) => {
  if (signal) {
    process.exit(0);
  }
  process.exit(code ?? 0);
});
