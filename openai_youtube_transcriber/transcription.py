"""Whisper: what is said in a recording, and in which language."""

import os
import subprocess

import whisper
from langdetect import DetectorFactory, LangDetectException, detect

from .common import error

# langdetect samples at random, so a short or mixed transcript was tagged fr on
# one run and en the next, and named differently each time
DetectorFactory.seed = 0


class TranscriptionMixin:
    """Transcribing with Whisper."""

    def transcribe_audio_file(self, file_path, model_name, target_language,
                              source_language=None):
        """Transcribe with Whisper into target_language, the language to write.

        Whisper's own `language` is the language spoken, not the one to write:
        handed the target, it decoded English speech as if it were French. So
        the spoken language is source_language, or detected, and the target
        picks the task - 'auto' or the spoken language itself is a
        transcription, English is Whisper's translation, and any other language
        Whisper cannot write, so the transcription stands in for it, said so.

        Returns (text, language_code), the code being the language the text is
        actually in, or (None, code) on failure or no speech. Never an error
        string, which callers would otherwise save as a transcript.
        """
        if not os.path.exists(file_path):
            error(f"Error: Audio file not found: {file_path}")
            return None, "en"

        # Several target languages ask for the same weights in turn. Keeping
        # one model saves reloading them; keeping two would double the memory a
        # large model already takes
        if getattr(self, '_loaded_model_name', None) == model_name:
            model = self._loaded_model
        else:
            # The last model is let go before the next is loaded: held while it
            # loaded, the two took twice the memory a large model already does
            self._loaded_model_name = self._loaded_model = None
            try:
                print(f"Loading Whisper model: {model_name}")
                model = whisper.load_model(model_name)
            # Whisper reports an unknown name, a corrupt download and a checksum
            # mismatch as RuntimeError, as torch does running out of memory
            except (OSError, ValueError, RuntimeError) as load_error:
                error(f"Error loading Whisper model: {str(load_error)}")
                print("Falling back to base model")
                try:
                    model = whisper.load_model("base")
                except (OSError, ValueError, RuntimeError) as fallback_error:
                    error(f"Error loading fallback model: {str(fallback_error)}")
                    return None, "en"
            # Kept under the name asked for, fallback or not: a model that ran
            # out of memory once does again, and every later target and source
            # of a batch spent gigabytes failing to load it before falling back
            self._loaded_model_name, self._loaded_model = model_name, model

        auto = target_language in (None, "", self.AUTO_LANGUAGE)
        absolute_path = os.path.abspath(file_path)
        wanted = ("in the language spoken" if auto
                  else f"into {self.language_name(target_language)}")
        print(f"Transcribing audio from {absolute_path} ({wanted})...")

        # The passes already made over this audio, and over no other: a batch
        # moves on to the next file, and has no use for the last one's
        cache = getattr(self, '_whisper_results', None) or {}
        if cache.get('path') != absolute_path:
            cache = {'path': absolute_path}
        self._whisper_results = cache
        # The spoken language, once any target has found it out
        heard_key = ('spoken', model_name)

        spoken = source_language or cache.get(heard_key)
        if target_language == 'en' and not spoken:
            # English is a transcription of English speech and a translation of
            # anything else, so this is the one target that needs to know first
            spoken = cache[heard_key] = self.spoken_language(model, file_path)

        def run(language, translate=False):
            """One Whisper pass, once per audio however many targets want it."""
            key = (model_name, language, translate)
            if key not in cache:
                # The task only where it is not the default, so a stand-in model
                # need take no more than Whisper's own first two arguments
                options = {'task': 'translate'} if translate else {}
                result = model.transcribe(file_path, language=language, **options)
                # The text and its language, not the segments and their tokens
                cache[key] = {'text': result['text'], 'language': result.get('language')}
                heard = cache[key]['language']
                if language is None and not translate and heard:
                    # What Whisper detected is what a hint of it would decode:
                    # 'auto' then 'en' on English speech ran a second, identical
                    # full pass, and threw it away as already saved
                    cache.setdefault((model_name, heard, False), cache[key])
                    cache[heard_key] = cache.get(heard_key) or heard
            return cache[key]

        try:
            translated = target_language == 'en' and spoken not in (None, 'en')
            if translated:
                print(f"Whisper heard {self.language_name(spoken)}; translating it into English.")
            result = run(spoken, translated)
            heard = result.get('language')
            if target_language == 'en' and not translated and heard not in (None, 'en'):
                # Detection could not be had beforehand, and Whisper's own says
                # this was not English
                print(f"Whisper heard {self.language_name(heard)}; translating it into English.")
                result, translated = run(heard, True), True
            transcribed_text = result["text"]

            if not transcribed_text.strip():
                print("Warning: Transcription produced empty text. "
                      "The audio might be silent or not contain speech.")
                return None, target_language

        except (RuntimeError, ValueError) as e:
            error(f"Error during transcription: {str(e)}")
            return None, "en"

        print("\nTranscription:\n" + transcribed_text + "\n")

        try:
            detected_language = detect(transcribed_text)
        except LangDetectException as e:
            error(f"Error detecting language: {str(e)}")
            detected_language = "unknown"

        # Named for the language the text is in, which Whisper knows: English
        # for a translation, else the language it transcribed. langdetect only
        # stands in for a model that does not say.
        fallback = self.DEFAULT_LANGUAGE if auto else target_language
        language = ('en' if translated else result.get('language') or spoken
                    or self.resolve_transcript_language(detected_language, fallback))
        read_as = self.resolve_transcript_language(detected_language, None)
        if read_as == language:
            print(f"Verified {self.language_name(language)}")
        elif read_as:
            print(f"Note: Whisper wrote {self.language_name(language)}, but the text reads "
                  f"as {self.language_name(read_as)}.")
        if not auto and language != target_language:
            # Whisper writes the language spoken, or English, and nothing else
            print(f"Whisper translates into English only, so this is the "
                  f"{self.language_name(language)} transcript. For "
                  f"{self.language_name(target_language)}, refine it with "
                  f"prompt0-translator.txt, naming the language on its first line.")
        return transcribed_text, language

    @staticmethod
    def language_name(code):
        """'fr' as 'French', for a message."""
        return whisper.tokenizer.LANGUAGES.get(code, code or "an unknown language").capitalize()

    def spoken_language(self, model, file_path):
        """The language spoken in the audio, by Whisper's own detection, or None.

        One 30-second window, as transcribe() itself decides by, rather than a
        whole transcription just to find out. An English-only model can hear
        nothing else; one that cannot detect leaves it to transcribe().
        """
        if not getattr(model, 'is_multilingual', True):
            return 'en'
        if not hasattr(model, 'detect_language'):
            return None
        try:
            audio = whisper.pad_or_trim(self.load_opening(file_path))
            mel = whisper.log_mel_spectrogram(audio, n_mels=model.dims.n_mels)
            _tokens, probabilities = model.detect_language(mel.to(model.device))
            return max(probabilities, key=probabilities.get)
        except (subprocess.CalledProcessError, OSError, RuntimeError, ValueError,
                AttributeError, TypeError) as e:
            print(f"Note: could not detect the spoken language first ({str(e)}).")
            return None

    @staticmethod
    def load_opening(file_path, seconds=30):
        """The first `seconds` of a file's audio, as whisper.load_audio returns
        all of it: mono float32 at Whisper's sample rate.

        Detection hears only the first 30 seconds, and load_audio decoded the
        whole file for them - hundreds of megabytes of a three-hour lecture -
        before transcribe() decoded it all again. -t ahead of -i stops ffmpeg
        reading at that point.
        """
        import numpy
        command = ['ffmpeg', '-nostdin', '-threads', '0', '-t', str(seconds), '-i', file_path,
                   '-f', 's16le', '-ac', '1', '-acodec', 'pcm_s16le',
                   '-ar', str(whisper.audio.SAMPLE_RATE), '-']
        pcm = subprocess.run(command, capture_output=True, check=True).stdout
        return numpy.frombuffer(pcm, numpy.int16).flatten().astype(numpy.float32) / 32768.0
