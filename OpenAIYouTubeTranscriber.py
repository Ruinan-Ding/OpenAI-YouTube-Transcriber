# Downloads audio/video from YouTube and transcribes it using OpenAI's Whisper
# Author: Ruinan Ding

# Run with: python OpenAIYouTubeTranscriber.py

"""The script the README runs, and the module code written for 1.2 imports.

The app itself is the openai_youtube_transcriber package beside this file;
this keeps `python OpenAIYouTubeTranscriber.py`, `python .` and
`import OpenAIYouTubeTranscriber` working as they did.
"""

from openai_youtube_transcriber.cli import main
from openai_youtube_transcriber.common import (AIEnhancementMode, LocalModel,
                                               ModelSize, Provider, Resolution,
                                               YesNo)
from openai_youtube_transcriber.transcriber import YouTubeTranscriber

__all__ = ['AIEnhancementMode', 'LocalModel', 'ModelSize', 'Provider', 'Resolution', 'YesNo',
           'YouTubeTranscriber', 'main']

if __name__ == "__main__":
    main()
