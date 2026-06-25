import { NextRequest, NextResponse } from 'next/server';
import { RtcTokenBuilder, RtcRole } from 'agora-token';
import { DEFAULT_AGENT_UID, DEFAULT_MATCH_FEED_UID } from '@/lib/agora';
import {
  ACCESS_COOKIE_NAME,
  isValidAccessCookie,
} from '@/lib/accessPassword';

const EXPIRATION_TIME_IN_SECONDS = 3600;
const DEFAULT_LIVE_CHANNEL_NAME = 'worldcup-live';

function getDefaultChannelName(): string {
  return (
    process.env.NEXT_PUBLIC_LIVE_CHANNEL_NAME ??
    process.env.LIVE_CHANNEL_NAME ??
    DEFAULT_LIVE_CHANNEL_NAME
  ).trim();
}

function getReservedUids(): Set<number> {
  return new Set([
    Number(process.env.NEXT_PUBLIC_AGENT_UID ?? DEFAULT_AGENT_UID),
    Number(process.env.NEXT_PUBLIC_MATCH_FEED_UID ?? DEFAULT_MATCH_FEED_UID),
  ]);
}

function parsePositiveUid(value: string | null): number | null {
  if (!value || !/^\d+$/.test(value)) return null;
  const parsed = Number.parseInt(value, 10);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
}

function randomViewerUid(reservedUids: Set<number>): number {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    const uid = Math.floor(Math.random() * 9_999_000) + 1000;
    if (!reservedUids.has(uid)) return uid;
  }
  throw new Error('Failed to generate a non-reserved viewer UID.');
}

export async function GET(request: NextRequest) {
  const accessCookie = request.cookies.get(ACCESS_COOKIE_NAME)?.value;
  if (!isValidAccessCookie(accessCookie)) {
    return NextResponse.json(
      { error: 'Access verification is required before issuing Agora tokens.' },
      { status: 401 },
    );
  }

  const APP_ID = process.env.NEXT_PUBLIC_AGORA_APP_ID;
  const APP_CERTIFICATE = process.env.NEXT_AGORA_APP_CERTIFICATE;

  if (!APP_ID || !APP_CERTIFICATE) {
    return NextResponse.json(
      { error: 'Agora credentials are not set' },
      { status: 500 },
    );
  }

  const { searchParams } = new URL(request.url);
  const reservedUids = getReservedUids();
  const parsedUid = parsePositiveUid(searchParams.get('uid'));
  const uid = parsedUid ?? randomViewerUid(reservedUids);
  if (reservedUids.has(uid)) {
    return NextResponse.json(
      { error: 'Requested UID is reserved for backend media or AI participants.' },
      { status: 400 },
    );
  }

  const defaultChannelName = getDefaultChannelName();
  const channelName = searchParams.get('channel') || defaultChannelName;
  if (channelName !== defaultChannelName) {
    return NextResponse.json(
      { error: 'Requested channel is not configured for this live booth.' },
      { status: 400 },
    );
  }

  const expirationTime =
    Math.floor(Date.now() / 1000) + EXPIRATION_TIME_IN_SECONDS;

  try {
    const token = RtcTokenBuilder.buildTokenWithRtm(
      APP_ID,
      APP_CERTIFICATE,
      channelName,
      uid.toString(),
      RtcRole.PUBLISHER,
      expirationTime,
      expirationTime,
    );

    return NextResponse.json({
      token,
      uid: uid.toString(),
      channel: channelName,
    });
  } catch (error) {
    console.error('Error generating Agora token:', error);
    return NextResponse.json(
      {
        error: 'Failed to generate Agora token',
        details: error instanceof Error ? error.message : String(error),
      },
      { status: 500 },
    );
  }
}
