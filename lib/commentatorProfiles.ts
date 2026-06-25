export const DEFAULT_COMMENTATOR_PROFILE_ID = 'zh-cn-fish-meme';

export type CommentatorProfileId =
  | 'zh-cn-fish-meme'
  | 'zh-cn-fish-tactical'
  | 'en-us-sportscaster'
  | 'fr-fr-sportscaster';

export type CommentatorProfileOption = {
  id: CommentatorProfileId;
  label: string;
  description: string;
};

export const COMMENTATOR_PROFILES: CommentatorProfileOption[] = [
  {
    id: 'zh-cn-fish-meme',
    label: 'Chinese Meme Commentary',
    description: 'Fish Audio voice via FISH_AUDIO_VOICE_ID_ZH_MEME',
  },
  {
    id: 'zh-cn-fish-tactical',
    label: 'Chinese Tactical Commentary',
    description: 'Fish Audio voice via FISH_AUDIO_VOICE_ID_ZH_TACTICAL',
  },
  {
    id: 'en-us-sportscaster',
    label: 'English Sportscaster',
    description: 'ElevenLabs voice via ELEVENLABS_VOICE_ID_EN_SPORTSCASTER',
  },
  {
    id: 'fr-fr-sportscaster',
    label: 'French Sportscaster',
    description: 'ElevenLabs voice via ELEVENLABS_VOICE_ID_FR_SPORTSCASTER',
  },
];
