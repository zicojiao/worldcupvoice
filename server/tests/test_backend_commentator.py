import asyncio
import json
import pytest

from app.backend_commentator import (
    _AgoraAudioConsumerPacer,
    BackendVisionCommentator,
    FrameSnapshot,
    _agora_i420_frame_to_image,
    _build_visual_prompt,
    _comfort_noise_frame,
    _extract_response_text,
    _is_no_call,
    _is_repetitive_commentary,
    _resample_pcm_mono,
    _sample_rate_from_pcm_output_format,
    _transcript_payload,
    _trim_pcm_to_millisecond_boundary,
)
from app.config import Settings
from app.models import MatchContext


def test_extract_response_text_prefers_output_text():
    assert _extract_response_text({"output_text": "  A guard drives left.  "}) == (
        "A guard drives left."
    )


def test_extract_response_text_falls_back_to_output_content():
    payload = {
        "output": [
            {
                "content": [
                    {"type": "output_text", "text": "The ball is swung"},
                    {"type": "output_text", "text": "to the corner."},
                ]
            }
        ]
    }

    assert _extract_response_text(payload) == "The ball is swung to the corner."


def test_trim_pcm_to_millisecond_boundary():
    pcm = b"x" * 100

    assert len(_trim_pcm_to_millisecond_boundary(pcm, sample_rate=24000)) == 96


def test_sample_rate_from_pcm_output_format():
    assert _sample_rate_from_pcm_output_format("pcm_16000") == 16000
    assert _sample_rate_from_pcm_output_format("PCM_24000") == 24000
    assert _sample_rate_from_pcm_output_format("mp3_44100") is None


def test_resample_pcm_mono_changes_duration_bytes_to_target_rate():
    pcm_24k_100ms = b"\x00\x00" * 2400

    converted = _resample_pcm_mono(
        pcm_24k_100ms,
        source_rate=24000,
        target_rate=16000,
    )

    assert len(converted) == 3200


def test_comfort_noise_frame_is_low_level_nonzero_pcm():
    frame = _comfort_noise_frame(8, amplitude=16)

    assert len(frame) == 8
    assert frame != bytes(8)
    assert frame[:2] == (-16).to_bytes(2, byteorder="little", signed=True)
    assert frame[2:4] == (16).to_bytes(2, byteorder="little", signed=True)


def test_transcript_payload_matches_agent_toolkit_shape():
    payload = json.loads(
        _transcript_payload(text="A player cuts through the lane.", agent_uid=123456, turn_id=7)
    )

    assert payload["object"] == "assistant.transcription"
    assert payload["text"] == "A player cuts through the lane."
    assert payload["user_id"] == "123456"
    assert payload["turn_id"] == 7
    assert payload["turn_status"] == 1


def test_visual_prompt_uses_multi_frame_play_by_play_constraints():
    prompt = _build_visual_prompt(
        MatchContext(
            sport="football",
            title="Argentina vs France",
            competition="FIFA World Cup Qatar 2022 - Final",
            venue="Lusail Stadium",
            homeTeam="Argentina",
            awayTeam="France",
            storyline="Mbappe leads France back late.",
        ),
        samples=[
            FrameSnapshot(video_time=12.0, captured_at=1.0, image_base64="old"),
            FrameSnapshot(video_time=13.1, captured_at=2.0, image_base64="new"),
        ],
        previous_calls=["Messi carries it toward the box."],
    )

    assert "oldest first and newest last" in prompt
    assert "natural live broadcast cadence" in prompt
    assert "4 to 16 words" in prompt
    assert "Default to a grounded call" in prompt
    assert "Return exactly NO_CALL only" in prompt
    assert "live football play-by-play commentator" in prompt
    assert "Do not say the game is starting, kick-off, penalty" in prompt
    assert "Messi carries it toward the box." in prompt
    assert "13.1s" in prompt


