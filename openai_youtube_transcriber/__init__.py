"""Download audio and video from YouTube, and transcribe it with OpenAI's Whisper.

Author: Ruinan Ding

Run it as `python OpenAIYouTubeTranscriber.py`, or `openai-youtube-transcriber`
once installed. The modules, from the ground up:

- common: the words everything else is written in - yes and no, qualities,
  Whisper models, AI providers - and the helpers they all use
- transcriber: YouTubeTranscriber, made of the mixins in inputs, files,
  youtube, media, transcription and enhancement
- config: what a session is set to do, and what a run carries between rounds
- answers: where a setting's answer comes from - a profile, or the round
  before - and what a gap in it means
- profiles: choosing and reading a profile
- questions: the menus and typed answers the settings are asked with
- settings: settling each setting, for a profile and a person alike
- naming: what each file is called, so that no two land on one name
- transcripts: refining, saving, and replacing a refined source
- pipeline: one pass per source - downloads, merges, conversions
- cli: the session, its rounds, and main()
"""
