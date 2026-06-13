"""
Content Generator Service - Three-Pass Pipeline for Comprehensive Materials
Generates detailed notes and quizzes from lecture transcripts.
"""

import logging
import json
import re
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

from app.services.llm import LLMService, LLMError
from app.services.database import DatabaseService

logger = logging.getLogger(__name__)

# How many topic-level LLM calls to run concurrently.
# Keep modest to avoid provider rate limits while still being much faster than sequential.
TOPIC_WORKERS = 4


def _balance_json(text: str) -> str:
    """
    Best-effort repair of JSON that was cut off mid-output (the classic truncation
    symptom). Strips trailing junk after the last complete element, closes any open
    strings, and balances braces/brackets. Not perfect, but recovers most near-complete
    responses that would otherwise be a total loss.
    """
    s = text.strip()
    # Drop a leading code fence if one slipped through.
    if s.startswith("```"):
        s = s.split("```", 2)[-1] if s.count("```") >= 2 else s.lstrip("`")
        s = s.replace("json", "", 1).strip() if s.lower().startswith("json") else s
    # Walk the string tracking structure; remember the last position that was a
    # "safe" cut point (end of a complete value, i.e. not inside a string).
    stack = []
    in_string = False
    escape = False
    for ch in s:
        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]":
            if stack:
                stack.pop()
    # Close an unterminated string, drop a dangling comma, then close open containers.
    repaired = s
    if in_string:
        repaired += '"'
    repaired = re.sub(r",\s*$", "", repaired.rstrip())
    while stack:
        repaired += stack.pop()
    return repaired


def safe_json_loads(text: str, *, context: str = "response") -> Dict[str, Any]:
    """
    Parse LLM JSON robustly: direct parse, then strip code fences, then balance-repair.
    Raises ContentGeneratorError only if every strategy fails.
    """
    if text is None:
        raise ContentGeneratorError(f"Empty {context} (None) from LLM")

    # 1. Direct
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. Extract from markdown fences if present
    candidate = text
    if "```json" in candidate:
        candidate = candidate.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in candidate:
        parts = candidate.split("```")
        if len(parts) >= 3:
            candidate = parts[1]
    candidate = candidate.strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    # 3. Optional: json_repair library if installed (much smarter than our balancer)
    try:
        import json_repair  # type: ignore
        repaired = json_repair.loads(candidate)
        if isinstance(repaired, (dict, list)):
            logger.warning(f"Recovered {context} JSON via json_repair")
            return repaired
    except ImportError:
        pass
    except Exception:
        pass

    # 4. Last resort: balance braces/strings ourselves (handles truncation)
    try:
        result = json.loads(_balance_json(candidate))
        logger.warning(f"Recovered {context} JSON via brace-balancing (was likely truncated)")
        return result
    except json.JSONDecodeError as e:
        raise ContentGeneratorError(f"Could not parse {context} as JSON even after repair: {e}")


def _split_note_blocks(markdown: str) -> List[str]:
    """
    Split notes Markdown into blocks at top-level `---` horizontal rules, ignoring any
    `---` that appears inside a fenced code block. The per-topic notes are assembled with
    `---` separators, so this yields roughly one section per block — small enough that each
    translation call stays well under the output-token cap. Separators are dropped; callers
    rejoin blocks with the same `---` rule.
    """
    blocks: List[str] = []
    current: List[str] = []
    in_fence = False
    for line in markdown.split("\n"):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            current.append(line)
            continue
        if not in_fence and stripped == "---":
            blocks.append("\n".join(current).strip())
            current = []
            continue
        current.append(line)
    blocks.append("\n".join(current).strip())
    return [b for b in blocks if b]


def _atomize_paragraphs(text: str) -> List[str]:
    """
    Split a block into paragraph atoms on blank lines, keeping fenced code blocks intact
    (a code block is never split, even if it contains blank lines). Used to break an
    oversized section into translatable pieces without cutting through code or sentences.
    """
    atoms: List[str] = []
    current: List[str] = []
    in_fence = False
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            current.append(line)
            continue
        if not in_fence and stripped == "":
            if current:
                atoms.append("\n".join(current))
                current = []
            continue
        current.append(line)
    if current:
        atoms.append("\n".join(current))
    return atoms


def _pack_atoms(atoms: List[str], max_chars: int) -> List[str]:
    """Greedily pack paragraph atoms into pieces no larger than max_chars (a single oversized
    atom, e.g. a long code block, becomes its own piece rather than being split)."""
    pieces: List[str] = []
    buf: List[str] = []
    size = 0
    for atom in atoms:
        alen = len(atom) + 2  # account for the "\n\n" join
        if buf and size + alen > max_chars:
            pieces.append("\n\n".join(buf))
            buf, size = [], 0
        buf.append(atom)
        size += alen
    if buf:
        pieces.append("\n\n".join(buf))
    return pieces


