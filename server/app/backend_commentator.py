import asyncio
import base64
from collections import deque
from dataclasses import dataclass
import io
import json
import logging
import os
import re
import threading
import time
from types import SimpleNamespace
import audioop

import httpx
from agora_agent.agentkit.token import ROLE_PUBLISHER, generate_rtc_token
from PIL import Image

from .agora_region import area_code_value
from .commentator_profiles import CommentatorProfile
from .config import Settings
from .models import CommentatorStats, MatchContext

logger = logging.getLogger(__name__)


@dataclass
class _TtsStreamResult:
    publish_ms: int
    sent_bytes: int
    received_bytes: int
    duration_ms: int


OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
OPENAI_SPEECH_URL = "https://api.openai.com/v1/audio/speech"
ELEVENLABS_SPEECH_URL = "https://api.elevenlabs.io/v1/text-to-speech"
FISH_AUDIO_SPEECH_URL = "https://api.fish.audio/v1/tts"
PCM_CHANNELS = 1
PCM_BYTES_PER_SAMPLE = 2
TRANSCRIPT_TURN_END = 1
OPENAI_RATE_LIMIT_BASE_BACKOFF_SECONDS = 8.0
OPENAI_RATE_LIMIT_MAX_BACKOFF_SECONDS = 60.0
AI_AUDIO_HEALTH_LOG_SECONDS = 2.0
AI_AUDIO_SLOW_SEND_GAP_MS = 120
AI_AUDIO_SLOW_SEND_DURATION_MS = 80
# Streaming fallback frame size when the Agora AudioConsumer pacer is not
# available. Normal live sessions use AudioConsumer so generation and playback
# do not block each other.
AI_AUDIO_SEND_CHUNK_MS = 100


@dataclass(frozen=True)
class FrameSnapshot:
    video_time: float
    captured_at: float
    image_base64: str


def _extract_response_text(payload: dict) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    parts: list[str] = []
    for item in payload.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue
            text = content.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
    return " ".join(parts).strip()


def _trim_pcm_to_millisecond_boundary(
    pcm: bytes,
    *,
    sample_rate: int,
    channels: int = PCM_CHANNELS,
) -> bytes:
    bytes_per_ms = int(sample_rate * channels * PCM_BYTES_PER_SAMPLE / 1000)
    if bytes_per_ms <= 0:
        return b""
    usable = len(pcm) - (len(pcm) % bytes_per_ms)
    return pcm[:usable]


def _trim_pcm_to_10ms_boundary(
    pcm: bytes,
    *,
    sample_rate: int,
    channels: int = PCM_CHANNELS,
) -> bytes:
    bytes_per_10ms = int(sample_rate * channels * PCM_BYTES_PER_SAMPLE * 10 / 1000)
    if bytes_per_10ms <= 0:
        return b""
    usable = len(pcm) - (len(pcm) % bytes_per_10ms)
    return pcm[:usable]


def _resample_pcm_mono(
    pcm: bytes,
    *,
    source_rate: int,
    target_rate: int,
) -> bytes:
    if not pcm or source_rate <= 0 or target_rate <= 0:
        return b""
    if source_rate == target_rate:
        return _trim_pcm_to_millisecond_boundary(pcm, sample_rate=target_rate)
    converted, _state = audioop.ratecv(
        pcm,
        PCM_BYTES_PER_SAMPLE,
        PCM_CHANNELS,
        source_rate,
        target_rate,
        None,
    )
    return _trim_pcm_to_millisecond_boundary(converted, sample_rate=target_rate)


def _sample_rate_from_pcm_output_format(output_format: str) -> int | None:
    match = re.fullmatch(r"pcm_(\d+)", output_format.strip().lower())
    if not match:
        return None
    return int(match.group(1))


def _comfort_noise_frame(size: int, *, amplitude: int = 16) -> bytes:
    if size <= 0:
        return b""
    data = bytearray(size)
    for offset in range(0, size - 1, PCM_BYTES_PER_SAMPLE):
        sample_index = offset // PCM_BYTES_PER_SAMPLE
        sample = amplitude if sample_index % 2 else -amplitude
        data[offset : offset + PCM_BYTES_PER_SAMPLE] = sample.to_bytes(
            PCM_BYTES_PER_SAMPLE,
            byteorder="little",
            signed=True,
        )
    return bytes(data)


def _push_audio_chunk_to_connection(
    connection: object,
    chunk: bytes,
    sample_rate: int,
    *,
    present_time_ms: int,
) -> int:
    from agora.rtc.agora_base import PcmAudioFrame

    sender = getattr(connection, "_audio_sender", None)
    if sender is None:
        return -1001

    frame = PcmAudioFrame()
    frame.data = bytearray(chunk)
    frame.sample_rate = sample_rate
    frame.number_of_channels = PCM_CHANNELS
    frame.bytes_per_sample = PCM_BYTES_PER_SAMPLE
    frame.timestamp = 0
    frame.samples_per_channel = len(chunk) // (PCM_CHANNELS * PCM_BYTES_PER_SAMPLE)
    frame.present_time_ms = present_time_ms
    return sender.send_audio_pcm_data(frame)


