import { NextRequest, NextResponse } from 'next/server';
import {
  AgentErrorResponse,
  AgentResponse,
  ClientStartRequest,
} from '@/types/conversation';
import { DEFAULT_AGENT_UID, DEFAULT_MATCH_FEED_UID } from '@/lib/agora';
import { isValidAccessPassword } from '@/lib/accessPassword';
import { getBackendHeaders, getBackendUrl } from '@/lib/backend';

const BACKEND_START_TIMEOUT_MS = 45_000;

function toErrorResponse(error: unknown, status = 502): NextResponse {
  const message =
    error instanceof Error ? error.message : 'Failed to start AI commentator';
  return NextResponse.json(
    {
      error: message,
      detail:
        status === 502
          ? 'The Python Agora RTC backend is not reachable or rejected the session.'
          : status === 504
            ? 'The Python Agora RTC backend did not answer the start request in time.'
          : undefined,
      statusCode: status,
    } as AgentErrorResponse,
    { status },
  );
}

export async function POST(request: NextRequest) {
  try {
    const body: ClientStartRequest = await request.json();
    const {
      requester_id,
      channel_name,
      match_context,
      access_password,
    } = body;

    // Access gate while the live booth is in private preview.
    if (!isValidAccessPassword(access_password)) {
      return NextResponse.json(
        { error: 'Incorrect access password.', statusCode: 401 } as AgentErrorResponse,
        { status: 401 },
      );
    }

    if (!channel_name || !requester_id) {
      return NextResponse.json(
        { error: 'channel_name and requester_id are required' },
        { status: 400 },
      );
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(
      () => controller.abort(),
      BACKEND_START_TIMEOUT_MS,
    );

    const backendResponse = await fetch(
      `${getBackendUrl()}/sessions/start`,
      {
        method: 'POST',
        headers: getBackendHeaders(),
        body: JSON.stringify({
          requester_id,
          channel_name,
          source_mode: 'agora-gateway',
          match_context,
          agent_uid: Number(
            process.env.NEXT_PUBLIC_AGENT_UID ?? DEFAULT_AGENT_UID,
          ),
          media_uid: Number(
            process.env.NEXT_PUBLIC_MATCH_FEED_UID ?? DEFAULT_MATCH_FEED_UID,
          ),
        }),
        cache: 'no-store',
        signal: controller.signal,
      },
    ).finally(() => clearTimeout(timeoutId));

    const payload = await backendResponse.json().catch(() => null);
    if (!backendResponse.ok) {
      const message =
        payload?.detail ?? payload?.error ?? 'Backend failed to start';
      return NextResponse.json(
        {
          error: message,
          statusCode: backendResponse.status,
        } as AgentErrorResponse,
        { status: backendResponse.status },
      );
    }

    return NextResponse.json(payload as AgentResponse);
  } catch (error) {
    console.error('Error starting AI commentator:', error);
    if (error instanceof Error && error.name === 'AbortError') {
      return toErrorResponse(
        new Error('Backend start timed out. Railway may still be warming up or overloaded.'),
        504,
      );
    }
    return toErrorResponse(error);
  }
}