def _distribute(total: int, buckets: int) -> List[int]:
    """Spread `total` items across `buckets` as evenly as possible (front-loaded)."""
    if buckets <= 0 or total <= 0:
        return [0] * max(buckets, 0)
    base, rem = divmod(total, buckets)
    return [base + (1 if i < rem else 0) for i in range(buckets)]


class ContentGeneratorError(Exception):
    """Raised when content generation fails."""
    pass


class ContentGenerator:
    """
    Three-pass content generation pipeline:
    1. Pass 1: Extract complete outline from full transcript
    2. Pass 2: Generate detailed notes and quizzes from outline
    3. Pass 3: Verification & coverage report
    """

    def __init__(self):
        self.llm = LLMService()
        self.db = DatabaseService()
        self.logs_dir = Path("logs/content_generation")
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        logger.info("Initialized ContentGenerator service")

    def _load_prompt(self, prompt_file: str) -> str:
        """Load prompt template from file."""
        prompt_path = Path(__file__).parent.parent.parent / "prompts" / prompt_file
        if not prompt_path.exists():
            raise ContentGeneratorError(f"Prompt file not found: {prompt_path}")
        return prompt_path.read_text(encoding="utf-8")

    def _save_json(self, data: Dict[str, Any], filename: str) -> Path:
        """Save data as JSON with timestamp."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = self.logs_dir / f"{filename}_{timestamp}.json"

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"Saved {filename} to {filepath}")
        return filepath

    def _count_tokens_estimate(self, text: str) -> int:
        """Rough token estimate (chars / 4)."""
        return len(text) // 4

    def get_transcript_text(self, lecture_id: str) -> str:
        """
        Fetch a lecture's transcript and flatten it to plain text.

        Prefers the LLM-cleaned transcript (filler/ASR noise removed) so notes/quiz/
        outline are built from clean text; falls back to the raw transcript if a lecture
        was ingested before cleaning was wired in.
        """
        lecture = self.db.get_lecture(lecture_id)
        if not lecture:
            raise ContentGeneratorError(f"No lecture found for {lecture_id}")

        transcript_data = lecture.get('cleaned_transcript') or lecture.get('full_transcript')
        if not transcript_data:
            raise ContentGeneratorError(f"No transcript found for lecture {lecture_id}")

        if isinstance(transcript_data, str):
            transcript_data = json.loads(transcript_data)

        return "\n".join(seg["text"] for seg in transcript_data if "text" in seg)

    def pass1_extract_outline(
        self,
        lecture_id: str,
        full_transcript: str,
        show_progress: bool = True
    ) -> Dict[str, Any]:
        """
        Pass 1: Extract complete structured outline from full transcript.

        Args:
            lecture_id: UUID of lecture
            full_transcript: Complete transcript text
            show_progress: Show progress messages

        Returns:
            Structured outline as JSON with topics, concepts, definitions, examples

        Raises:
            ContentGeneratorError: If extraction fails
        """
        try:
            if show_progress:
                tokens = self._count_tokens_estimate(full_transcript)
                print(f"\n{'='*60}")
                print(f"[PASS 1] Extracting outline from transcript")
                print(f"Lecture ID: {lecture_id}")
                print(f"Transcript length: {len(full_transcript)} chars (~{tokens} tokens)")
                print(f"Model: {self.llm.complex_model}")
                print(f"{'='*60}\n")

            start_time = time.time()

            # Load prompt template
            prompt_template = self._load_prompt("outline_extraction.txt")

            # Combine template with full transcript
            full_prompt = prompt_template.replace("{{TRANSCRIPT}}", full_transcript)

            # Call LLM with complex model (better for analysis)
            # Retry up to 2 times if JSON parsing fails
            max_retries = 2
            response = None

            for attempt in range(max_retries):
                try:
                    response = self.llm.complete(
                        prompt=full_prompt,
                        model="complex",  # Use deepseek-v4-pro for better analysis
                        temperature=0.2,
                        max_tokens=16192,  # Large output for comprehensive outline
                        json_mode=True  # Force pure JSON output
                    )
                    # Try to parse immediately to validate
                    json.loads(response)
                    break  # Success, exit retry loop
                except json.JSONDecodeError as e:
                    if attempt < max_retries - 1:
                        logger.warning(f"Attempt {attempt + 1}/{max_retries} failed to parse JSON, retrying...")
                        time.sleep(2)
                    else:
                        # Last attempt failed, will be handled below
                        pass

            # Parse JSON response
            try:
                outline = json.loads(response)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse outline JSON: {e}")

                # Save raw response for debugging
                debug_file = self.logs_dir / f"debug_outline_{lecture_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                debug_file.write_text(response, encoding='utf-8')
                logger.error(f"Saved raw response to {debug_file}")

                # Try to extract JSON from markdown code blocks
                if "```json" in response:
                    json_text = response.split("```json")[1].split("```")[0].strip()
                    try:
                        outline = json.loads(json_text)
                    except json.JSONDecodeError:
                        raise ContentGeneratorError(f"LLM response is not valid JSON even after extraction: {e}")
                elif "```" in response:
                    json_text = response.split("```")[1].split("```")[0].strip()
                    try:
                        outline = json.loads(json_text)
                    except json.JSONDecodeError:
                        raise ContentGeneratorError(f"LLM response is not valid JSON even after extraction: {e}")
                else:
                    # Try to find JSON object in response
                    import re
                    json_match = re.search(r'\{.*\}', response, re.DOTALL)
                    if json_match:
                        try:
                            outline = json.loads(json_match.group(0))
                        except json.JSONDecodeError:
                            raise ContentGeneratorError(f"LLM response is not valid JSON: {e}. Saved to {debug_file}")
                    else:
                        raise ContentGeneratorError(f"LLM response is not valid JSON: {e}. Saved to {debug_file}")

            # Add metadata
            outline["lecture_id"] = lecture_id
            outline["generated_at"] = datetime.now().isoformat()
            outline["pass"] = "outline_extraction"

            duration = time.time() - start_time

            if show_progress:
                num_topics = len(outline.get("topics", []))
                num_concepts = sum(len(topic.get("concepts", [])) for topic in outline.get("topics", []))
                print(f"\n[PASS 1 SUCCESS] Extracted outline in {duration:.1f}s")
                print(f"  Topics: {num_topics}")
                print(f"  Concepts: {num_concepts}")
                print(f"  Output size: {len(response)} chars")

            # Save outline
            self._save_json(outline, f"outline_{lecture_id}")

            return outline

        except Exception as e:
            error_msg = f"Pass 1 (outline extraction) failed: {str(e)}"
            logger.error(error_msg)
            raise ContentGeneratorError(error_msg)

    @staticmethod
    def _get_topics(outline: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Return the top-level topics list from an outline (empty list if absent)."""
        topics = outline.get("topics")
        return topics if isinstance(topics, list) else []

    @staticmethod
    def _topic_title(topic: Dict[str, Any], index: int) -> str:
        return topic.get("title") or topic.get("name") or f"Topic {index + 1}"

    def _build_notes_header(self, outline: Dict[str, Any], topic_titles: List[str]) -> str:
        """Build the document title + table of contents that wraps the per-topic sections."""
        meta = outline.get("lecture_metadata", {}) or {}
        subject = meta.get("subject") or "Vorlesungsnotizen"
        lines = [f"# {subject}", ""]
        main_topics = meta.get("main_topics")
        if main_topics:
            lines.append(f"> **Themen:** {', '.join(str(t) for t in main_topics)}")
            lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## Inhaltsverzeichnis")
        for i, title in enumerate(topic_titles, 1):
            lines.append(f"{i}. {title}")
        lines.append("")
        lines.append("---")
        lines.append("")
        return "\n".join(lines)

    def pass2_generate_notes(
        self,
        lecture_id: str,
        outline: Dict[str, Any],
        show_progress: bool = True
    ) -> str:
        """
        Pass 2a: Generate detailed notes from outline, ONE topic per LLM call in parallel.

        Generating per-topic keeps each call small enough to never hit the output-token
        cap (the cause of truncated/incomplete notes) and runs them concurrently for speed.
        Falls back to a single whole-outline call if the outline has no topics array.

        Returns:
            Markdown formatted detailed notes

        Raises:
            ContentGeneratorError: If generation fails
        """
        try:
            topics = self._get_topics(outline)

            if show_progress:
                print(f"\n{'='*60}")
                print(f"[PASS 2A] Generating notes ({len(topics)} topics, {TOPIC_WORKERS} workers)")
                print(f"Lecture ID: {lecture_id}")
                print(f"Model: {self.llm.complex_model}")
                print(f"{'='*60}\n")

            start_time = time.time()

            if not topics:
                logger.warning("Outline has no topics; falling back to single-call notes generation")
                notes_markdown = self._generate_notes_whole(outline)
            else:
                notes_markdown = self._generate_notes_per_topic(outline, topics, show_progress)

            duration = time.time() - start_time

            if show_progress:
                print(f"\n[PASS 2A SUCCESS] Generated notes in {duration:.1f}s")
                print(f"  Length: {len(notes_markdown)} chars")
                print(f"  Lines: {notes_markdown.count(chr(10))}")

            # Save notes
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            notes_file = self.logs_dir / f"notes_{lecture_id}_{timestamp}.md"
            notes_file.write_text(notes_markdown, encoding='utf-8')
            logger.info(f"Saved notes to {notes_file}")

            return notes_markdown

        except ContentGeneratorError:
            raise
        except Exception as e:
            error_msg = f"Pass 2a (notes generation) failed: {str(e)}"
            logger.error(error_msg)
            raise ContentGeneratorError(error_msg)

    def _generate_notes_whole(self, outline: Dict[str, Any]) -> str:
        """Fallback: original single-call notes generation for outlines without topics."""
        prompt_template = self._load_prompt("notes_generation.txt")
        outline_json = json.dumps(outline, indent=2, ensure_ascii=False)
        full_prompt = prompt_template.replace("{{OUTLINE}}", outline_json)
        return self.llm.complete(
            prompt=full_prompt, model="complex", temperature=0.3, max_tokens=16384
        )

    def _generate_notes_per_topic(
        self,
        outline: Dict[str, Any],
        topics: List[Dict[str, Any]],
        show_progress: bool
    ) -> str:
        """Generate one markdown section per topic in parallel, then assemble in order."""
        prompt_template = self._load_prompt("notes_topic.txt")
        topic_titles = [self._topic_title(t, i) for i, t in enumerate(topics)]

        def gen_one(index: int, topic: Dict[str, Any]) -> tuple[int, str]:
            title = topic_titles[index]
            topic_json = json.dumps(topic, indent=2, ensure_ascii=False)
            prompt = (prompt_template
                      .replace("{{TOPIC_TITLE}}", title)
                      .replace("{{TOPIC}}", topic_json))
            # Notes are markdown, so truncation degrades gracefully (no JSON to break).
            # 8k tokens is plenty for one topic and well under the cap.
            section = self.llm.complete(
                prompt=prompt, model="complex", temperature=0.3, max_tokens=8000
            ).strip()
            # Strip a stray document title if the model added one.
            if section.startswith("# "):
                section = "## " + section[2:]
            return index, section

        sections: Dict[int, str] = {}
        completed = 0
        with ThreadPoolExecutor(max_workers=TOPIC_WORKERS) as executor:
            futures = {executor.submit(gen_one, i, t): i for i, t in enumerate(topics)}
            for future in as_completed(futures):
                i = futures[future]
                try:
                    idx, section = future.result()
                    sections[idx] = section
                except Exception as e:
                    logger.error(f"Notes for topic {i} ('{topic_titles[i]}') failed: {e}")
                    sections[i] = f"## {topic_titles[i]}\n\n_(Notizen für dieses Thema konnten nicht generiert werden.)_"
                completed += 1
                if show_progress:
                    print(f"  [notes] {completed}/{len(topics)} topics done")

        header = self._build_notes_header(outline, topic_titles)
        body = "\n\n---\n\n".join(sections[i] for i in range(len(topics)))
        return header + body + "\n"

    # Supported translation targets: code -> language name used in the prompt.
    TRANSLATION_LANGUAGES = {"pl": "Polish", "en": "English"}

    # Accepted spellings for the target language, mapped to the canonical code.
    _LANGUAGE_ALIASES = {
        "pl": "pl", "polish": "pl", "polski": "pl",
        "en": "en", "english": "en", "angielski": "en",
    }

    @classmethod
    def normalize_language(cls, language: str) -> Optional[str]:
        """Map a user-supplied language ('Polish', 'pl', 'angielski', ...) to 'pl'/'en', or None."""
        if not language:
            return None
        return cls._LANGUAGE_ALIASES.get(language.strip().lower())

    # Translate sections this size or smaller per call; larger ones get sub-split first.
    # ~3000 chars -> well under the 8000-token output cap even at Polish token density.
    _TRANSLATE_MAX_CHARS = 3000

    @staticmethod
    def _translate_max_tokens(text: str) -> int:
        """
        Token budget for translating one piece.

        DeepSeek tokenizes target languages like Polish very densely (accented chars
        ł/ś/ż/ą often cost ~1 token each), so the OUTPUT can need roughly as many tokens
        as the source has characters — sometimes more. We therefore budget ~1.8x the char
        count (not the < 1x that was truncating Polish), with a 2048 floor for tiny pieces
        and the 8000 model-output ceiling. Pieces are pre-split to _TRANSLATE_MAX_CHARS so
        this stays under the ceiling in practice.
        """
        return min(max(2048, int(len(text) * 1.8)), 8000)

    @staticmethod
    def _strip_wrapping_fence(text: str) -> str:
        """Drop a code fence the model may have wrapped the whole answer in (```markdown ... ```)."""
        first, _, rest = text.partition("\n")
        if first.strip() in ("```", "```markdown", "```md") and text.rstrip().endswith("```"):
            body = rest.rstrip()
            if body.endswith("```"):
                body = body[: -3].rstrip()
            return body
        return text

    def translate_notes(
        self,
        notes_markdown: str,
        target_language: str,
        show_progress: bool = True,
    ) -> str:
        """
        Translate already-generated (German) notes into the target language.

        Splits the notes on top-level `---` rules and translates each block in parallel
        with the cheap/fast model (`simple` = deepseek-v4-flash), then reassembles. Keeping
        each call small avoids the output-token cap; a block that fails to translate falls
        back to the original so the document is never lost.

        Args:
            notes_markdown: The source notes (German) as Markdown.
            target_language: 'pl'/'polish' or 'en'/'english' (case-insensitive).
            show_progress: Print per-block progress.

        Returns:
            Translated Markdown notes.

        Raises:
            ContentGeneratorError: If the language is unsupported or notes are empty.
        """
        lang_code = self.normalize_language(target_language)
        lang_name = self.TRANSLATION_LANGUAGES.get(lang_code) if lang_code else None
        if not lang_name:
            raise ContentGeneratorError(
                f"Unsupported translation language: {target_language!r} (supported: pl, en)"
            )
        if not notes_markdown or not notes_markdown.strip():
            raise ContentGeneratorError("Cannot translate empty notes")

        prompt_template = self._load_prompt("notes_translation.txt")

        # Split into top-level blocks (on `---`), then sub-split any block that exceeds the
        # per-call size so no single translation can approach the output-token cap. Each unit
        # is a list of pieces; pieces of a block are rejoined with blank lines, blocks with `---`.
        blocks = _split_note_blocks(notes_markdown) or [notes_markdown.strip()]
        units: List[List[str]] = [
            [block] if len(block) <= self._TRANSLATE_MAX_CHARS
            else _pack_atoms(_atomize_paragraphs(block), self._TRANSLATE_MAX_CHARS)
            for block in blocks
        ]
        # Flat job list across all pieces so every call runs in the same parallel pool.
        jobs = [(bi, pi, piece)
                for bi, pieces in enumerate(units)
                for pi, piece in enumerate(pieces)]

        if show_progress:
            print(f"\n{'='*60}")
            print(f"[TRANSLATE] {len(blocks)} blocks ({len(jobs)} pieces) -> {lang_name} ({lang_code})")
            print(f"Model: {self.llm.simple_model}")
            print(f"{'='*60}\n")

        start_time = time.time()

        def translate_piece(bi: int, pi: int, text: str) -> tuple[int, int, str]:
            prompt = (prompt_template
                      .replace("{{TARGET_LANGUAGE}}", lang_name)
                      .replace("{{NOTES}}", text))
            out, finish = self.llm.complete(
                prompt=prompt,
                model="simple",  # cheap/fast model for translation
                temperature=0.2,
                max_tokens=self._translate_max_tokens(text),
                return_finish_reason=True,
            )
            # If the target language was denser than estimated and we still hit the cap,
            # retry once at the ceiling so the piece isn't left truncated.
            if finish == "length":
                logger.warning(f"Translation piece ({bi},{pi}) -> {lang_code} truncated; retrying at max budget")
                retry, _ = self.llm.complete(
                    prompt=prompt, model="simple", temperature=0.2,
                    max_tokens=8000, return_finish_reason=True,
                )
                if len(retry.strip()) > len(out.strip()):
                    out = retry
            out = out.strip()
            return bi, pi, self._strip_wrapping_fence(out) or text

        # results[block_index][piece_index] = translated text
        results: Dict[int, Dict[int, str]] = {bi: {} for bi in range(len(units))}
        completed = 0
        with ThreadPoolExecutor(max_workers=TOPIC_WORKERS) as executor:
            futures = {executor.submit(translate_piece, bi, pi, text): (bi, pi)
                       for bi, pi, text in jobs}
            for future in as_completed(futures):
                bi, pi = futures[future]
                try:
                    rbi, rpi, translated = future.result()
                    results[rbi][rpi] = translated
                except Exception as e:
                    logger.error(f"Translation of piece ({bi},{pi}) -> {lang_code} failed: {e}; keeping original")
                    results[bi][pi] = units[bi][pi]
                completed += 1
                if show_progress:
                    print(f"  [translate->{lang_code}] {completed}/{len(jobs)} pieces done")

        block_strs = [
            "\n\n".join(results[bi][pi] for pi in range(len(units[bi])))
            for bi in range(len(units))
        ]
        translated_notes = "\n\n---\n\n".join(block_strs) + "\n"

        if show_progress:
            duration = time.time() - start_time
            print(f"\n[TRANSLATE SUCCESS] {len(blocks)} blocks -> {lang_name} in {duration:.1f}s "
                  f"({len(translated_notes)} chars)")

        return translated_notes

    def pass2_generate_quiz(
        self,
        lecture_id: str,
        outline: Dict[str, Any],
        num_questions: int = 20,
        show_progress: bool = True
    ) -> Dict[str, Any]:
        """
        Pass 2b: Generate quiz from outline.

        Args:
            lecture_id: UUID of lecture
            outline: Structured outline from Pass 1
            num_questions: Number of quiz questions to generate
            show_progress: Show progress messages

        Returns:
            Quiz data with questions, options, correct answers

        Raises:
            ContentGeneratorError: If generation fails
        """
        try:
            topics = self._get_topics(outline)

            if show_progress:
                print(f"\n{'='*60}")
                print(f"[PASS 2B] Generating quiz ({num_questions} questions across {len(topics)} topics)")
                print(f"Lecture ID: {lecture_id}")
                print(f"Model: {self.llm.complex_model}")
                print(f"{'='*60}\n")

            start_time = time.time()

            if not topics:
                logger.warning("Outline has no topics; falling back to single-call quiz generation")
                questions = self._generate_quiz_whole(outline, num_questions, lecture_id)
            else:
                questions = self._generate_quiz_per_topic(outline, topics, num_questions, lecture_id, show_progress)

            # Renumber sequentially and assemble final quiz object
            for new_id, q in enumerate(questions, 1):
                q["question_id"] = new_id

            quiz_data = {
                "quiz_metadata": {
                    "total_questions": len(questions),
                    "topics_covered": sorted({q.get("topic", "") for q in questions if q.get("topic")}),
                    "difficulty_distribution": self._difficulty_counts(questions),
                },
                "questions": questions,
                "lecture_id": lecture_id,
                "generated_at": datetime.now().isoformat(),
                "pass": "quiz_generation",
            }

            duration = time.time() - start_time

            if show_progress:
                print(f"\n[PASS 2B SUCCESS] Generated quiz in {duration:.1f}s")
                print(f"  Questions generated: {len(questions)} (requested {num_questions})")

            self._save_json(quiz_data, f"quiz_{lecture_id}")
            return quiz_data

        except ContentGeneratorError:
            raise
        except Exception as e:
            error_msg = f"Pass 2b (quiz generation) failed: {str(e)}"
            logger.error(error_msg)
            raise ContentGeneratorError(error_msg)

    # Required keys for a usable quiz question (per app.models.content.QuizQuestion).
    _QUIZ_REQUIRED = ("type", "difficulty", "topic", "question_text", "correct_answer", "explanation")

    @staticmethod
    def _difficulty_counts(questions: List[Dict[str, Any]]) -> Dict[str, int]:
        counts = {"basic": 0, "intermediate": 0, "advanced": 0}
        for q in questions:
            d = q.get("difficulty")
            if d in counts:
                counts[d] += 1
        return counts

    def _validate_questions(self, raw: Any, topic_title: str) -> List[Dict[str, Any]]:
        """Keep only well-formed questions; drop malformed ones instead of failing the batch."""
        if isinstance(raw, dict):
            raw = raw.get("questions", [])
        if not isinstance(raw, list):
            return []
        valid = []
        for q in raw:
            if not isinstance(q, dict):
                continue
            if not all(q.get(k) for k in self._QUIZ_REQUIRED):
                logger.warning(f"Dropping malformed quiz question in topic '{topic_title}': missing fields")
                continue
            q.setdefault("topic", topic_title)
            q.pop("question_id", None)  # reassigned globally later
            valid.append(q)
        return valid

    def _generate_quiz_whole(
        self, outline: Dict[str, Any], num_questions: int, lecture_id: str
    ) -> List[Dict[str, Any]]:
        """Fallback: original single-call quiz generation for outlines without topics."""
        prompt_template = self._load_prompt("quiz_generation.txt")
        outline_json = json.dumps(outline, indent=2, ensure_ascii=False)
        prompt = (prompt_template
                  .replace("{{OUTLINE}}", outline_json)
                  .replace("{{NUM_QUESTIONS}}", str(num_questions)))
        response, finish = self.llm.complete(
            prompt=prompt, model="complex", temperature=0.4,
            max_tokens=min(num_questions * 1400 + 1000, 16384),
            json_mode=True, return_finish_reason=True,
        )
        if finish == "length":
            logger.warning("Whole-outline quiz hit token cap; some questions may be lost")
        return self._validate_questions(safe_json_loads(response, context="quiz"), "")

    def _generate_quiz_per_topic(
        self,
        outline: Dict[str, Any],
        topics: List[Dict[str, Any]],
        num_questions: int,
        lecture_id: str,
        show_progress: bool,
    ) -> List[Dict[str, Any]]:
        """Generate each topic's share of questions in parallel, then merge."""
        prompt_template = self._load_prompt("quiz_topic.txt")
        topic_titles = [self._topic_title(t, i) for i, t in enumerate(topics)]
        allocation = _distribute(num_questions, len(topics))

        # Only call topics that were allocated questions.
        jobs = [(i, topics[i], allocation[i]) for i in range(len(topics)) if allocation[i] > 0]

        def gen_batch(title: str, topic_json: str, n: int) -> List[Dict[str, Any]]:
            """One LLM call for n questions on a topic. Budget is generous per question
            (detailed explanations in any language run ~800-1200 tokens each) so a small
            batch stays well under the cap and the JSON always closes."""
            prompt = (prompt_template
                      .replace("{{NUM_QUESTIONS}}", str(n))
                      .replace("{{TOPIC_TITLE}}", title)
                      .replace("{{TOPIC}}", topic_json))
            response, finish = self.llm.complete(
                prompt=prompt, model="complex", temperature=0.4,
                max_tokens=min(n * 1400 + 800, 12000),
                json_mode=True, return_finish_reason=True,
            )
            if finish == "length":
                logger.warning(f"Quiz batch for topic '{title}' still truncated; repairing")
            return self._validate_questions(safe_json_loads(response, context=f"quiz[{title}]"), title)

        def gen_one(index: int, topic: Dict[str, Any], n: int) -> tuple[int, List[Dict[str, Any]]]:
            title = topic_titles[index]
            topic_json = json.dumps(topic, indent=2, ensure_ascii=False)
            questions = gen_batch(title, topic_json, n)
            # One top-up attempt if the batch came back short (truncation/drops).
            if len(questions) < n:
                shortfall = n - len(questions)
                logger.info(f"Topic '{title}' returned {len(questions)}/{n}; topping up {shortfall}")
                questions += gen_batch(title, topic_json, shortfall)
            return index, questions[:n]

        results: Dict[int, List[Dict[str, Any]]] = {}
        completed = 0
        with ThreadPoolExecutor(max_workers=TOPIC_WORKERS) as executor:
            futures = {executor.submit(gen_one, i, t, n): i for i, t, n in jobs}
            for future in as_completed(futures):
                i = futures[future]
                try:
                    idx, questions = future.result()
                    results[idx] = questions
                except Exception as e:
                    logger.error(f"Quiz for topic {i} ('{topic_titles[i]}') failed: {e}")
                    results[i] = []
                completed += 1
                if show_progress:
                    got = len(results.get(i, []))
                    print(f"  [quiz] {completed}/{len(jobs)} topics done | +{got} questions")

        # Merge in topic order
        merged: List[Dict[str, Any]] = []
        for i in range(len(topics)):
            merged.extend(results.get(i, []))
        return merged

    def pass3_verify_coverage(
        self,
        lecture_id: str,
        outline: Dict[str, Any],
        notes: str,
        quiz: Dict[str, Any],
        show_progress: bool = True
    ) -> Dict[str, Any]:
        """
        Pass 3: Verify coverage and generate report.

        Args:
            lecture_id: UUID of lecture
            outline: Outline from Pass 1
            notes: Generated notes from Pass 2a
            quiz: Generated quiz from Pass 2b
            show_progress: Show progress messages

        Returns:
            Coverage report with statistics and gaps

        Raises:
            ContentGeneratorError: If verification fails
        """
        try:
            if show_progress:
                print(f"\n{'='*60}")
                print(f"[PASS 3] Verifying coverage")
                print(f"Lecture ID: {lecture_id}")
                print(f"Model: {self.llm.simple_model}")
                print(f"{'='*60}\n")

            start_time = time.time()

            # Load prompt template
            prompt_template = self._load_prompt("coverage_verification.txt")

            # Prepare data for verification
            outline_json = json.dumps(outline, indent=2, ensure_ascii=False)
            quiz_json = json.dumps(quiz, indent=2, ensure_ascii=False)

            full_prompt = prompt_template.replace("{{OUTLINE}}", outline_json)
            full_prompt = full_prompt.replace("{{NOTES}}", notes[:20000])  # Truncate if too long
            full_prompt = full_prompt.replace("{{QUIZ}}", quiz_json)

            # Call LLM. Bigger budget + json_mode + robust parsing: the coverage report is
            # a sizeable nested object, and 4096 tokens was truncating it mid-JSON.
            response, finish = self.llm.complete(
                prompt=full_prompt,
                model="simple",  # Simple model sufficient for verification
                temperature=0.1,
                max_tokens=8000,
                json_mode=True,
                return_finish_reason=True,
            )
            if finish == "length":
                logger.warning("Coverage report truncated; attempting repair")

            report = safe_json_loads(response, context="coverage report")

            # Add metadata
            report["lecture_id"] = lecture_id
            report["generated_at"] = datetime.now().isoformat()
            report["pass"] = "coverage_verification"

            duration = time.time() - start_time

            if show_progress:
                coverage = report.get("overall_assessment", {}).get("coverage_percent", 0)
                gaps = len(report.get("gaps", []))
                print(f"\n[PASS 3 SUCCESS] Coverage verification in {duration:.1f}s")
                print(f"  Coverage: {coverage}%")
                print(f"  Gaps found: {gaps}")

            # Save report
            self._save_json(report, f"coverage_{lecture_id}")

            return report

        except Exception as e:
            error_msg = f"Pass 3 (coverage verification) failed: {str(e)}"
            logger.error(error_msg)
            raise ContentGeneratorError(error_msg)

    def generate_all(
        self,
        lecture_id: str,
        num_quiz_questions: int = 20,
        show_progress: bool = True
    ) -> Dict[str, Any]:
        """
        Run complete three-pass pipeline for a lecture.

        Args:
            lecture_id: UUID of lecture
            num_quiz_questions: Number of quiz questions
            show_progress: Show progress messages

        Returns:
            Dict with outline, notes, quiz, and coverage report

        Raises:
            ContentGeneratorError: If any pass fails
        """
        try:
            # Get full transcript from database
            full_text = self.get_transcript_text(lecture_id)

            if show_progress:
                print(f"\n{'='*70}")
                print(f"THREE-PASS CONTENT GENERATION PIPELINE")
                print(f"Lecture ID: {lecture_id}")
                print(f"Transcript: {len(full_text)} chars")
                print(f"{'='*70}")

            # Pass 1: Extract outline
            outline = self.pass1_extract_outline(lecture_id, full_text, show_progress)

            # Pass 2a: Generate notes
            notes = self.pass2_generate_notes(lecture_id, outline, show_progress)

            # Pass 2b: Generate quiz
            quiz = self.pass2_generate_quiz(lecture_id, outline, num_quiz_questions, show_progress)

            # Pass 3: Verify coverage
            coverage_report = self.pass3_verify_coverage(
                lecture_id, outline, notes, quiz, show_progress
            )

            # Combine results
            result = {
                "lecture_id": lecture_id,
                "outline": outline,
                "notes": notes,
                "quiz": quiz,
                "coverage_report": coverage_report,
                "generated_at": datetime.now().isoformat()
            }

            if show_progress:
                print(f"\n{'='*70}")
                print(f"[PIPELINE COMPLETE]")
                print(f"  ✓ Outline extracted")
                print(f"  ✓ Notes generated ({len(notes)} chars)")
                print(f"  ✓ Quiz generated ({len(quiz.get('questions', []))} questions)")
                print(f"  ✓ Coverage verified ({coverage_report.get('coverage_percent', 0)}%)")
                print(f"{'='*70}\n")

            return result

        except Exception as e:
            error_msg = f"Three-pass pipeline failed: {str(e)}"
            logger.error(error_msg)
            raise ContentGeneratorError(error_msg)


# Test script
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    generator = ContentGenerator()

    # Test with a lecture ID
    lecture_id = "your-lecture-uuid-here"

    try:
        result = generator.generate_all(lecture_id, num_quiz_questions=10)
        print("\nGeneration complete!")
        print(f"Results saved to: {generator.logs_dir}")
    except ContentGeneratorError as e:
        print(f"Error: {e}")