def _transcript_payload(
    *, text: str, agent_uid: int, turn_id: int, language: str = "en"
) -> bytes:
    payload = {
        "object": "assistant.transcription",
        "text": text,
        "start_ms": 0,
        "duration_ms": 0,
        "language": language,
        "turn_id": turn_id,
        "stream_id": 0,
        "user_id": str(agent_uid),
        "words": None,
        "quiet": False,
        "turn_seq_id": turn_id,
        "turn_status": TRANSCRIPT_TURN_END,
    }
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _build_visual_prompt(
    match: MatchContext | None,
    *,
    samples: list[FrameSnapshot],
    previous_calls: list[str],
    profile: CommentatorProfile | None = None,
) -> str:
    if match is None:
        context = "Game context: the live sports feed."
    else:
        context = _build_match_context_text(match)

    latest_time = samples[-1].video_time if samples else 0.0
    previous = "\n".join(f"- {call}" for call in previous_calls[-5:]) or "- none"
    if profile and profile.language.startswith("zh"):
        return (
            "你是实时足球解说员，不是图片说明员。\n"
            f"解说员角色：{profile.label}。\n"
            f"风格要求：{profile.style_prompt}\n"
            f"{context}\n"
            f"当前视频源时间：{latest_time:.1f} 秒。\n"
            "你会看到一小段连续画面，顺序是从旧到新。只解说最新可见动作："
            "持球推进、盘带、传球、斜传、传中、射门、扑救、解围、逼抢、反击、"
            "防线移动、庆祝或球员重新组织。快节奏时短句，发展中的进攻可以稍长，"
            "通常 8 到 24 个汉字，最多一句。\n"
            "只要画面里能看清比赛、球员、球场或球权区域，就给出有依据的解说。"
            "只有在最新画面不可读、没有足球动作、或明显是静态暂停/纯观众镜头时，"
            "才只返回 NO_CALL。\n"
            "写之前先检查持球人、传球人、射门人、门将和最近防守人的球衣号码。"
            "如果号码、球衣颜色和阵容信息能对应，就用球员短名；看不清号码时，"
            "用位置或角色描述，不要编球员名。\n"
            "除非最新画面明确支持，不要说开球、点球、进球、扳平、犯规、比分、"
            "场外声音或画面外事件。已知最终比分只是背景元数据，不要当成实时比分播报。\n"
            "避免重复最近这些解说：\n"
            f"{previous}"
        )
    if profile and profile.language.startswith("fr"):
        return (
            "Tu es un commentateur football en direct, pas un rédacteur de légende d'image.\n"
            f"Profil du commentateur : {profile.label}.\n"
            f"Style demandé : {profile.style_prompt}\n"
            f"{context}\n"
            f"Temps actuel dans la source vidéo : {latest_time:.1f} s.\n"
            "Tu vois une courte rafale d'images, de la plus ancienne à la plus récente. "
            "Commente uniquement l'action la plus récente visible : conduite de balle, "
            "dribble, passe, centre, tir, arrêt, dégagement, pressing, contre-attaque, "
            "ligne défensive, célébration ou réorganisation des joueurs. Rythme de direct : "
            "phrases courtes quand ça va vite, un peu plus développées quand l'action se "
            "construit, généralement 4 à 16 mots, une phrase maximum.\n"
            "Fais un commentaire ancré dans l'image dès qu'un match, des joueurs, le terrain "
            "ou la zone du ballon sont lisibles. Retourne exactement NO_CALL seulement si "
            "la dernière image est illisible, qu'aucune action de football n'est visible, "
            "ou que la scène est clairement un arrêt de jeu statique, un ralenti, ou un plan "
            "foule sans changement visible.\n"
            "Avant d'écrire, inspecte les numéros visibles du porteur, du passeur, du tireur, "
            "du gardien et du défenseur le plus proche. Si le numéro, le maillot et le contexte "
            "correspondent à l'effectif, utilise le nom court du joueur. Si ce n'est pas clair, "
            "décris le rôle sans inventer de nom.\n"
            "Ne dis pas coup d'envoi, penalty, but, égalisation, faute, score, son du stade "
            "ou événement hors champ sauf si la dernière image le montre clairement. Le score "
            "final connu est une métadonnée privée, pas un score en direct à annoncer.\n"
            "Commentaires récents à éviter de répéter :\n"
            f"{previous}"
        )
    return (
        "You are a live football play-by-play commentator, not an image captioner.\n"
        f"Commentator profile: {profile.label if profile else 'Default sportscaster'}.\n"
        f"Style guide: {profile.style_prompt if profile else 'Use grounded live broadcast play-by-play.'}\n"
        f"{context}\n"
        f"Current video clock in the source: {latest_time:.1f}s.\n"
        "You are given a short burst of frames, oldest first and newest last. "
        "Call the newest visible live action: ball movement, dribble, pass, cross, "
        "shot, save, clearance, press, counterattack, defensive line, celebration, "
        "crowd surge, or players organizing for the next phase. Use natural live broadcast "
        "cadence: short when the action is fast, longer when the play is developing, usually "
        "4 to 16 words, one sentence max. It is okay to sound clipped, urgent, or "
        "mid-play.\n"
        "Default to a grounded call when a live game, players, pitch, or "
        "ball-side action is visible. Return exactly NO_CALL only when the newest "
        "frame is not readable, no football action is visible, or the scene is clearly "
        "a static timeout/replay/crowd-only shot with no new visible change.\n"
        "Before writing, inspect visible shirt numbers on the ball carrier, "
        "passer, crosser, shooter, goalkeeper, and nearest defender. Naming priority: "
        "if a shirt number is readable and the team kit matches the roster "
        "map, use that player's short name instead of a generic role. If the "
        "number is not readable, fall back to a generic role.\n"
        "Do not say the game is starting, kick-off, penalty, goal, or equaliser unless "
        "the newest frame visibly supports that event. Do not invent "
        "player names, fouls, sounds, scores, or off-screen events. Use the roster "
        "map only when the shirt number, kit color, or possession context is "
        "visually clear. If shirt or scoreboard text is unclear, describe roles "
        "generically. Treat the known final score as private match metadata, not "
        "the live score to announce.\n"
        "Recent calls to avoid repeating:\n"
        f"{previous}"
    )


def _build_match_context_text(match: MatchContext) -> str:
    detail_parts = [
        f"{match.awayTeam} at {match.homeTeam}",
        match.competition,
        f"at {match.venue}",
    ]
    if match.gameDate:
        detail_parts.append(match.gameDate)
    if match.localTipTime:
        detail_parts.append(f"tip {match.localTipTime}")
    if match.finalScore:
        detail_parts.append(f"known final metadata: {match.finalScore}")

    lines = [
        f"Game context: {', '.join(part for part in detail_parts if part)}.",
        f"Storyline: {match.storyline}",
    ]
    if match.homeJerseyColor:
        lines.append(f"{match.homeTeam} uniforms: {match.homeJerseyColor}.")
    if match.awayJerseyColor:
        lines.append(f"{match.awayTeam} uniforms: {match.awayJerseyColor}.")

    home_roster = _format_roster(
        label=f"{match.homeTeamAbbr or match.homeTeam} player map",
        players=match.homeRoster,
    )
    away_roster = _format_roster(
        label=f"{match.awayTeamAbbr or match.awayTeam} player map",
        players=match.awayRoster,
    )
    if home_roster:
        lines.append(home_roster)
    if away_roster:
        lines.append(away_roster)
    if match.playerIdentificationNotes:
        notes = " ".join(f"{index + 1}) {note}" for index, note in enumerate(match.playerIdentificationNotes))
        lines.append(f"Player identification rules: {notes}")
    if match.broadcastNotes:
        notes = " ".join(f"{index + 1}) {note}" for index, note in enumerate(match.broadcastNotes))
        lines.append(f"Broadcast notes: {notes}")

    return "\n".join(lines)


def _format_roster(*, label: str, players: list[object]) -> str:
    if not players:
        return ""

    entries: list[str] = []
    for player in players:
        role = getattr(player, "role", "")
        name = getattr(player, "name", "")
        short_name = getattr(player, "shortName", name)
        number = getattr(player, "number", "")
        position = getattr(player, "position", None)
        notes = getattr(player, "notes", None)
        detail = f"#{number} {short_name}"
        if name and short_name != name:
            detail += f" ({name})"
        role_bits = [bit for bit in (role, position) if bit]
        if role_bits:
            detail += f" [{'/'.join(role_bits)}]"
        if notes:
            detail += f" - {notes}"
        entries.append(detail)

    return f"{label}: " + "; ".join(entries) + "."


def _plane_bytes(buffer: object, *, stride: int, width: int, height: int) -> bytes:
    raw = bytes(buffer or b"")
    stride = stride or width
    if stride == width:
        return raw[: width * height]
    return b"".join(raw[row * stride : row * stride + width] for row in range(height))


