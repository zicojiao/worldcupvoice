from app.models import HeartbeatSessionRequest, MatchContext, StartSessionRequest


def test_start_session_request_is_gateway_only_with_match_context():
    request = StartSessionRequest(
        requester_id="1000",
        channel_name="test-channel",
        match_context=MatchContext(
            sport="football",
            title="Argentina vs France",
            competition="Demo",
            venue="Lusail Stadium",
            homeTeam="Argentina",
            awayTeam="France",
            broadcastNotes=["Keep the crowd sound audible."],
            storyline="Mbappe leads France back late.",
        ),
    )

    assert request.source_mode == "agora-gateway"
    assert request.match_context
    assert request.match_context.homeTeam == "Argentina"
    assert request.match_context.broadcastNotes == ["Keep the crowd sound audible."]


def test_heartbeat_session_request_accepts_session_or_agent_id():
    by_session = HeartbeatSessionRequest(session_id="session-1")
    by_agent = HeartbeatSessionRequest(agent_id="agent-1")

    assert by_session.session_id == "session-1"
    assert by_agent.agent_id == "agent-1"