def test_visual_prompt_includes_roster_map_and_identity_rules():
    prompt = _build_visual_prompt(
        MatchContext(
            sport="football",
            title="Argentina vs France",
            competition="FIFA World Cup Qatar 2022 - Final",
            venue="Lusail Stadium",
            homeTeam="Argentina",
            awayTeam="France",
            gameDate="2022-12-18",
            localTipTime="6:00 PM AST",
            finalScore="Argentina 3, France 3 - Argentina won 4-2 on penalties",
            homeTeamAbbr="ARG",
            awayTeamAbbr="FRA",
            homeJerseyColor="white and sky-blue striped Argentina shirts",
            awayJerseyColor="navy France shirts",
            homeRoster=[
                {
                    "number": "10",
                    "name": "Lionel Messi",
                    "shortName": "Messi",
                    "role": "starter",
                    "position": "FW",
                }
            ],
            awayRoster=[
                {
                    "number": "10",
                    "name": "Kylian Mbappe",
                    "shortName": "Mbappe",
                    "role": "starter",
                    "position": "LW",
                }
            ],
            playerIdentificationNotes=[
                "Use player names only when the shirt number or team kit is visually clear.",
            ],
            broadcastNotes=[
                "Use football vocabulary and keep the crowd audio breathing.",
            ],
            storyline="France chase the final late through Mbappe.",
        ),
        samples=[
            FrameSnapshot(video_time=22.0, captured_at=1.0, image_base64="frame"),
        ],
        previous_calls=[],
    )

    assert "Argentina uniforms: white and sky-blue striped Argentina shirts." in prompt
    assert "#10 Messi (Lionel Messi) [starter/FW]" in prompt
    assert "#10 Mbappe (Kylian Mbappe) [starter/LW]" in prompt
    assert "if a shirt number is readable" in prompt
    assert "use that player's short name" in prompt
    assert "Use player names only when the shirt number" in prompt
    assert "describe roles generically" in prompt
    assert "Broadcast notes:" in prompt
    assert "football vocabulary" in prompt


def test_no_call_detection_allows_model_to_stay_silent():
    assert _is_no_call("NO_CALL")
    assert _is_no_call("No call.")


def test_repetitive_commentary_detection_blocks_same_action():
    previous = ["Messi carries it toward the box."]

    assert _is_repetitive_commentary(
        "Messi carries toward the box.",
        previous,
    )
    assert not _is_repetitive_commentary(
        "Mbappe breaks down the left.",
        previous,
    )


def test_tts_description_reports_elevenlabs_provider():
    commentator = BackendVisionCommentator(
        settings=Settings(
            agora_app_id="app-id",
            agora_app_certificate="app-cert",
            tts_provider="elevenlabs",
            elevenlabs_voice_id="voice-id",
            elevenlabs_model="eleven_flash_v2_5",
        ),
        channel_name="channel",
        agent_uid=123456,
        match_context=None,
        media_uid=234567,
    )

    assert commentator._tts_description() == "elevenlabs:eleven_flash_v2_5:voice-id"


@pytest.mark.asyncio
async def test_publish_audio_sends_pcm_frames_sequentially():
    commentator = BackendVisionCommentator(
        settings=Settings(
            agora_app_id="app-id",
            agora_app_certificate="app-cert",
            commentary_audio_sample_rate=24000,
            commentary_audio_consume_interval_ms=1000,
        ),
        channel_name="channel",
        agent_uid=123456,
        match_context=None,
        media_uid=234567,
    )
    sent_chunks: list[tuple[bytes, int, int]] = []

    def fake_push_audio_chunk(
        _connection: object,
        chunk: bytes,
        sample_rate: int,
        *,
        present_time_ms: int,
    ) -> int:
        sent_chunks.append((bytes(chunk), sample_rate, present_time_ms))
        return 0

    async def no_sleep(_delay: float) -> None:
        return None

    commentator._push_audio_chunk = fake_push_audio_chunk  # type: ignore[method-assign]
    commentator._sleep_until_stop = no_sleep  # type: ignore[method-assign]

    pcm_2400ms = b"x" * int(24000 * 1 * 2 * 2400 / 1000)

    sent = await commentator._publish_audio(object(), pcm_2400ms)

    # Audio is paced as ~100ms PCM chunks (4800 bytes at 24kHz mono) sent in real
    # time, with a constant present_time_ms of 0 so the SDK plays them immediately
    # instead of treating per-utterance timestamps as scheduled in the past.
    bytes_per_100ms = int(24000 * 1 * 2 * 100 / 1000)
    assert sent == len(pcm_2400ms)
    assert len(sent_chunks) == 24
    assert {len(chunk) for chunk, _rate, _time in sent_chunks} == {bytes_per_100ms}
    assert {rate for _chunk, rate, _time in sent_chunks} == {24000}
    assert {time_ms for _chunk, _rate, time_ms in sent_chunks} == {0}
    stats = commentator.stats()
    assert stats.audio_buffer_ms == 0
    assert stats.last_audio_duration_ms == 2400