def _agora_i420_frame_to_image(frame: object) -> Image.Image:
    width = int(getattr(frame, "width", 0) or 0)
    height = int(getattr(frame, "height", 0) or 0)
    if width <= 0 or height <= 0:
        raise RuntimeError("Agora video frame is missing dimensions.")

    chroma_width = max(1, width // 2)
    chroma_height = max(1, height // 2)
    y = _plane_bytes(
        getattr(frame, "y_buffer", b""),
        stride=int(getattr(frame, "y_stride", width) or width),
        width=width,
        height=height,
    )
    u = _plane_bytes(
        getattr(frame, "u_buffer", b""),
        stride=int(getattr(frame, "u_stride", chroma_width) or chroma_width),
        width=chroma_width,
        height=chroma_height,
    )
    v = _plane_bytes(
        getattr(frame, "v_buffer", b""),
        stride=int(getattr(frame, "v_stride", chroma_width) or chroma_width),
        width=chroma_width,
        height=chroma_height,
    )
    if len(y) < width * height or len(u) < chroma_width * chroma_height or len(v) < chroma_width * chroma_height:
        raise RuntimeError("Agora video frame planes are smaller than expected.")

    # Convert planar I420 -> RGB using Pillow's C-level YCbCr conversion instead
    # of a per-pixel Python loop. The old loop held the GIL for hundreds of ms on
    # every sampled frame, which froze the asyncio event loop and starved AI audio
    # pacing (choppy commentary). NEAREST chroma upsampling reproduces the exact
    # output of the previous `u[uv_row + col // 2]` indexing. Pillow's YCbCr->RGB
    # uses the same full-range JFIF coefficients (1.402 / 0.344136 / 0.714136 /
    # 1.772) the loop used.
    y_img = Image.frombytes("L", (width, height), bytes(y[: width * height]))
    u_img = Image.frombytes(
        "L", (chroma_width, chroma_height), bytes(u[: chroma_width * chroma_height])
    ).resize((width, height), Image.Resampling.NEAREST)
    v_img = Image.frombytes(
        "L", (chroma_width, chroma_height), bytes(v[: chroma_width * chroma_height])
    ).resize((width, height), Image.Resampling.NEAREST)
    image = Image.merge("YCbCr", (y_img, u_img, v_img)).convert("RGB")
    rotation = int(getattr(frame, "rotation", 0) or 0)
    if rotation in {90, 180, 270}:
        image = image.rotate(-rotation, expand=True)
    return image


def _agora_frame_to_jpeg_base64(frame: object, *, max_width: int, quality: int = 72) -> str:
    image = _agora_i420_frame_to_image(frame)
    if image.width > max_width:
        height = max(1, round(image.height * (max_width / image.width)))
        image = image.resize((max_width, height), Image.Resampling.LANCZOS)

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality, optimize=True)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


class _AgoraRemoteFrameObserver:
    def __init__(
        self,
        *,
        loop: asyncio.AbstractEventLoop,
        queue: asyncio.Queue[FrameSnapshot],
        media_uid: int,
        sample_seconds: float,
        max_width: int,
        jpeg_quality: int,
    ):
        self._loop = loop
        self._queue = queue
        self._media_uid = str(media_uid)
        self._sample_seconds = sample_seconds
        self._max_width = max_width
        self._jpeg_quality = jpeg_quality
        self._last_sample_at = 0.0
        self._lock = threading.Lock()
        self.frames_seen = 0
        self.frames_sampled = 0

    def on_frame(self, channel_id: str | None, remote_uid: str, frame: object) -> None:
        if str(remote_uid) != self._media_uid:
            return
        now = time.monotonic()
        with self._lock:
            self.frames_seen += 1
            if now - self._last_sample_at < self._sample_seconds:
                return
            self._last_sample_at = now

        try:
            image_base64 = _agora_frame_to_jpeg_base64(
                frame,
                max_width=self._max_width,
                quality=self._jpeg_quality,
            )
            snapshot = FrameSnapshot(
                video_time=float(getattr(frame, "render_time_ms", 0) or 0) / 1000,
                captured_at=now,
                image_base64=image_base64,
            )
            self.frames_sampled += 1
            self._loop.call_soon_threadsafe(self._enqueue, snapshot)
        except Exception:
            logger.warning(
                "Failed to convert Agora RTC frame channel=%s remote_uid=%s",
                channel_id,
                remote_uid,
                exc_info=True,
            )

    def _enqueue(self, snapshot: FrameSnapshot) -> None:
        if self._queue.full():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        self._queue.put_nowait(snapshot)


class _MeasuredPcmSender:
    def __init__(self, sender: object, *, sample_rate: int):
        self._sender = sender
        self._sample_rate = sample_rate
        self.send_calls = 0
        self.send_errors = 0
        self.sent_audio_ms = 0
        self.last_send_ms: int | None = None
        self.last_send_ret: int | None = None
        self.last_send_gap_ms: int | None = None
        self.max_send_gap_ms = 0
        self.slow_send_gaps = 0
        self.last_send_duration_ms: int | None = None
        self.max_send_duration_ms = 0
        self.slow_send_durations = 0
        self._last_send_started_at: float | None = None

    def send_audio_pcm_data(self, frame: object) -> int:
        started_at = time.monotonic()
        if self._last_send_started_at is not None:
            gap_ms = int((started_at - self._last_send_started_at) * 1000)
            self.last_send_gap_ms = gap_ms
            self.max_send_gap_ms = max(self.max_send_gap_ms, gap_ms)
            if gap_ms > AI_AUDIO_SLOW_SEND_GAP_MS:
                self.slow_send_gaps += 1

        try:
            ret = int(self._sender.send_audio_pcm_data(frame) or 0)
        except Exception:
            self.send_errors += 1
            raise
        finally:
            duration_ms = int((time.monotonic() - started_at) * 1000)
            self.last_send_duration_ms = duration_ms
            self.max_send_duration_ms = max(self.max_send_duration_ms, duration_ms)
            if duration_ms > AI_AUDIO_SLOW_SEND_DURATION_MS:
                self.slow_send_durations += 1
            self._last_send_started_at = started_at

        samples = int(getattr(frame, "samples_per_channel", 0) or 0)
        frame_ms = int(samples * 1000 / self._sample_rate) if self._sample_rate else 0
        self.send_calls += 1
        self.last_send_ms = frame_ms
        self.sent_audio_ms += frame_ms
        self.last_send_ret = ret
        if ret != 0:
            self.send_errors += 1
        return ret


class _AgoraAudioConsumerPacer:
    """Feeds TTS PCM through Agora's AudioConsumer at the SDK-recommended cadence."""

    def __init__(
        self,
        *,
        connection: object,
        sample_rate: int,
        consume_interval_ms: int,
        keepalive: bool,
        stop_event: asyncio.Event,
        channel_name: str,
        max_buffer_seconds: float = 12.0,
    ):
        from agora.rtc.utils.audio_consumer import AudioConsumer

        pcm_sender = getattr(connection, "_audio_sender", None)
        if pcm_sender is None:
            raise RuntimeError("Agora PCM audio sender is not available.")

        self._connection = connection
        self._sample_rate = sample_rate
        self._consume_interval_ms = max(40, min(80, consume_interval_ms))
        self._keepalive_enabled = keepalive
        self._stop = stop_event
        self._channel_name = channel_name
        self._bytes_per_10ms = int(
            sample_rate * PCM_CHANNELS * PCM_BYTES_PER_SAMPLE * 10 / 1000
        )
        self._max_buffer_size = int(
            sample_rate * PCM_CHANNELS * PCM_BYTES_PER_SAMPLE * max_buffer_seconds
        )
        self._sender_proxy = _MeasuredPcmSender(pcm_sender, sample_rate=sample_rate)
        self._consumer = AudioConsumer(
            pcm_sender=self._sender_proxy,
            sample_rate=sample_rate,
            channels=PCM_CHANNELS,
        )
        self._task: asyncio.Task[None] | None = None
        self._consume_calls = 0
        self._consume_errors = 0
        self._buffer_clears = 0
        self._underflows = 0
        self._keepalive_calls = 0
        self._last_consume_result: int | None = None
        self._last_audio_duration_ms: int | None = None
        self._last_health_log_at = 0.0
        keepalive_bytes = int(
            self._bytes_per_second() * self._consume_interval_ms / 1000
        )
        keepalive_bytes -= keepalive_bytes % self._bytes_per_10ms
        self._keepalive_pcm = _comfort_noise_frame(keepalive_bytes, amplitude=1)

    @property
    def consume_interval_ms(self) -> int:
        return self._consume_interval_ms

    @property
    def frame_size(self) -> int:
        return self._bytes_per_10ms

    def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(
            self._run(),
            name=f"ai-audio-consumer-{self._channel_name}",
        )

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)
        self._task = None
        self.clear()
        self._consumer.release()

    async def enqueue(self, pcm: bytes) -> int:
        if not pcm:
            return 0

        trimmed = _trim_pcm_to_10ms_boundary(pcm, sample_rate=self._sample_rate)
        if not trimmed:
            return 0

        current_buffer_size = self._consumer.len()
        overflow = current_buffer_size + len(trimmed) - self._max_buffer_size
        if overflow > 0 and current_buffer_size > 0:
            self.clear()
            logger.warning(
                "Cleared stale AI audio buffer before enqueue channel=%s overflow_bytes=%s",
                self._channel_name,
                overflow,
            )

        self._consumer.push_pcm_data(trimmed)
        duration_ms = int(len(trimmed) * 1000 / self._bytes_per_second())
        self._last_audio_duration_ms = duration_ms

        logger.info(
            "Queued AI audio for Agora AudioConsumer channel=%s bytes=%s duration_ms=%s buffer_ms=%s consume_interval_ms=%s",
            self._channel_name,
            len(trimmed),
            duration_ms,
            self.buffer_ms(),
            self._consume_interval_ms,
        )
        return len(trimmed)

    async def _run(self) -> None:
        logger.info(
            "Started Agora AudioConsumer for AI audio channel=%s sample_rate=%s consume_interval_ms=%s",
            self._channel_name,
            self._sample_rate,
            self._consume_interval_ms,
        )
        next_send_at = time.monotonic()
        while not self._stop.is_set():
            self._consume_once()
            self._maybe_log_health()
            next_send_at += self._consume_interval_ms / 1000
            delay = next_send_at - time.monotonic()
            if delay > 0:
                await self._sleep_until_stop(delay)
            elif delay < -0.2:
                next_send_at = time.monotonic()

    async def _sleep_until_stop(self, delay: float) -> None:
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=delay)
        except asyncio.TimeoutError:
            return

    def _bytes_per_second(self) -> int:
        return self._sample_rate * PCM_CHANNELS * PCM_BYTES_PER_SAMPLE

    def _maybe_log_health(self) -> None:
        now = time.monotonic()
        if now - self._last_health_log_at < AI_AUDIO_HEALTH_LOG_SECONDS:
            return
        self._last_health_log_at = now
        logger.info(
            "AI_AUDIO_HEALTH channel=%s sample_rate=%s tick_ms=%s buffer_ms=%s "
            "consume_calls=%s keepalive=%s underflows=%s send_calls=%s "
            "send_errors=%s sent_ms=%s last_send_gap_ms=%s max_send_gap_ms=%s "
            "slow_send_gaps=%s last_send_duration_ms=%s max_send_duration_ms=%s "
            "slow_send_durations=%s last_send_ms=%s last_send_ret=%s "
            "last_consume_result=%s",
            self._channel_name,
            self._sample_rate,
            self._consume_interval_ms,
            self.buffer_ms(),
            self._consume_calls,
            self._keepalive_calls,
            self._underflows,
            self._sender_proxy.send_calls,
            self._sender_proxy.send_errors,
            self._sender_proxy.sent_audio_ms,
            self._sender_proxy.last_send_gap_ms,
            self._sender_proxy.max_send_gap_ms,
            self._sender_proxy.slow_send_gaps,
            self._sender_proxy.last_send_duration_ms,
            self._sender_proxy.max_send_duration_ms,
            self._sender_proxy.slow_send_durations,
            self._sender_proxy.last_send_ms,
            self._sender_proxy.last_send_ret,
            self._last_consume_result,
        )

    def _consume_once(self) -> int:
        remaining_before = self._consumer.len()
        try:
            result = self._consumer.consume()
        except Exception:
            self._consume_errors += 1
            logger.warning(
                "Agora AudioConsumer consume failed channel=%s errors=%s",
                self._channel_name,
                self._consume_errors,
                exc_info=True,
            )
            return -1

        self._consume_calls += 1
        self._last_consume_result = int(result or 0)
        if self._last_consume_result == -2:
            self._underflows += 1
        if (
            self._keepalive_enabled
            and self._last_consume_result <= 0
            and remaining_before == 0
        ):
            self._send_keepalive()
        return self._last_consume_result

    def _send_keepalive(self) -> None:
        if not self._keepalive_pcm:
            return
        try:
            from agora.rtc.audio_pcm_data_sender import PcmAudioFrame

            frame = PcmAudioFrame()
            frame.data = bytearray(self._keepalive_pcm)
            frame.sample_rate = self._sample_rate
            frame.number_of_channels = PCM_CHANNELS
            frame.bytes_per_sample = PCM_BYTES_PER_SAMPLE
            frame.timestamp = 0
            frame.samples_per_channel = len(self._keepalive_pcm) // (
                PCM_CHANNELS * PCM_BYTES_PER_SAMPLE
            )
            ret = self._sender_proxy.send_audio_pcm_data(frame)
            self._keepalive_calls += 1
            if ret != 0:
                logger.debug("AI audio keepalive send returned %s", ret)
        except Exception:
            self._consume_errors += 1
            logger.warning("Failed to send AI audio keepalive", exc_info=True)

    def clear(self) -> None:
        try:
            self._consumer.clear()
            self._buffer_clears += 1
        except Exception:
            self._consume_errors += 1
            logger.warning("Failed to clear Agora AudioConsumer", exc_info=True)

    def buffer_ms(self) -> int:
        return int(self._consumer.len() * 1000 / self._bytes_per_second())

    def is_completed(self) -> bool:
        try:
            return self._consumer.is_push_to_rtc_completed() == 1
        except Exception:
            self._consume_errors += 1
            logger.warning(
                "Failed to read Agora AudioConsumer completion state",
                exc_info=True,
            )
            return False

    def stats(self) -> dict[str, int | bool | None]:
        return {
            "audio_consume_interval_ms": self._consume_interval_ms,
            "audio_buffer_ms": self.buffer_ms(),
            "audio_consume_calls": self._consume_calls,
            "audio_consume_errors": self._consume_errors,
            "audio_buffer_clears": self._buffer_clears,
            "audio_underflows": self._underflows,
            "audio_keepalive_calls": self._keepalive_calls,
            "audio_send_calls": self._sender_proxy.send_calls,
            "audio_send_errors": self._sender_proxy.send_errors,
            "audio_sent_ms": self._sender_proxy.sent_audio_ms,
            "last_audio_send_ms": self._sender_proxy.last_send_ms,
            "last_audio_send_ret": self._sender_proxy.last_send_ret,
            "last_audio_send_gap_ms": self._sender_proxy.last_send_gap_ms,
            "max_audio_send_gap_ms": self._sender_proxy.max_send_gap_ms,
            "slow_audio_send_gaps": self._sender_proxy.slow_send_gaps,
            "last_audio_send_duration_ms": self._sender_proxy.last_send_duration_ms,
            "max_audio_send_duration_ms": self._sender_proxy.max_send_duration_ms,
            "slow_audio_send_durations": self._sender_proxy.slow_send_durations,
            "last_consume_result": self._last_consume_result,
            "audio_consumer_completed": self.is_completed(),
            "last_audio_duration_ms": self._last_audio_duration_ms,
        }


