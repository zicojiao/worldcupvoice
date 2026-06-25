import { NextResponse } from 'next/server';
import { StopConversationRequest } from '@/types/conversation';
import { getBackendHeaders, getBackendUrl } from '@/lib/backend';

export async function POST(request: Request) {
  try {
    const body: StopConversationRequest = await request.json();

    if (!body.agent_id && !body.session_id) {
      return NextResponse.json(
        { error: 'agent_id or session_id is required' },
        { status: 400 },
      );
    }

    const backendResponse = await fetch(`${getBackendUrl()}/sessions/stop`, {
      method: 'POST',
      headers: getBackendHeaders(),
      body: JSON.stringify({
        agent_id: body.agent_id,
        session_id: body.session_id,
      }),
      cache: 'no-store',
    });

    const payload = await backendResponse.json().catch(() => null);
    if (!backendResponse.ok) {
      return NextResponse.json(
        {
          error: payload?.detail ?? payload?.error ?? 'Failed to stop session',
          statusCode: backendResponse.status,
        },
        { status: backendResponse.status },
      );
    }

    return NextResponse.json(payload ?? { success: true });
  } catch (error) {
    console.error('Error stopping conversation:', error);
    return NextResponse.json(
      {
        error:
          error instanceof Error
            ? error.message
            : 'Failed to stop conversation',
      },
      { status: 500 },
    );
  }
}
