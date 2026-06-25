from dataclasses import dataclass
import os

from .config import Settings


@dataclass(frozen=True)
class CommentatorProfile:
    id: str
    label: str
    language: str
    transcript_language: str
    style_prompt: str
    tts_provider: str
    voice_env: str | None = None


DEFAULT_COMMENTATOR_PROFILE_ID = "zh-cn-fish-meme"

COMMENTATOR_PROFILES: dict[str, CommentatorProfile] = {
    "zh-cn-fish-meme": CommentatorProfile(
        id="zh-cn-fish-meme",
        label="Chinese Meme Commentary",
        language="zh-CN",
        transcript_language="zh",
        tts_provider="fish_audio",
        voice_env="FISH_AUDIO_VOICE_ID_ZH_MEME",
        style_prompt=(
            "你是中文足球现场解说员，风格有梗、反应快、接地气，但不要辱骂球员、"
            "不要冒充真实公众人物本人。用简体中文解说，优先描述最新画面里的持球、"
            "传球、逼抢、冲刺、射门、防守站位和观众能错过的细节。节奏要像直播间："
            "快攻时短促兴奋，阵地战时可以稍微补充战术观察。"
        ),
    ),
    "zh-cn-fish-tactical": CommentatorProfile(
        id="zh-cn-fish-tactical",
        label="Chinese Tactical Commentary",
        language="zh-CN",
        transcript_language="zh",
        tts_provider="fish_audio",
        voice_env="FISH_AUDIO_VOICE_ID_ZH_TACTICAL",
        style_prompt=(
            "你是中文足球战术解说员。用简体中文，少喊口号，多讲阵型、空间、压迫、"
            "反击线路、二点球和防线移动。保持直播节奏，不要长篇复盘，不要预测比分。"
        ),
    ),
    "en-us-sportscaster": CommentatorProfile(
        id="en-us-sportscaster",
        label="English Sportscaster",
        language="en-US",
        transcript_language="en",
        tts_provider="elevenlabs",
        voice_env="ELEVENLABS_VOICE_ID_EN_SPORTSCASTER",
        style_prompt=(
            "You are an energetic American English sportscaster. Call the newest visible "
            "action with sharp play-by-play cadence, urgency on attacks, and restraint "
            "when the picture is unclear."
        ),
    ),
    "fr-fr-sportscaster": CommentatorProfile(
        id="fr-fr-sportscaster",
        label="French Sportscaster",
        language="fr-FR",
        transcript_language="fr",
        tts_provider="elevenlabs",
        voice_env="ELEVENLABS_VOICE_ID_FR_SPORTSCASTER",
        style_prompt=(
            "Tu es un grand commentateur français de football, dans un style de "
            "diffusion télévisée métropolitaine. Ton énergie est explosive, urgente, "
            "théâtrale et passionnée. Reste dans le commentaire de direct: phrases "
            "courtes pendant les attaques, montée dramatique quand le danger arrive, "
            "noms des joueurs nets, et explosion émotionnelle seulement si l'image "
            "montre vraiment une occasion décisive ou un but."
        ),
    ),
}


def resolve_commentator_profile(profile_id: str | None) -> CommentatorProfile:
    if profile_id and profile_id in COMMENTATOR_PROFILES:
        return COMMENTATOR_PROFILES[profile_id]
    return COMMENTATOR_PROFILES[DEFAULT_COMMENTATOR_PROFILE_ID]


def settings_for_commentator_profile(
    settings: Settings,
    profile: CommentatorProfile,
) -> Settings:
    voice_id = os.getenv(profile.voice_env, "") if profile.voice_env else ""
    if not voice_id and profile.tts_provider == "fish_audio":
        voice_id = settings.fish_audio_voice_id or ""
    if not voice_id and profile.tts_provider == "elevenlabs":
        voice_id = settings.elevenlabs_voice_id or ""
    update: dict[str, object] = {
        "tts_provider": profile.tts_provider if voice_id else "openai",
    }
    if profile.tts_provider == "fish_audio":
        update["fish_audio_voice_id"] = voice_id
    elif profile.tts_provider == "elevenlabs":
        update["elevenlabs_voice_id"] = voice_id
    return settings.model_copy(update=update)