@pytest.mark.asyncio
async def test_publish_audio_queues_to_audio_consumer_pacer_when_available():
    commentator = BackendVisionCommentator(
        settings=Settings(
            agora_app_id="app-id",
            agora_app_certificate="app-cert",
            commentary_audio_sample_rate=24000,
            commentary_audio_consume_interval_ms=60,
        ),
        channel_name="channel",
        agent_uid=123456,
        match_context=None,
        media_uid=234567,
    )

    class FakePacer:
        def __init__(self):
            self.queued: list[bytes] = []

        def buffer_ms(self) -> int:
            return 120

        async def enqueue(self, pcm: bytes) -> int:
            self.queued.append(bytes(pcm))
            return len(pcm)

    pacer = FakePacer()
    commentator._audio_pacer = pacer  # type: ignore[assignment]
    pcm = b"x" * 1000

    sent = await commentator._publish_audio(object(), pcm)

    # 24kHz mono PCM is 480 bytes per 10ms. The pacer path trims to that
    # boundary and returns immediately instead of sleeping for playback time.
    assert sent == 960
    assert [len(chunk) for chunk in pacer.queued] == [960]
    assert commentator._last_audio_duration_ms == 20


@pytest.mark.asyncio
async def test_agora_audio_consumer_pacer_buffers_and_consumes_tts_pcm():
    class FakeSender:
        def __init__(self):
            self.frames: list[bytes] = []

        def send_audio_pcm_data(self, frame):
            self.frames.append(bytes(frame.data))
            return 0

    class FakeConnection:
        def __init__(self):
            self._audio_sender = FakeSender()

    connection = FakeConnection()
    pacer = _AgoraAudioConsumerPacer(
        connection=connection,
        sample_rate=24000,
        consume_interval_ms=60,
        keepalive=True,
        stop_event=asyncio.Event(),
        channel_name="channel",
    )

    assert pacer.frame_size == 480
    assert pacer.consume_interval_ms == 60

    pcm_240ms = b"x" * int(24000 * 1 * 2 * 240 / 1000)
    await pacer.enqueue(pcm_240ms)

    assert pacer.buffer_ms() == 240
    result = pacer._consume_once()

    assert result == 0
    assert [len(frame) for frame in connection._audio_sender.frames] == [4800]
    assert pacer.buffer_ms() == 140
    assert pacer.stats()["audio_consume_calls"] == 1
    assert pacer.stats()["audio_consume_errors"] == 0
    assert pacer.stats()["audio_send_calls"] == 1
    assert pacer.stats()["last_audio_send_ms"] == 100
    assert pacer.stats()["last_audio_duration_ms"] == 240


def test_agora_audio_consumer_pacer_sends_keepalive_when_empty():
    class FakeSender:
        def __init__(self):
            self.frames: list[bytes] = []

        def send_audio_pcm_data(self, frame):
            self.frames.append(bytes(frame.data))
            return 0

    class FakeConnection:
        def __init__(self):
            self._audio_sender = FakeSender()

    connection = FakeConnection()
    pacer = _AgoraAudioConsumerPacer(
        connection=connection,
        sample_rate=16000,
        consume_interval_ms=40,
        keepalive=True,
        stop_event=asyncio.Event(),
        channel_name="channel",
    )

    result = pacer._consume_once()

    assert result in {-2, 0}
    assert [len(frame) for frame in connection._audio_sender.frames] == [1280]
    assert pacer.stats()["audio_keepalive_calls"] == 1
    assert pacer.stats()["audio_send_calls"] == 1


def test_agora_audio_consumer_pacer_stays_quiet_when_keepalive_disabled():
    class FakeSender:
        def __init__(self):
            self.frames: list[bytes] = []

        def send_audio_pcm_data(self, frame):
            self.frames.append(bytes(frame.data))
            return 0

    class FakeConnection:
        def __init__(self):
            self._audio_sender = FakeSender()

    connection = FakeConnection()
    pacer = _AgoraAudioConsumerPacer(
        connection=connection,
        sample_rate=16000,
        consume_interval_ms=40,
        keepalive=False,
        stop_event=asyncio.Event(),
        channel_name="channel",
    )

    result = pacer._consume_once()

    assert result in {-2, 0}
    assert connection._audio_sender.frames == []
    assert pacer.stats()["audio_keepalive_calls"] == 0
    assert pacer.stats()["audio_send_calls"] == 0


