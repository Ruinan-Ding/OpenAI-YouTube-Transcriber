"""Refining a transcript with a cloud or a local model, a chunk at a time."""

from __future__ import annotations

import difflib
import importlib.util
import inspect
import re
import unicodedata
from collections.abc import Callable

from .base import TranscriberBase
from .common import AIEnhancementMode, LocalModel, Provider, error


class EnhancementMixin(TranscriberBase):
    """Refining a transcript with a model, a chunk at a time."""

    # Appended to the enhancement prompt so chat models don't add "Sure! Here's..." preambles.
    # It says nothing about layout: that is the prompt's to decide, and the
    # shipped ones ask for headers.
    ENHANCEMENT_OUTPUT_DIRECTIVE = (
        'Reply with the result alone: no opening line such as "Here is the edited '
        'transcript", and nothing after it.')
    # max_tokens is required by the Anthropic API (no SDK default); per-chunk value
    # is sized off the chunk itself (see enhance_with_anthropic), capped here
    ANTHROPIC_MAX_OUTPUT_TOKENS = 8192

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """A token count without a tokenizer: the text's UTF-8 bytes over four.

        Characters over four held for English, at 4.4 a token with Qwen's
        tokenizer, but not for Chinese at 1.7, where a chunk took 2.4 times the
        text it was meant to. A CJK character is three bytes, so this errs a
        little high for both.
        """
        return len(text.encode('utf-8')) // 4

    @staticmethod
    def rejoin(left: str) -> str:
        """What goes back where text was cut after `left`: a space, or nothing
        after Chinese or Japanese, which are written without spaces between words.

        Width finds those - their characters, kana and full-width stops and
        brackets are all wide - except Hangul, which is as wide but spaces its
        words, and lost a space at every seam of a Korean transcript.
        """
        if not left:
            return " "
        last = left[-1]
        wide = unicodedata.east_asian_width(last) in ("W", "F")
        return "" if wide and not unicodedata.name(last, "").startswith("HANGUL") else " "

    @staticmethod
    def longest_missing_run(source: str, reply: str) -> int:
        """The most words of source in a row that reply leaves out.

        Compared without case, accents or apostrophes, which a refinement fixes;
        a Chinese or Japanese character counts as a word.
        """
        def words(text: str) -> list[str]:
            text = unicodedata.normalize("NFKD", text.lower().replace("'", "").replace("’", ""))
            text = "".join(c for c in text if not unicodedata.combining(c))
            return re.findall(r"[\u3040-\u30ff\u3400-\u9fff]|[^\W_]+", text)

        longest = start = 0
        matcher = difflib.SequenceMatcher(a=words(source), b=words(reply), autojunk=False)
        for block in matcher.get_matching_blocks():
            longest, start = max(longest, block.a - start), block.a + block.size
        return longest

    @classmethod
    def chunk_text(cls, text: str, max_tokens: int = 800) -> list[str]:
        """Split text into chunks at sentence boundaries, under max_tokens each.

        Chunks do not overlap. An overlap gives the model context across the
        boundary, but it cannot be stripped again afterwards: enhancement
        rewrites both copies of it, so no exact match survives to find, and the
        overlap is duplicated into the transcript. Splitting on sentence
        boundaries leaves nothing mid-thought for the context to rescue.
        """
        return cls.chunk_spans(text, max_tokens)[0]

    @classmethod
    def chunk_spans(cls, text: str, max_tokens: int = 800,
                    count: Callable[[str], int] | None = None) -> tuple[list[str], list[str]]:
        """(chunks, seams): chunk_text's chunks, and the exact text between each
        chunk and the next - whitespace, or nothing where a cut had to fall
        inside a word.

        Every chunk is a span of the text as it stands, so a chunk the model
        failed on goes back exactly as it was. Wrapped with textwrap, a word
        longer than the budget was cut and a space put into it, and a script
        without spaces between words, Thai among them, got one at every cut:
        a failed enhancement still changed the words.

        `count` measures a span in tokens, estimate_tokens by default; a
        backend that has the model's own tokenizer passes that instead.
        """
        count = count or cls.estimate_tokens

        def fits(span: str) -> bool:
            return count(span) <= max_tokens

        # Hindi ends a sentence with a danda and Arabic a question with its own
        # mark, both followed by a space; Chinese and Japanese use a full-width
        # stop with no space after it. A number opening a line is a list item's,
        # and a cut there left "1." ending one chunk and its item opening the next.
        # The space after each sentence is captured to go back as it was: joined
        # on a space, a chunk kept unrefined lost its line breaks and ran headers
        # into the paragraph before them.
        parts = re.split(r'((?<=[.!?।؟])(?<!^\d\.)(?<!^\d\d\.)\s+|(?<=[。！？])\s*)',
                         text, flags=re.MULTILINE)
        # (span, the whitespace after it); joined, they are the text itself
        pieces: list[tuple[str, str]] = []
        for sentence, space in zip(parts[::2], parts[1::2] + [""]):
            if fits(sentence):
                pieces.append((sentence, space))
                continue
            # Unpunctuated audio yields one giant "sentence": cut it between
            # words, and a word too long for any chunk between characters
            words = re.split(r'(\s+)', sentence)
            for word, gap in zip(words[::2], words[1::2] + [space]):
                pieces += cls._split_word(word, fits) + [("", gap)]

        chunks: list[str] = []
        seams: list[str] = []
        current, pending = "", ""
        for span, space in pieces:
            if not span.strip():
                # Whitespace only: it belongs to the seam, whichever side it is
                pending += span + space
                continue
            lead = span[:len(span) - len(span.lstrip())]
            span, space = span.strip(), span[len(span.rstrip()):] + space
            if current and not fits(current + pending + lead + span):
                chunks.append(current)
                seams.append(pending + lead)
                current = span
            else:
                current += (pending + lead if current else "") + span
            pending = space
        if current:
            chunks.append(current)
        return (chunks, seams) if chunks else ([text], [])

    @staticmethod
    def _split_word(word: str, fits: Callable[[str], bool]) -> list[tuple[str, str]]:
        """A run of text with no whitespace in it, as spans that each fit.

        Cut where the budget runs out, but never between a letter and the mark
        that goes with it - a Thai vowel sign, an accent - which would open the
        next chunk on a mark with nothing to sit on.
        """
        spans: list[tuple[str, str]] = []
        while word and not fits(word):
            low, high = 1, len(word)
            while low < high:
                middle = (low + high + 1) // 2
                low, high = (middle, high) if fits(word[:middle]) else (low, middle - 1)
            cut = low
            while cut > 1 and unicodedata.category(word[cut])[0] == 'M':
                cut -= 1
            spans.append((word[:cut], ""))
            word = word[cut:]
        return spans + [(word, "")]

    def _build_chat_messages(self, prompt_text: str, chunk: str) -> list[dict[str, str]]:
        """Build the system/user message pair shared by all chat-style backends."""
        return [
            {"role": "system", "content": f"{prompt_text}\n\n{self.ENHANCEMENT_OUTPUT_DIRECTIVE}"},
            {"role": "user", "content": chunk}
        ]

    def _run_chunked_enhancement(self, chunks: list[str], backend_label: str,
                                 call_chunk: Callable[[str], str],
                                 seams: list[str] | None = None) -> str:
        """Shared chunk-loop for the enhancement backends.

        call_chunk(chunk) returns enhanced text; a falsy return or a raised
        exception keeps the original chunk. `seams` is chunk_spans' text
        between the chunks, which two chunks kept as they were are joined by,
        so a backend that fails throughout hands back the text it was given.
        """
        enhanced_chunks: list[str] = []
        unchanged: list[str] = []
        for i, chunk in enumerate(chunks):
            enhanced: str | None
            try:
                print(f"  Processing chunk {i+1}/{len(chunks)}...")
                enhanced = call_chunk(chunk)
            except Exception as e:
                print(f"  Warning: {backend_label} error on chunk {i+1}: {str(e)}")
                enhanced = None
            # A small model wraps its reply in a code block though every prompt says
            # not to, and each fence landed in the file - unless the chunk opened one
            fenced = re.fullmatch(r"```[\w-]*\n(.*?)\n?```", (enhanced or "").strip(), re.DOTALL)
            if fenced and not chunk.startswith("```"):
                enhanced = fenced.group(1).strip()
            if not enhanced:
                unchanged.append(str(i + 1))
            enhanced_chunks.append(enhanced or chunk)
        # A chunk kept as transcribed sits in the file looking like the rest, so
        # the run has to say which, or a partial refinement reads as a whole one
        if unchanged:
            print(f"  Warning: {len(unchanged)} of {len(chunks)} chunk(s) kept as "
                  f"transcribed, not enhanced: chunk {', '.join(unchanged)}.")
        # chunk_text leaves no overlap to strip. Each reply is laid out on its own,
        # so after a chunk that ended a sentence a blank line keeps its last
        # paragraph off the next reply's header. A transcript with no punctuation
        # to cut at is cut mid-sentence, and a blank line there would split the
        # sentence in two, so that seam closes as the text was - on a space, or on
        # nothing in a script without spaces - unless a header follows.
        # Between two chunks kept as they were, the seam is the text's own.
        # Where one was cut mid-word, no reply is laid out around the cut either,
        # so an unended seam closes as the text did there, and not on a space
        # a cut word would take in.
        merged = enhanced_chunks[0].strip() if enhanced_chunks else ""
        for i, (chunk, reply) in enumerate(zip(chunks, enhanced_chunks[1:])):
            reply = reply.strip()
            seam = seams[i] if seams is not None and i < len(seams) else None
            kept = str(i + 1) in unchanged and str(i + 2) in unchanged
            ended = chunk.rstrip()[-1:] in ".!?।؟。！？"
            if seam is not None and kept:
                merged += seam + reply
            elif ended or reply.startswith("#"):
                merged += "\n\n" + reply
            else:
                merged += (self.rejoin(merged) if seam is None else seam) + reply
        return merged.strip()

    def enhance_with_openai_compatible(self, text: str, prompt_text: str, api_key: str,
                                       provider: Provider) -> str:
        """Enhance transcript text via an OpenAI-compatible endpoint.

        Covers OPENAI and OPENROUTER, plus anything else reachable by overriding the
        provider's base URL (Groq, Together, DeepSeek, Azure). Returns `text` on failure.
        """
        try:
            import openai
        except ImportError:
            print("Warning: 'openai' package not installed. Skipping AI enhancement.")
            print("Install with: pip install openai")
            return text

        model = provider.resolve_model()
        base_url = provider.resolve_base_url()
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        client = openai.OpenAI(**client_kwargs)
        chunks, seams = self.chunk_spans(text, max_tokens=3000)

        print(f"Enhancing transcript with {provider.key} ({model}, {len(chunks)} chunk(s))...")

        def call_chunk(chunk: str) -> str:
            response = client.chat.completions.create(
                model=model,
                messages=self._build_chat_messages(prompt_text, chunk),
                temperature=0.3
            )
            choice = response.choices[0]
            if choice.finish_reason == "length":
                # Cut off mid-reply, as the Anthropic path guards against too: the
                # original chunk is worth more than the half of it that came back
                print("  Warning: response truncated at the output limit; "
                      "keeping original chunk to avoid content loss.")
                return ""
            # A refusal can arrive with no content at all
            return (choice.message.content or "").strip()

        result = self._run_chunked_enhancement(chunks, provider.key, call_chunk, seams)
        print(f"{provider.key} enhancement complete.")
        return result

    def enhance_with_anthropic(self, text: str, prompt_text: str, api_key: str,
                               provider: Provider) -> str:
        """Enhance transcript text via Anthropic's Messages API. Returns `text` on failure."""
        try:
            import anthropic
        except ImportError:
            print("Warning: 'anthropic' package not installed. Skipping AI enhancement.")
            print("Install with: pip install anthropic")
            return text

        model = provider.resolve_model()
        base_url = provider.resolve_base_url()
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        client = anthropic.Anthropic(**client_kwargs)
        chunks, seams = self.chunk_spans(text, max_tokens=3000)

        print(f"Enhancing transcript with anthropic ({model}, {len(chunks)} chunk(s))...")

        def call_chunk(chunk: str) -> str:
            # Size the output budget off the chunk itself, twice the estimate chunk_text
            # sized it by, so expansion-style prompts still have headroom. Characters
            # over three left a Chinese reply less room than the chunk it answers.
            max_tokens = min(max(self.estimate_tokens(chunk) * 2, 1024),
                             self.ANTHROPIC_MAX_OUTPUT_TOKENS)
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=f"{prompt_text}\n\n{self.ENHANCEMENT_OUTPUT_DIRECTIVE}",
                messages=[{"role": "user", "content": chunk}],
            )
            if response.stop_reason == "max_tokens":
                # Output was cut off mid-sentence; keep the original chunk rather
                # than silently save truncated text.
                print(f"  Warning: response truncated at {max_tokens} tokens; "
                      "keeping original chunk to avoid content loss.")
                return ""
            return "".join(
                block.text for block in response.content if block.type == "text"
            ).strip()

        result = self._run_chunked_enhancement(chunks, "anthropic", call_chunk, seams)
        print("anthropic enhancement complete.")
        return result

    def enhance_with_local(self, text: str, prompt_text: str, local_model: str | LocalModel,
                           keeps: str = "all") -> str:
        """Enhance transcript text with a local HuggingFace model. Returns `text` on failure.

        keeps is what a reply holds of its chunk, and so how it is checked:
        "words" for a refinement, the speaker's own words; "all" for a prompt
        that carries the whole of it in other words, a translation; "some" for
        a summary, shorter on purpose, which a check for a model that stopped
        early would refuse chunk by chunk.
        """
        try:
            from transformers import AutoTokenizer, pipeline
        except ImportError:
            print("Warning: 'transformers' package not installed. Skipping local enhancement.")
            print("Install with: pip install transformers torch")
            return text

        try:
            import torch
        except ImportError:
            print("Warning: 'torch' package not installed or not available. "
                  "Skipping local enhancement.")
            print("Install with: pip install torch")
            return text

        try:
            torch_version = torch.__version__.split('+')[0]
            major, minor = (int(p) for p in torch_version.split('.')[:2])
            if (major, minor) < (2, 2):
                print(f"Note: PyTorch {torch.__version__} is older than the recommended 2.2+. "
                      "Attempting local enhancement anyway; upgrade torch if model loading fails.")
        except Exception:
            print("Note: Unable to determine PyTorch version. Attempting local enhancement anyway.")

        if isinstance(local_model, LocalModel):
            model_id = local_model.hf_model_id
        else:
            model_id = str(local_model)
        print(f"Loading local model: {model_id} (this may take a moment on first run)...")

        try:
            tokenizer = AutoTokenizer.from_pretrained(model_id)
            max_length = getattr(tokenizer, 'model_max_length', 1024)
            # The prompt shares the context with each chunk and its reply. GPT-2
            # reads 1024 tokens and a shipped prompt takes up to 804 of them, so a
            # chunk sized without it failed with "index out of range in self". The
            # 32 covers the chat template's framing.
            prompt_size = len(tokenizer.encode(
                f"{prompt_text}\n\n{self.ENHANCEMENT_OUTPUT_DIRECTIVE}")) + 32
            # A chunk and a reply twice its size in what is left, and each chunk
            # short: Qwen2.5-1.5B returned a 550-word chunk cut down, commented on
            # or swapped for the prompt's example in 5 of 12 runs, a 200-word one
            # in 1 of 6, and a short passage in none; more, shorter calls took
            # about the same time.
            # ponytail: sized for a 1.5B model on CPU; a larger local model can take more
            chunk_max = min((max_length - prompt_size) // 3, 300)
            if chunk_max < 32:
                print(f"Warning: {model_id} reads {max_length} tokens and the prompt takes "
                      f"{prompt_size} of them, leaving no room for the transcript. Skipping "
                      "local enhancement; use a model with a longer context.")
                return text

            accelerate_available = importlib.util.find_spec("accelerate") is not None
            if not accelerate_available:
                print("Warning: 'accelerate' not installed. Loading model without device_map.")

            # transformers called it torch_dtype until 4.56, which renamed it
            # dtype; older ones passed an unknown dtype on to generate(), which
            # refused it for every chunk, and nothing was enhanced
            dtype_argument = ('dtype' if 'dtype' in inspect.signature(pipeline).parameters
                              else 'torch_dtype')
            generator = pipeline(
                'text-generation',
                model=model_id,
                tokenizer=tokenizer,
                device_map="auto" if accelerate_available else None,
                **{dtype_argument: "auto"}
            )
        except Exception as e:
            error(f"Error loading local model '{model_id}': {str(e)}")
            print("Skipping local enhancement.")
            return text

        # Measured by the model's own tokenizer, as chunk_max itself was: the
        # estimate runs high for most models and low for some, and a chunk
        # over its share leaves the reply too little of the context
        chunks, seams = self.chunk_spans(
            text, max_tokens=chunk_max,
            count=lambda span: len(tokenizer.encode(span, add_special_tokens=False)))
        # Instruct/chat models define a chat template; base models (gpt2 etc.) don't
        has_chat_template = getattr(tokenizer, 'chat_template', None) is not None

        print(f"Enhancing transcript with local model ({len(chunks)} chunk(s))...")

        def call_chunk(chunk: str) -> str:
            # Not words: Chinese has no spaces to count them by, and a whole chunk
            # counted as one word, capping the reply at a third of the chunk
            max_new_tokens = max(self.estimate_tokens(chunk) * 2, 256)
            # but never past the end of the context, where the model fails outright
            max_new_tokens = min(max_new_tokens,
                                 max_length - prompt_size - len(tokenizer.encode(chunk)))

            if has_chat_template:
                full_prompt = tokenizer.apply_chat_template(
                    self._build_chat_messages(prompt_text, chunk),
                    tokenize=False, add_generation_prompt=True
                )
                result = generator(
                    full_prompt,
                    max_new_tokens=max_new_tokens,
                    do_sample=True,
                    temperature=0.3,
                    num_return_sequences=1,
                    return_full_text=False
                )
                enhanced = result[0]['generated_text'].strip()
            else:
                full_prompt = f"{prompt_text}\n\n{chunk}\n\nEnhanced version:"
                result = generator(
                    full_prompt,
                    max_new_tokens=max_new_tokens,
                    do_sample=True,
                    temperature=0.3,
                    num_return_sequences=1
                )
                generated = result[0]['generated_text']
                if "Enhanced version:" in generated:
                    enhanced = generated.split("Enhanced version:")[-1].strip()
                else:
                    enhanced = generated[len(full_prompt):].strip()

            # Out of room is a cut-off reply whatever the prompt, as the cloud
            # backends check. Counted before <think> blocks go, and re-encoded
            # from text, which can come out a token short
            if len(tokenizer.encode(enhanced, add_special_tokens=False)) >= max_new_tokens - 1:
                print("  Warning: response truncated at the output limit; "
                      "keeping original chunk to avoid content loss.")
                return ""

            # Reasoning models (e.g., DeepSeek-R1 distills) emit <think> blocks; drop them
            enhanced = re.sub(r'<think>.*?</think>', '', enhanced, flags=re.DOTALL).strip()
            if not enhanced:
                return ""

            # A reply that should be the whole chunk but is under a third of it is
            # usually a model that stopped early. In bytes, not characters: a
            # faithful Chinese translation of English runs to 27% of its characters
            size, whole_size = len(enhanced.encode("utf-8")), len(chunk.encode("utf-8"))
            if keeps != "some" and size < whole_size * 0.3:
                print(f"  The reply was {size * 100 // whole_size}% the size of the chunk, "
                      "too little to be the whole of it.")
                return ""

            # A refinement long enough can still have dropped a paragraph. Clean
            # replies from Qwen2.5-1.5B left out at most 7 words in a row, to filler
            # and misheard words; ones that dropped sentences, 23 and 132.
            # ponytail: measured on English and Spanish; a few dropped words pass
            gap = self.longest_missing_run(chunk, enhanced) if keeps == "words" else 0
            if gap >= 15:
                print(f"  The reply left out {gap} words of the chunk in a row.")
                return ""
            return enhanced

        result = self._run_chunked_enhancement(chunks, "Local model", call_chunk, seams)
        print("Local model enhancement complete.")
        return result

    def enhance_text(self, text: str, mode: AIEnhancementMode | None, prompt_text: str | None,
                     api_key: str | None = None, provider: Provider | None = None,
                     local_model: str | LocalModel | None = None, keeps: str = "all") -> str:
        """Dispatch enhancement to the cloud or local backend.

        api_key/provider apply to API mode, local_model and keeps to LOCAL mode.
        Returns `text` unchanged if enhancement is skipped or fails.
        """
        if not text or not text.strip():
            print("Warning: No text to enhance.")
            return text

        if not prompt_text:
            print("Warning: No prompt loaded. Skipping enhancement.")
            return text

        if mode == AIEnhancementMode.API:
            if not api_key:
                print("Warning: No API key provided. Skipping enhancement.")
                return text
            provider = provider or Provider.default()
            if provider == Provider.ANTHROPIC:
                return self.enhance_with_anthropic(text, prompt_text, api_key, provider)
            return self.enhance_with_openai_compatible(text, prompt_text, api_key, provider)

        elif mode == AIEnhancementMode.LOCAL:
            if not local_model:
                local_model = LocalModel.default().hf_model_id
            return self.enhance_with_local(text, prompt_text, local_model, keeps=keeps)

        else:
            print("Warning: Unknown enhancement mode. Skipping.")
            return text