def _normalize_commentary(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", text.lower()).strip()


def _commentary_words(text: str) -> set[str]:
    stop_words = {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "for",
        "from",
        "in",
        "is",
        "of",
        "on",
        "the",
        "to",
        "with",
    }
    return {
        word
        for word in _normalize_commentary(text).split()
        if len(word) > 2 and word not in stop_words
    }


def _is_no_call(text: str) -> bool:
    return _normalize_commentary(text) in {"no_call", "nocall", "no call"}


def _is_repetitive_commentary(text: str, previous_calls: list[str]) -> bool:
    if not previous_calls:
        return False

    normalized = _normalize_commentary(text)
    if not normalized:
        return True

    for previous in previous_calls[-4:]:
        previous_normalized = _normalize_commentary(previous)
        if normalized == previous_normalized:
            return True
        words = _commentary_words(text)
        previous_words = _commentary_words(previous)
        if len(words) < 4 or len(previous_words) < 4:
            continue
        overlap = len(words & previous_words) / max(1, len(words | previous_words))
        if overlap >= 0.72:
            return True

    return False


class BackendVisionCommentator:
    """Backend-owned AI commentator that publishes audio and transcript to RTC."""

    def __init__(
        self,
        *,
        settings: Settings,
        channel_name: str,
        agent_uid: int,
        match_context: MatchContext | None,
        media_uid: int,
        profile: CommentatorProfile | None = None,
    ):
        self._settings = settings
        self._channel_name = channel_name
        self._agent_uid = agent_uid
        self._match_context = match_context
        self._media_uid = media_uid
        self._profile = profile
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._sampler_task: asyncio.Task[None] | None = None
        self._audio_pacer: _AgoraAudioConsumerPacer | None = None
        self._audio_sender_proxy: _MeasuredPcmSender | None = None
        self._frame_lock = asyncio.Lock()
        self._frame_buffer: deque[FrameSnapshot] = deque(
            maxlen=max(1, settings.commentary_context_frames)
        )
        self._previous_calls: list[str] = []
        self._turn_id = 1
        self._vision_rate_limit_errors = 0
        self._vision_rate_limit_resume_at = 0.0
        self._frames_sampled = 0
        self._vision_requests = 0
        self._tts_requests = 0
        self._audio_backlog_skips = 0
        self._last_frame_at: int | None = None
        self._last_commentary_at: int | None = None
        self._last_audio_at: int | None = None
        self._last_audio_duration_ms: int | None = None
        self._stream_next_send_at: float | None = None

    @property
    def agent_uid(self) -> int:
        return self._agent_uid

    def stats(self) -> CommentatorStats:
        audio_stats = self._audio_stats()
        audio_consume_interval_ms = audio_stats.get("audio_consume_interval_ms")
        last_audio_duration_ms = audio_stats.get("last_audio_duration_ms")
        last_audio_send_ms = audio_stats.get("last_audio_send_ms")
        last_audio_send_ret = audio_stats.get("last_audio_send_ret")
        last_audio_send_gap_ms = audio_stats.get("last_audio_send_gap_ms")
        last_audio_send_duration_ms = audio_stats.get("last_audio_send_duration_ms")
        last_consume_result = audio_stats.get("last_consume_result")
        return CommentatorStats(
            frames_sampled=self._frames_sampled,
            vision_requests=self._vision_requests,
            tts_requests=self._tts_requests,
            audio_sample_rate=self._settings.commentary_audio_sample_rate,
            audio_consume_interval_ms=(
                int(audio_consume_interval_ms)
                if isinstance(audio_consume_interval_ms, int)
                else self._settings.commentary_audio_consume_interval_ms
            ),
            audio_buffer_ms=int(audio_stats.get("audio_buffer_ms", 0)),
            audio_consume_calls=int(audio_stats.get("audio_consume_calls", 0)),
            audio_consume_errors=int(audio_stats.get("audio_consume_errors", 0)),
            audio_buffer_clears=int(audio_stats.get("audio_buffer_clears", 0)),
            audio_backlog_skips=self._audio_backlog_skips,
            audio_underflows=int(audio_stats.get("audio_underflows", 0)),
            audio_keepalive_calls=int(audio_stats.get("audio_keepalive_calls", 0)),
            audio_send_calls=int(audio_stats.get("audio_send_calls", 0)),
            audio_send_errors=int(audio_stats.get("audio_send_errors", 0)),
            audio_sent_ms=int(audio_stats.get("audio_sent_ms", 0)),
            last_audio_send_ms=(
                int(last_audio_send_ms) if isinstance(last_audio_send_ms, int) else None
            ),
            last_audio_send_ret=(
                int(last_audio_send_ret) if isinstance(last_audio_send_ret, int) else None
            ),
            last_audio_send_gap_ms=(
                int(last_audio_send_gap_ms)
                if isinstance(last_audio_send_gap_ms, int)
                else None
            ),
            max_audio_send_gap_ms=int(audio_stats.get("max_audio_send_gap_ms", 0)),
            slow_audio_send_gaps=int(audio_stats.get("slow_audio_send_gaps", 0)),
            last_audio_send_duration_ms=(
                int(last_audio_send_duration_ms)
                if isinstance(last_audio_send_duration_ms, int)
                else None
            ),
            max_audio_send_duration_ms=int(
                audio_stats.get("max_audio_send_duration_ms", 0)
            ),
            slow_audio_send_durations=int(
                audio_stats.get("slow_audio_send_durations", 0)
            ),
            last_consume_result=(
                int(last_consume_result) if isinstance(last_consume_result, int) else None
            ),
            audio_consumer_completed=bool(
                audio_stats.get("audio_consumer_completed", True)
            ),
            last_audio_duration_ms=(
                int(last_audio_duration_ms)
                if isinstance(last_audio_duration_ms, int)
                else None
            ),
            last_frame_at=self._last_frame_at,
            last_commentary_at=self._last_commentary_at,
            last_audio_at=self._last_audio_at,
        )

    def _audio_stats(self) -> dict[str, int | bool | None]:
        if self._audio_pacer is not None:
            return self._audio_pacer.stats()

        sender = self._audio_sender_proxy
        if sender is None:
            return {
                "audio_consume_interval_ms": self._settings.commentary_audio_consume_interval_ms,
                "audio_buffer_ms": 0,
                "audio_consume_calls": 0,
                "audio_consume_errors": 0,
                "audio_buffer_clears": 0,
                "audio_underflows": 0,
                "audio_keepalive_calls": 0,
                "audio_send_calls": 0,
                "audio_send_errors": 0,
                "audio_sent_ms": 0,
                "last_audio_send_ms": None,
                "last_audio_send_ret": None,
                "last_audio_send_gap_ms": None,
                "max_audio_send_gap_ms": 0,
                "slow_audio_send_gaps": 0,
                "last_audio_send_duration_ms": None,
                "max_audio_send_duration_ms": 0,
                "slow_audio_send_durations": 0,
                "last_consume_result": None,
                "audio_consumer_completed": True,
                "last_audio_duration_ms": self._last_audio_duration_ms,
            }

        return {
            "audio_consume_interval_ms": self._settings.commentary_audio_consume_interval_ms,
            "audio_buffer_ms": 0,
            "audio_consume_calls": sender.send_calls,
            "audio_consume_errors": sender.send_errors,
            "audio_buffer_clears": 0,
            "audio_underflows": 0,
            "audio_keepalive_calls": 0,
            "audio_send_calls": sender.send_calls,
            "audio_send_errors": sender.send_errors,
            "audio_sent_ms": sender.sent_audio_ms,
            "last_audio_send_ms": sender.last_send_ms,
            "last_audio_send_ret": sender.last_send_ret,
            "last_audio_send_gap_ms": sender.last_send_gap_ms,
            "max_audio_send_gap_ms": sender.max_send_gap_ms,
            "slow_audio_send_gaps": sender.slow_send_gaps,
            "last_audio_send_duration_ms": sender.last_send_duration_ms,
            "max_audio_send_duration_ms": sender.max_send_duration_ms,
            "slow_audio_send_durations": sender.slow_send_durations,
            "last_consume_result": sender.last_send_ret,
            "audio_consumer_completed": True,
            "last_audio_duration_ms": self._last_audio_duration_ms,
        }

    def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(
            self._run(),
            name=f"backend-commentator-{self._channel_name}",
        )

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=8)
            except asyncio.TimeoutError:
                self._task.cancel()
                await asyncio.gather(self._task, return_exceptions=True)

    async def _run(self) -> None:
        sdk = self._load_sdk()
        os.makedirs(self._settings.log_dir, exist_ok=True)

        service_config = sdk.AgoraServiceConfig()
        service_config.appid = self._settings.agora_app_id
        service_config.enable_video = 1
        service_config.log_path = os.path.join(self._settings.log_dir, "agorasdk.log")
        service_config.log_file_size_kb = 1024
        service_config.data_dir = self._settings.log_dir
        service_config.config_dir = self._settings.log_dir
        service_config.area_code = area_code_value(self._settings.agora_area_code, sdk.AreaCode)

        service = sdk.AgoraService()
        connection = None
        try:
            service.initialize(service_config)
            connection = service.create_rtc_connection(
                sdk.RTCConnConfig(
                    auto_subscribe_audio=0,
                    auto_subscribe_video=0,
                    client_role_type=sdk.ClientRoleType.CLIENT_ROLE_BROADCASTER,
                    channel_profile=sdk.ChannelProfileType.CHANNEL_PROFILE_LIVE_BROADCASTING,
                    enable_audio_recording_or_playout=0,
                ),
                sdk.RtcConnectionPublishConfig(
                    audio_profile=sdk.AudioProfileType.AUDIO_PROFILE_DEFAULT,
                    audio_scenario=sdk.AudioScenarioType.AUDIO_SCENARIO_AI_SERVER,
                    audio_publish_type=sdk.AudioPublishType.AUDIO_PUBLISH_TYPE_PCM,
                    video_publish_type=sdk.VideoPublishType.VIDEO_PUBLISH_TYPE_NONE,
                    is_publish_audio=True,
                    is_publish_video=False,
                ),
            )
            token = generate_rtc_token(
                app_id=self._settings.agora_app_id,
                app_certificate=self._settings.agora_app_certificate,
                channel=self._channel_name,
                uid=self._agent_uid,
                role=ROLE_PUBLISHER,
                expiry_seconds=self._settings.token_expire_seconds,
            )
            connection.connect(token, self._channel_name, str(self._agent_uid))
            connection.publish_audio()
            self._audio_pacer = _AgoraAudioConsumerPacer(
                connection=connection,
                sample_rate=self._settings.commentary_audio_sample_rate,
                consume_interval_ms=self._settings.commentary_audio_consume_interval_ms,
                keepalive=self._settings.commentary_audio_keepalive,
                stop_event=self._stop,
                channel_name=self._channel_name,
                max_buffer_seconds=max(
                    1.0, self._settings.commentary_audio_backlog_limit_ms / 1000
                ),
            )
            self._audio_pacer.start()
            logger.info(
                "Started backend AI commentator channel=%s uid=%s vision_model=%s tts_model=%s audio_tick_ms=%s",
                self._channel_name,
                self._agent_uid,
                self._settings.openai_vision_model,
                self._tts_description(),
                self._audio_pacer.consume_interval_ms,
            )
            await self._commentary_loop(connection)
        finally:
            if self._audio_pacer is not None:
                try:
                    await self._audio_pacer.stop()
                except Exception:
                    logger.warning("Failed to stop AI audio pacer", exc_info=True)
                self._audio_pacer = None
            self._audio_sender_proxy = None
            if connection is not None:
                try:
                    connection.disconnect()
                    connection.release()
                except Exception:
                    logger.warning("Failed to release commentator RTC connection", exc_info=True)
            try:
                service.release()
            except Exception:
                logger.warning("Failed to release commentator Agora service", exc_info=True)

    async def _commentary_loop(self, connection: object) -> None:
        self._sampler_task = asyncio.create_task(
            self._sample_frames_until_stopped(connection),
            name=f"commentary-frame-sampler-{self._channel_name}",
        )
        try:
            await self._wait_for_first_frame()
            while not self._stop.is_set():
                started_at = time.monotonic()
                await self._commentary_from_latest_frames(connection)
                elapsed = time.monotonic() - started_at
                delay = max(0.05, self._settings.commentary_interval_seconds - elapsed)
                await self._sleep_until_stop(delay)
        finally:
            if self._sampler_task is not None:
                self._sampler_task.cancel()
                await asyncio.gather(self._sampler_task, return_exceptions=True)

    async def _sample_frames_until_stopped(self, connection: object) -> None:
        await self._sample_agora_frames_until_stopped(connection)

    async def _sample_agora_frames_until_stopped(self, connection: object) -> None:
        local_user = connection.get_local_user()
        frame_queue: asyncio.Queue[FrameSnapshot] = asyncio.Queue(
            maxsize=max(2, self._settings.commentary_context_frames * 3)
        )
        observer = _AgoraRemoteFrameObserver(
            loop=asyncio.get_running_loop(),
            queue=frame_queue,
            media_uid=self._media_uid,
            sample_seconds=self._settings.commentary_frame_sample_seconds,
            max_width=self._settings.commentary_frame_width,
            jpeg_quality=self._settings.commentary_frame_jpeg_quality,
        )
        register_ret = connection.register_video_frame_observer(observer)
        subscribe_ret = local_user.subscribe_video(str(self._media_uid), None)
        logger.info(
            "Subscribed backend commentator to Agora video channel=%s media_uid=%s register_ret=%s subscribe_ret=%s",
            self._channel_name,
            self._media_uid,
            register_ret,
            subscribe_ret,
        )
        try:
            while not self._stop.is_set():
                try:
                    snapshot = await asyncio.wait_for(frame_queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                await self._store_frame(snapshot)
                self._frames_sampled += 1
                self._last_frame_at = int(time.time())
                if observer.frames_sampled == 1:
                    logger.info(
                        "Received first Agora RTC video frame channel=%s media_uid=%s",
                        self._channel_name,
                        self._media_uid,
                    )
        finally:
            try:
                local_user.unsubscribe_video(str(self._media_uid))
            except Exception:
                logger.warning("Failed to unsubscribe Agora video", exc_info=True)
            try:
                connection._unregister_video_frame_observer()
            except Exception:
                logger.warning("Failed to unregister Agora video frame observer", exc_info=True)

    async def _commentary_from_latest_frames(self, connection: object) -> None:
        if self._vision_rate_limit_resume_at > time.monotonic():
            return

        samples = await self._latest_frames()
        if not samples:
            return

        try:
            pipeline_started_at = time.monotonic()
            describe_started_at = time.monotonic()
            text = await self._describe_frames(samples)
            describe_ms = int((time.monotonic() - describe_started_at) * 1000)
            self._vision_rate_limit_errors = 0
            self._vision_rate_limit_resume_at = 0.0
            if not text or _is_no_call(text):
                return
            if _is_repetitive_commentary(text, self._previous_calls):
                logger.info("Skipped repetitive visual commentary: %s", text)
                return
            self._previous_calls.append(text)
            self._previous_calls = self._previous_calls[-8:]
            turn_id = self._turn_id
            # Publish the transcript first so text appears immediately while
            # the spoken clip is still being prepared.
            transcript_started_at = time.monotonic()
            await self._publish_transcript(connection, text)
            transcript_ms = int((time.monotonic() - transcript_started_at) * 1000)

            audio_started_at = time.monotonic()
            if self._can_stream_elevenlabs():
                try:
                    result = await self._stream_publish_speech_elevenlabs(connection, text)
                    tts_ms = result.publish_ms
                    sent_bytes = result.sent_bytes
                    pcm_bytes = result.received_bytes
                    audio_duration_ms = result.duration_ms
                except Exception:
                    logger.warning(
                        "ElevenLabs stream endpoint TTS failed; falling back to buffered synth",
                        exc_info=True,
                    )
                    tts_ms, sent_bytes, pcm_bytes, audio_duration_ms = (
                        await self._buffered_synth_and_publish(connection, text)
                    )
            else:
                tts_ms, sent_bytes, pcm_bytes, audio_duration_ms = (
                    await self._buffered_synth_and_publish(connection, text)
                )
            audio_publish_ms = int((time.monotonic() - audio_started_at) * 1000)
            logger.info(
                "AI_AUDIO_PIPELINE channel=%s turn=%s describe_ms=%s transcript_ms=%s "
                "tts_ms=%s audio_publish_ms=%s total_ms=%s pcm_bytes=%s sent_bytes=%s "
                "pcm_ms=%s text_len=%s text=%r",
                self._channel_name,
                turn_id,
                describe_ms,
                transcript_ms,
                tts_ms,
                audio_publish_ms,
                int((time.monotonic() - pipeline_started_at) * 1000),
                pcm_bytes,
                sent_bytes,
                audio_duration_ms,
                len(text),
                text,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                self._pause_after_openai_rate_limit(exc.response.headers.get("retry-after"))
                return
            logger.warning("Failed to generate commentary for latest frames", exc_info=True)
        except Exception:
            logger.warning("Failed to generate commentary for latest frames", exc_info=True)

    def _pause_after_openai_rate_limit(self, retry_after: str | None) -> None:
        self._vision_rate_limit_errors = min(self._vision_rate_limit_errors + 1, 4)
        delay: float | None = None
        if retry_after:
            try:
                delay = max(1.0, float(retry_after))
            except ValueError:
                delay = None
        if delay is None:
            delay = min(
                OPENAI_RATE_LIMIT_MAX_BACKOFF_SECONDS,
                OPENAI_RATE_LIMIT_BASE_BACKOFF_SECONDS
                * (2 ** (self._vision_rate_limit_errors - 1)),
            )
        self._vision_rate_limit_resume_at = time.monotonic() + delay
        logger.warning("OpenAI vision rate limited; pausing commentary for %.1fs", delay)

    async def _store_frame(self, snapshot: FrameSnapshot) -> None:
        async with self._frame_lock:
            self._frame_buffer.append(snapshot)

    async def _latest_frames(self) -> list[FrameSnapshot]:
        async with self._frame_lock:
            return list(self._frame_buffer)

    async def _wait_for_first_frame(self) -> None:
        while not self._stop.is_set():
            if await self._latest_frames():
                return
            await self._sleep_until_stop(0.05)

    async def _sleep_until_stop(self, delay: float) -> None:
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=delay)
        except asyncio.TimeoutError:
            return

    async def _describe_frames(self, samples: list[FrameSnapshot]) -> str:
        if not self._settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for backend visual commentary.")

        content: list[dict[str, str]] = [
            {
                "type": "input_text",
                "text": _build_visual_prompt(
                    self._match_context,
                    samples=samples,
                    previous_calls=self._previous_calls,
                    profile=self._profile,
                ),
            }
        ]
        for sample in samples:
            content.append(
                {
                    "type": "input_image",
                    "image_url": f"data:image/jpeg;base64,{sample.image_base64}",
                }
            )

        request_body = {
            "model": self._settings.openai_vision_model,
            "input": [
                {
                    "role": "user",
                    "content": content,
                }
            ],
            "max_output_tokens": 40,
            "temperature": 0.55,
        }

        async with httpx.AsyncClient(timeout=35) as client:
            response = await client.post(
                OPENAI_RESPONSES_URL,
                headers={
                    "Authorization": f"Bearer {self._settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json=request_body,
            )
            response.raise_for_status()
            text = _extract_response_text(response.json())
            self._vision_requests += 1
            self._last_commentary_at = int(time.time())
            logger.info("Generated visual commentary: %s", text)
            return text

    async def _buffered_synth_and_publish(
        self, connection: object, text: str
    ) -> tuple[int, int, int, int]:
        """Synthesize the whole clip, then publish it. Returns
        ``(tts_ms, sent_bytes, pcm_bytes, audio_duration_ms)``."""
        sample_rate = self._settings.commentary_audio_sample_rate
        bytes_per_second = sample_rate * PCM_CHANNELS * PCM_BYTES_PER_SAMPLE
        tts_started_at = time.monotonic()
        audio_pcm = await self._synthesize_speech(text)
        tts_ms = int((time.monotonic() - tts_started_at) * 1000)
        audio_duration_ms = (
            int(len(audio_pcm) * 1000 / bytes_per_second)
            if audio_pcm and bytes_per_second
            else 0
        )
        sent_bytes = 0
        if audio_pcm:
            sent_bytes = await self._publish_audio(connection, audio_pcm)
        return tts_ms, sent_bytes, len(audio_pcm), audio_duration_ms

    async def _synthesize_speech(self, text: str) -> bytes:
        if self._settings.tts_provider == "elevenlabs":
            if self._settings.elevenlabs_api_key and self._settings.elevenlabs_voice_id:
                try:
                    return await self._synthesize_speech_elevenlabs(text)
                except Exception:
                    logger.warning(
                        "ElevenLabs TTS failed; falling back to OpenAI TTS",
                        exc_info=True,
                    )
            else:
                logger.warning(
                    "TTS_PROVIDER=elevenlabs requires ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID; falling back to OpenAI TTS"
                )
        if self._settings.tts_provider in {"fish_audio", "fishaudio", "fish"}:
            if self._settings.fish_audio_api_key and self._settings.fish_audio_voice_id:
                try:
                    return await self._synthesize_speech_fish_audio(text)
                except Exception:
                    logger.warning(
                        "Fish Audio TTS failed; falling back to OpenAI TTS",
                        exc_info=True,
                    )
            else:
                logger.warning(
                    "TTS_PROVIDER=fish_audio requires FISH_AUDIO_API_KEY and FISH_AUDIO_VOICE_ID; falling back to OpenAI TTS"
                )

        return await self._synthesize_speech_openai(text)

    def _can_stream_elevenlabs(self) -> bool:
        return bool(
            self._settings.elevenlabs_streaming
            and self._settings.tts_provider == "elevenlabs"
            and self._settings.elevenlabs_api_key
            and self._settings.elevenlabs_voice_id
            and _sample_rate_from_pcm_output_format(
                self._settings.elevenlabs_output_format
            )
        )

    async def _stream_publish_speech_elevenlabs(
        self, connection: object, text: str
    ) -> "_TtsStreamResult":
        """Fetch ElevenLabs PCM through its stream endpoint, then publish one clip.

        The HTTP response is read incrementally so large responses do not require
        a second download step, but this path intentionally buffers the complete
        PCM clip before handing it to the Agora audio pacer. Publishing partial
        chunks directly to RTC is possible, but it needs a dedicated jitter buffer
        to avoid choppy playback on real live streams.
        """
        source_rate = _sample_rate_from_pcm_output_format(
            self._settings.elevenlabs_output_format
        )
        assert source_rate is not None  # guarded by _can_stream_elevenlabs
        target_rate = self._settings.commentary_audio_sample_rate

        url = f"{ELEVENLABS_SPEECH_URL}/{self._settings.elevenlabs_voice_id}/stream"
        buffer = bytearray()
        ratecv_state = None
        sent = 0
        received = 0
        publish_ms: int | None = None
        started_at = time.monotonic()

        async with httpx.AsyncClient(timeout=35) as client:
            async with client.stream(
                "POST",
                url,
                params={"output_format": self._settings.elevenlabs_output_format},
                headers={
                    "xi-api-key": self._settings.elevenlabs_api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "text": text,
                    "model_id": self._settings.elevenlabs_model,
                    "voice_settings": {
                        "stability": self._settings.elevenlabs_stability,
                        "similarity_boost": self._settings.elevenlabs_similarity_boost,
                        "style": self._settings.elevenlabs_style,
                        "use_speaker_boost": self._settings.elevenlabs_use_speaker_boost,
                        "speed": self._settings.elevenlabs_speed,
                    },
                },
            ) as response:
                response.raise_for_status()
                async for raw in response.aiter_bytes():
                    if self._stop.is_set():
                        break
                    if not raw:
                        continue
                    received += len(raw)
                    if source_rate == target_rate:
                        pcm = raw
                    else:
                        pcm, ratecv_state = audioop.ratecv(
                            raw,
                            PCM_BYTES_PER_SAMPLE,
                            PCM_CHANNELS,
                            source_rate,
                            target_rate,
                            ratecv_state,
                        )
                    buffer.extend(pcm)

        if not self._stop.is_set():
            audio_pcm = _trim_pcm_to_10ms_boundary(bytes(buffer), sample_rate=target_rate)
            if audio_pcm:
                sent += await self._publish_audio(connection, audio_pcm)
            if publish_ms is None and sent > 0:
                publish_ms = int((time.monotonic() - started_at) * 1000)

        self._tts_requests += 1
        self._last_audio_at = int(time.time())
        duration_ms = int(received * 1000 / (source_rate * PCM_CHANNELS * PCM_BYTES_PER_SAMPLE)) if received else 0
        logger.info(
            "Buffered ElevenLabs commentary audio received_bytes=%s sent_bytes=%s "
            "publish_ms=%s duration_ms=%s voice=%s",
            received,
            sent,
            publish_ms,
            duration_ms,
            self._settings.elevenlabs_voice_id,
        )
        self._last_audio_duration_ms = duration_ms
        return _TtsStreamResult(
            publish_ms=publish_ms if publish_ms is not None else 0,
            sent_bytes=sent,
            received_bytes=received,
            duration_ms=duration_ms,
        )

    async def _synthesize_speech_openai(self, text: str) -> bytes:
        if not self._settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for backend commentary audio.")

        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(
                OPENAI_SPEECH_URL,
                headers={
                    "Authorization": f"Bearer {self._settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._settings.openai_tts_model,
                    "voice": self._settings.openai_tts_voice,
                    "input": text,
                    "response_format": "pcm",
                },
            )
            response.raise_for_status()
            self._tts_requests += 1
            self._last_audio_at = int(time.time())
            return _resample_pcm_mono(
                response.content,
                source_rate=24000,
                target_rate=self._settings.commentary_audio_sample_rate,
            )

    async def _synthesize_speech_elevenlabs(self, text: str) -> bytes:
        source_rate = _sample_rate_from_pcm_output_format(
            self._settings.elevenlabs_output_format
        )
        if source_rate is None:
            raise RuntimeError(
                "ELEVENLABS_OUTPUT_FORMAT must be a raw PCM format such as pcm_16000."
            )
        if not self._settings.elevenlabs_api_key:
            raise RuntimeError("ELEVENLABS_API_KEY is required for ElevenLabs commentary audio.")

        url = f"{ELEVENLABS_SPEECH_URL}/{self._settings.elevenlabs_voice_id}"
        async with httpx.AsyncClient(timeout=35) as client:
            response = await client.post(
                url,
                params={"output_format": self._settings.elevenlabs_output_format},
                headers={
                    "xi-api-key": self._settings.elevenlabs_api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "text": text,
                    "model_id": self._settings.elevenlabs_model,
                    "voice_settings": {
                        "stability": self._settings.elevenlabs_stability,
                        "similarity_boost": self._settings.elevenlabs_similarity_boost,
                        "style": self._settings.elevenlabs_style,
                        "use_speaker_boost": self._settings.elevenlabs_use_speaker_boost,
                        "speed": self._settings.elevenlabs_speed,
                    },
                },
            )
            response.raise_for_status()
            self._tts_requests += 1
            self._last_audio_at = int(time.time())
            logger.info(
                "Generated ElevenLabs commentary audio bytes=%s voice=%s source_rate=%s target_rate=%s",
                len(response.content),
                self._settings.elevenlabs_voice_id,
                source_rate,
                self._settings.commentary_audio_sample_rate,
            )
            return _resample_pcm_mono(
                response.content,
                source_rate=source_rate,
                target_rate=self._settings.commentary_audio_sample_rate,
            )

    async def _synthesize_speech_fish_audio(self, text: str) -> bytes:
        if self._settings.fish_audio_format != "pcm":
            raise RuntimeError("FISH_AUDIO_FORMAT must be pcm for Agora audio publishing.")
        if not self._settings.fish_audio_api_key:
            raise RuntimeError("FISH_AUDIO_API_KEY is required for Fish Audio commentary audio.")
        if not self._settings.fish_audio_voice_id:
            raise RuntimeError("FISH_AUDIO_VOICE_ID is required for Fish Audio commentary audio.")

        source_rate = (
            self._settings.fish_audio_sample_rate
            or self._settings.commentary_audio_sample_rate
        )
        async with httpx.AsyncClient(timeout=35) as client:
            response = await client.post(
                FISH_AUDIO_SPEECH_URL,
                headers={
                    "Authorization": f"Bearer {self._settings.fish_audio_api_key}",
                    "Content-Type": "application/json",
                    "model": self._settings.fish_audio_model,
                },
                json={
                    "text": text,
                    "reference_id": self._settings.fish_audio_voice_id,
                    "format": self._settings.fish_audio_format,
                    "sample_rate": source_rate,
                    "latency": self._settings.fish_audio_latency,
                    "chunk_length": self._settings.fish_audio_chunk_length,
                    "normalize": True,
                    "prosody": {
                        "speed": self._settings.fish_audio_speed,
                        "volume": self._settings.fish_audio_volume,
                        "normalize_loudness": self._settings.fish_audio_normalize_loudness,
                    },
                },
            )
            response.raise_for_status()
            self._tts_requests += 1
            self._last_audio_at = int(time.time())
            logger.info(
                "Generated Fish Audio commentary audio bytes=%s voice=%s model=%s source_rate=%s target_rate=%s",
                len(response.content),
                self._settings.fish_audio_voice_id,
                self._settings.fish_audio_model,
                source_rate,
                self._settings.commentary_audio_sample_rate,
            )
            return _resample_pcm_mono(
                response.content,
                source_rate=source_rate,
                target_rate=self._settings.commentary_audio_sample_rate,
            )

    def _tts_description(self) -> str:
        if self._settings.tts_provider == "elevenlabs":
            return f"elevenlabs:{self._settings.elevenlabs_model}:{self._settings.elevenlabs_voice_id}"
        if self._settings.tts_provider in {"fish_audio", "fishaudio", "fish"}:
            return f"fish_audio:{self._settings.fish_audio_model}:{self._settings.fish_audio_voice_id}"
        return f"openai:{self._settings.openai_tts_model}:{self._settings.openai_tts_voice}"

    async def _publish_transcript(self, connection: object, text: str) -> None:
        payload = _transcript_payload(
            text=text,
            agent_uid=self._agent_uid,
            turn_id=self._turn_id,
            language=self._profile.transcript_language if self._profile else "en",
        )
        ret = connection.send_stream_message(payload)
        if ret != 0:
            logger.debug("send_stream_message returned %s", ret)
        self._turn_id += 1

    async def _publish_audio(self, connection: object, pcm: bytes) -> int:
        sample_rate = self._settings.commentary_audio_sample_rate
        bytes_per_second = sample_rate * PCM_CHANNELS * PCM_BYTES_PER_SAMPLE
        trimmed_pcm = _trim_pcm_to_10ms_boundary(pcm, sample_rate=sample_rate)
        if not trimmed_pcm:
            return 0

        total_ms = int(len(trimmed_pcm) * 1000 / bytes_per_second)
        self._last_audio_duration_ms = total_ms

        if self._audio_pacer is not None:
            logger.info(
                "Queueing AI audio for RTC pacer channel=%s bytes=%s duration_ms=%s buffer_ms=%s",
                self._channel_name,
                len(trimmed_pcm),
                total_ms,
                self._audio_pacer.buffer_ms(),
            )
            return await self._audio_pacer.enqueue(trimmed_pcm)

        # Fallback for unit tests and unusual SDK startup failures: push ~100ms
        # chunks directly so we never send a giant PCM frame to Agora.
        chunk_ms = AI_AUDIO_SEND_CHUNK_MS
        chunk_size = int(bytes_per_second * chunk_ms / 1000)
        chunk_size -= chunk_size % (PCM_CHANNELS * PCM_BYTES_PER_SAMPLE)
        if chunk_size <= 0:
            chunk_size = max(PCM_CHANNELS * PCM_BYTES_PER_SAMPLE, bytes_per_second // 10)

        logger.info(
            "Publishing AI audio sequentially channel=%s bytes=%s duration_ms=%s chunk_ms=%s",
            self._channel_name,
            len(trimmed_pcm),
            total_ms,
            chunk_ms,
        )

        sent = 0
        for offset in range(0, len(trimmed_pcm), chunk_size):
            if self._stop.is_set():
                break

            chunk = _trim_pcm_to_millisecond_boundary(
                trimmed_pcm[offset : offset + chunk_size],
                sample_rate=sample_rate,
            )
            if not chunk:
                continue

            ret = self._push_audio_chunk(
                connection,
                chunk,
                sample_rate,
                present_time_ms=0,
            )
            if ret != 0:
                logger.warning("AI audio PCM chunk send returned %s", ret)
            else:
                sent += len(chunk)

            await self._sleep_until_stop(chunk_ms / 1000)

        logger.info(
            "Published AI audio sequentially channel=%s sent_bytes=%s duration_ms=%s",
            self._channel_name,
            sent,
            int(sent * 1000 / bytes_per_second) if bytes_per_second else 0,
        )
        return sent

    def _push_audio_chunk(
        self,
        connection: object,
        chunk: bytes,
        sample_rate: int,
        *,
        present_time_ms: int,
    ) -> int:
        sender = self._audio_sender_proxy
        if sender is None:
            return _push_audio_chunk_to_connection(
                connection,
                chunk,
                sample_rate,
                present_time_ms=present_time_ms,
            )

        from agora.rtc.agora_base import PcmAudioFrame

        frame = PcmAudioFrame()
        frame.data = bytearray(chunk)
        frame.sample_rate = sample_rate
        frame.number_of_channels = PCM_CHANNELS
        frame.bytes_per_sample = PCM_BYTES_PER_SAMPLE
        frame.timestamp = 0
        frame.samples_per_channel = len(chunk) // (PCM_CHANNELS * PCM_BYTES_PER_SAMPLE)
        frame.present_time_ms = present_time_ms
        return sender.send_audio_pcm_data(frame)

    @staticmethod
    def _load_sdk() -> SimpleNamespace:
        from agora.rtc.agora_base import (
            AreaCode,
            AudioProfileType,
            AudioPublishType,
            AudioScenarioType,
            ChannelProfileType,
            ClientRoleType,
            RtcConnectionPublishConfig,
            VideoPublishType,
        )
        from agora.rtc.agora_service import AgoraService, AgoraServiceConfig, RTCConnConfig

        return SimpleNamespace(
            AgoraService=AgoraService,
            AgoraServiceConfig=AgoraServiceConfig,
            RTCConnConfig=RTCConnConfig,
            RtcConnectionPublishConfig=RtcConnectionPublishConfig,
            AreaCode=AreaCode,
            AudioProfileType=AudioProfileType,
            AudioPublishType=AudioPublishType,
            AudioScenarioType=AudioScenarioType,
            ChannelProfileType=ChannelProfileType,
            ClientRoleType=ClientRoleType,
            VideoPublishType=VideoPublishType,
        )