@pytest.mark.asyncio
async def test_agora_audio_consumer_pacer_does_not_clear_empty_buffer_for_long_clip():
    class FakeSender:
        def send_audio_pcm_data(self, _frame):
            return 0

    class FakeConnection:
        def __init__(self):
            self._audio_sender = FakeSender()

    pacer = _AgoraAudioConsumerPacer(
        connection=FakeConnection(),
        sample_rate=24000,
        consume_interval_ms=60,
        keepalive=False,
        stop_event=asyncio.Event(),
        channel_name="channel",
        max_buffer_seconds=1.0,
    )

    pcm_2000ms = b"x" * int(24000 * 1 * 2 * 2000 / 1000)

    await pacer.enqueue(pcm_2000ms)

    assert pacer.buffer_ms() == 2000
    assert pacer.stats()["audio_buffer_clears"] == 0

    await pacer.enqueue(pcm_2000ms)

    assert pacer.buffer_ms() == 2000
    assert pacer.stats()["audio_buffer_clears"] == 1


@pytest.mark.asyncio
async def test_commentary_publishes_transcript_before_audio():
    commentator = BackendVisionCommentator(
        settings=Settings(
            agora_app_id="app-id",
            agora_app_certificate="app-cert",
            commentary_audio_sample_rate=24000,
        ),
        channel_name="channel",
        agent_uid=123456,
        match_context=None,
        media_uid=234567,
    )
    events: list[str] = []

    async def describe(_samples: list[FrameSnapshot]) -> str:
        events.append("describe")
        return "Messi drives into space."

    async def synthesize(text: str) -> bytes:
        assert text == "Messi drives into space."
        events.append("tts")
        return b"x" * int(24000 * 1 * 2 * 120 / 1000)

    async def publish_transcript(_connection: object, text: str) -> None:
        assert text == "Messi drives into space."
        events.append("transcript")

    async def publish_audio(_connection: object, pcm: bytes) -> int:
        assert pcm
        events.append("audio")
        return len(pcm)

    commentator._describe_frames = describe  # type: ignore[method-assign]
    commentator._synthesize_speech = synthesize  # type: ignore[method-assign]
    commentator._publish_transcript = publish_transcript  # type: ignore[method-assign]
    commentator._publish_audio = publish_audio  # type: ignore[method-assign]
    await commentator._store_frame(
        FrameSnapshot(video_time=1.0, captured_at=1.0, image_base64="frame")
    )

    await commentator._commentary_from_latest_frames(object())

    # Transcript is published before audio synthesis so the text appears
    # immediately while audio is still being produced.
    assert events == ["describe", "transcript", "tts", "audio"]


def test_commentator_stats_defaults_to_zero():
    commentator = BackendVisionCommentator(
        settings=Settings(
            agora_app_id="app-id",
            agora_app_certificate="app-cert",
        ),
        channel_name="channel",
        agent_uid=123456,
        match_context=None,
        media_uid=234567,
    )

    stats = commentator.stats()

    assert stats.frames_sampled == 0
    assert stats.vision_requests == 0
    assert stats.tts_requests == 0
    assert stats.audio_sample_rate == 24000
    assert stats.audio_consume_interval_ms == 60


def test_openai_rate_limit_pause_uses_exponential_backoff(monkeypatch):
    monkeypatch.setattr("app.backend_commentator.time.monotonic", lambda: 100.0)
    commentator = BackendVisionCommentator(
        settings=Settings(
            agora_app_id="app-id",
            agora_app_certificate="app-cert",
        ),
        channel_name="channel",
        agent_uid=123456,
        match_context=None,
        media_uid=234567,
    )

    commentator._pause_after_openai_rate_limit(None)
    assert commentator._vision_rate_limit_errors == 1
    assert commentator._vision_rate_limit_resume_at == 108.0

    commentator._pause_after_openai_rate_limit(None)
    assert commentator._vision_rate_limit_errors == 2
    assert commentator._vision_rate_limit_resume_at == 116.0


def test_openai_rate_limit_pause_honors_retry_after(monkeypatch):
    monkeypatch.setattr("app.backend_commentator.time.monotonic", lambda: 100.0)
    commentator = BackendVisionCommentator(
        settings=Settings(
            agora_app_id="app-id",
            agora_app_certificate="app-cert",
        ),
        channel_name="channel",
        agent_uid=123456,
        match_context=None,
        media_uid=234567,
    )

    commentator._pause_after_openai_rate_limit("12")
    assert commentator._vision_rate_limit_resume_at == 112.0


def test_agora_i420_frame_to_image_converts_raw_rtc_frame():
    class Frame:
        width = 2
        height = 2
        y_stride = 2
        u_stride = 1
        v_stride = 1
        y_buffer = bytes([128, 128, 128, 128])
        u_buffer = bytes([128])
        v_buffer = bytes([128])
        rotation = 0

    image = _agora_i420_frame_to_image(Frame())

    assert image.size == (2, 2)
    assert image.getpixel((0, 0)) == (128, 128, 128)
