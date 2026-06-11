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
import time

from app.services.llm import LLMService, LLMError
from app.services.database import DatabaseService

logger = logging.getLogger(__name__)


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

    def pass2_generate_notes(
        self,
        lecture_id: str,
        outline: Dict[str, Any],
        show_progress: bool = True
    ) -> str:
        """
        Pass 2a: Generate detailed notes from outline.

        Args:
            lecture_id: UUID of lecture
            outline: Structured outline from Pass 1
            show_progress: Show progress messages

        Returns:
            Markdown formatted detailed notes

        Raises:
            ContentGeneratorError: If generation fails
        """
        try:
            if show_progress:
                print(f"\n{'='*60}")
                print(f"[PASS 2A] Generating detailed notes from outline")
                print(f"Lecture ID: {lecture_id}")
                print(f"Model: {self.llm.complex_model}")
                print(f"{'='*60}\n")

            start_time = time.time()

            # Load prompt template
            prompt_template = self._load_prompt("notes_generation.txt")

            # Serialize outline to JSON for prompt
            outline_json = json.dumps(outline, indent=2, ensure_ascii=False)
            full_prompt = prompt_template.replace("{{OUTLINE}}", outline_json)

            # Call LLM
            notes_markdown = self.llm.complete(
                prompt=full_prompt,
                model="complex",
                temperature=0.3,
                max_tokens=16384  # Very large for comprehensive notes
            )

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

        except Exception as e:
            error_msg = f"Pass 2a (notes generation) failed: {str(e)}"
            logger.error(error_msg)
            raise ContentGeneratorError(error_msg)

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
            if show_progress:
                print(f"\n{'='*60}")
                print(f"[PASS 2B] Generating quiz from outline")
                print(f"Lecture ID: {lecture_id}")
                print(f"Questions: {num_questions}")
                print(f"Model: {self.llm.complex_model}")
                print(f"{'='*60}\n")

            start_time = time.time()

            # Load prompt template
            prompt_template = self._load_prompt("quiz_generation.txt")

            # Serialize outline to JSON for prompt
            outline_json = json.dumps(outline, indent=2, ensure_ascii=False)
            full_prompt = prompt_template.replace("{{OUTLINE}}", outline_json)
            full_prompt = full_prompt.replace("{{NUM_QUESTIONS}}", str(num_questions))

            # Call LLM with retry logic
            max_retries = 2
            response = None

            for attempt in range(max_retries):
                try:
                    # Calculate max_tokens based on number of questions
                    # ~600 tokens per question (question + 4 options + detailed explanation)
                    # Add generous buffer for metadata and formatting
                    estimated_tokens = num_questions * 600 + 1000  # +1000 for metadata
                    max_output = min(estimated_tokens, 16384)  # Cap at 16k

                    response = self.llm.complete(
                        prompt=full_prompt,
                        model="complex",
                        temperature=0.4,  # Slightly higher for variety in questions
                        max_tokens=max_output,
                        json_mode=True  # Force pure JSON output
                    )
                    # Try to parse immediately to validate
                    json.loads(response)
                    break  # Success
                except json.JSONDecodeError as e:
                    if attempt < max_retries - 1:
                        logger.warning(f"Attempt {attempt + 1}/{max_retries} failed to parse quiz JSON, retrying...")
                        time.sleep(2)
                    else:
                        pass  # Will be handled below

            # Parse JSON response
            try:
                quiz_data = json.loads(response)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse quiz JSON: {e}")

                # Save raw response for debugging
                debug_file = self.logs_dir / f"debug_quiz_{lecture_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                debug_file.write_text(response, encoding='utf-8')
                logger.error(f"Saved raw quiz response to {debug_file}")

                # Try to extract JSON from markdown code blocks
                if "```json" in response:
                    json_text = response.split("```json")[1].split("```")[0].strip()
                    try:
                        quiz_data = json.loads(json_text)
                    except json.JSONDecodeError:
                        raise ContentGeneratorError(f"LLM response is not valid JSON even after extraction: {e}")
                elif "```" in response:
                    json_text = response.split("```")[1].split("```")[0].strip()
                    try:
                        quiz_data = json.loads(json_text)
                    except json.JSONDecodeError:
                        raise ContentGeneratorError(f"LLM response is not valid JSON even after extraction: {e}")
                else:
                    # Try to find JSON object in response
                    json_match = re.search(r'\{.*\}', response, re.DOTALL)
                    if json_match:
                        try:
                            quiz_data = json.loads(json_match.group(0))
                        except json.JSONDecodeError:
                            raise ContentGeneratorError(f"LLM quiz response is not valid JSON: {e}. Saved to {debug_file}")
                    else:
                        raise ContentGeneratorError(f"LLM quiz response is not valid JSON: {e}. Saved to {debug_file}")

            # Add metadata
            quiz_data["lecture_id"] = lecture_id
            quiz_data["generated_at"] = datetime.now().isoformat()
            quiz_data["pass"] = "quiz_generation"

            duration = time.time() - start_time

            if show_progress:
                actual_questions = len(quiz_data.get("questions", []))
                print(f"\n[PASS 2B SUCCESS] Generated quiz in {duration:.1f}s")
                print(f"  Questions generated: {actual_questions}")
                print(f"  Output size: {len(response)} chars")

            # Save quiz
            self._save_json(quiz_data, f"quiz_{lecture_id}")

            return quiz_data

        except Exception as e:
            error_msg = f"Pass 2b (quiz generation) failed: {str(e)}"
            logger.error(error_msg)
            raise ContentGeneratorError(error_msg)

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

            # Call LLM
            response = self.llm.complete(
                prompt=full_prompt,
                model="simple",  # Simple model sufficient for verification
                temperature=0.1,
                max_tokens=4096
            )

            # Parse JSON response
            try:
                report = json.loads(response)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse coverage report JSON: {e}")
                if "```json" in response:
                    json_text = response.split("```json")[1].split("```")[0].strip()
                    report = json.loads(json_text)
                elif "```" in response:
                    json_text = response.split("```")[1].split("```")[0].strip()
                    report = json.loads(json_text)
                else:
                    raise ContentGeneratorError(f"LLM response is not valid JSON: {e}")

            # Add metadata
            report["lecture_id"] = lecture_id
            report["generated_at"] = datetime.now().isoformat()
            report["pass"] = "coverage_verification"

            duration = time.time() - start_time

            if show_progress:
                coverage = report.get("coverage_percent", 0)
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
            lecture = self.db.get_lecture(lecture_id)

            if not lecture or not lecture.get('full_transcript'):
                raise ContentGeneratorError(f"No transcript found for lecture {lecture_id}")

            # Extract text from transcript segments
            transcript_data = lecture['full_transcript']
            if isinstance(transcript_data, str):
                transcript_data = json.loads(transcript_data)

            full_text = "\n".join([seg["text"] for seg in transcript_data if "text" in seg])

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
