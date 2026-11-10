"""Offline MVP checks. Run: python -m unittest -v test_mvp

AI requests and rendering are mocked; no provider quota or paid APIs are used.
The UI tests use temporary lesson folders, never your saved lessons.
"""

import json
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import generate_lesson
import lesson_tools


PROJECT = Path(__file__).resolve().parent
VALID_CODE = """from manim import *

class GeneratedLesson(Scene):
    def construct(self):
        self.add(Text("A test lesson"))
        self.wait(120)
"""
SUGGESTIONS = [
    "Understanding derivatives as tangent slopes",
    "Calculating derivatives with the limit definition",
    "Using the power rule on polynomials",
]


class BackendTests(unittest.TestCase):
    def test_import_does_not_prompt_or_create_api_clients(self):
        with patch("builtins.input") as prompt, patch("groq.Groq") as groq, patch("google.genai.Client") as gemini:
            runpy.run_path(str(PROJECT / "generate_lesson.py"), run_name="import_check")
        prompt.assert_not_called()
        groq.assert_not_called()
        gemini.assert_not_called()

    def test_review_is_returned_without_terminal_recursion(self):
        with patch.object(generate_lesson, "ask_groq", return_value="Review") as ask, patch("builtins.input") as prompt:
            self.assertEqual(generate_lesson.check_topic("Calculus"), "Review")
        ask.assert_called_once_with("Calculus", "topic_viability.txt")
        prompt.assert_not_called()

    def test_empty_topic_does_not_request_ai(self):
        with patch.object(generate_lesson, "ask_groq") as ask:
            with self.assertRaises(ValueError):
                generate_lesson.check_topic("  ")
        ask.assert_not_called()

    def test_unexpected_decision_is_not_accepted(self):
        with patch.object(generate_lesson, "ask_groq", return_value="Maybe"):
            with self.assertRaises(ValueError):
                generate_lesson.check_topic("Slope")

    def test_suggestions_parse_three_numbered_nonempty_lines(self):
        response = "\n1. " + SUGGESTIONS[0] + "\n\n2) " + SUGGESTIONS[1] + "\n• " + SUGGESTIONS[2] + "\n"
        with patch.object(generate_lesson, "ask_groq", return_value=response) as ask:
            self.assertEqual(generate_lesson.generate_topic_suggestions("Derivatives"), SUGGESTIONS)
        ask.assert_called_once_with("Derivatives", "suggestions.txt")

    def test_wrong_suggestion_count_and_duplicates_fail(self):
        for response in ("One topic\nTwo topics", "One topic\none topic\nThird topic", "A\nB\nC\nD"):
            with self.subTest(response=response), patch.object(generate_lesson, "ask_groq", return_value=response):
                with self.assertRaises(ValueError):
                    generate_lesson.generate_topic_suggestions("Math")

    def test_code_fences_are_removed_and_unclosed_fences_rejected(self):
        self.assertEqual(lesson_tools.clean_manim_code("```python\n" + VALID_CODE + "```"), VALID_CODE)
        with self.assertRaises(ValueError):
            lesson_tools.clean_manim_code("```python\n" + VALID_CODE)

    def test_save_uses_unique_folders_and_preserves_first_lesson(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(lesson_tools, "lessons_directory", Path(temporary)):
            first = generate_lesson.save_lesson_code(VALID_CODE, "First topic")
            second = generate_lesson.save_lesson_code(VALID_CODE, "Second topic")
            self.assertNotEqual(first, second)
            self.assertEqual((first / "lesson.py").read_text(), VALID_CODE)
            self.assertEqual((second / "lesson.py").read_text(), VALID_CODE)
            self.assertEqual(json.loads((first / "metadata.json").read_text()), {"topic": "First topic", "status": "saved"})

    def test_invalid_or_disallowed_code_creates_no_lesson_folder(self):
        invalid_codes = [
            VALID_CODE.replace("self.wait(120)", "self.wait("),
            VALID_CODE.replace("(Scene)", "(Slide)"),
            "import os\n" + VALID_CODE,
            VALID_CODE.replace('self.add(Text("A test lesson"))', 'open("secret.txt")'),
            VALID_CODE.replace("self.wait(120)", 'eval("1 + 1")'),
            VALID_CODE.replace("self.wait(120)", 'self.__class__'),
            VALID_CODE.replace("self.wait(120)", "self.next_slide()"),
            VALID_CODE + '\nprint("top-level execution")\n',
        ]
        with tempfile.TemporaryDirectory() as temporary, patch.object(lesson_tools, "lessons_directory", Path(temporary)):
            for code in invalid_codes:
                with self.subTest(code=code), self.assertRaises(ValueError):
                    generate_lesson.save_lesson_code(code, "Bad lesson")
            self.assertEqual(list(Path(temporary).iterdir()), [])


class StreamlitFlowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.add_patch(lesson_tools, "lessons_directory", Path(self.temporary.name))
        self.add_patch(lesson_tools, "recent_lessons", return_value=[])
        self.check_topic = self.add_patch(generate_lesson, "check_topic")
        self.suggestions = self.add_patch(generate_lesson, "generate_topic_suggestions", return_value=SUGGESTIONS)
        self.generate = self.add_patch(generate_lesson, "generate_manim_code", return_value=VALID_CODE)
        self.render = self.add_patch(lesson_tools, "render_video", side_effect=self.fake_render)
        self.app = AppTest.from_file(str(PROJECT / "app.py"), default_timeout=20)
        self.app.run()
        self.assert_no_exceptions()

    def add_patch(self, module, name, *args, **kwargs):
        patcher = patch.object(module, name, *args, **kwargs)
        result = patcher.start()
        self.addCleanup(patcher.stop)
        return result

    @staticmethod
    def fake_render(directory):
        # Only a media fixture: the renderer is independently checked by a real render.
        video = directory / "lesson.mp4"
        video.write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom")
        metadata_path = directory / "metadata.json"
        metadata = json.loads(metadata_path.read_text())
        metadata.update(status="complete", duration=145.0, video="lesson.mp4")
        metadata_path.write_text(json.dumps(metadata))
        return video

    def assert_no_exceptions(self):
        self.assertEqual(len(self.app.exception), 0, [error.message for error in self.app.exception])

    def click(self, label):
        button = next(button for button in self.app.button if button.label == label)
        button.click().run()
        self.assert_no_exceptions()

    def submit_topic(self, topic):
        self.app.text_area(key="topic_input").set_value(topic)
        self.click("Find my lesson  →")

    def test_blank_input_never_calls_ai(self):
        self.submit_topic("   ")
        self.check_topic.assert_not_called()
        self.generate.assert_not_called()
        self.assertEqual(self.app.session_state["stage"], "input")
        self.assertIn("Enter a math", self.app.error[0].value)

    def test_rejected_topic_never_generates_or_renders(self):
        self.check_topic.return_value = "Rejected"
        self.submit_topic("Write a restaurant review")
        self.generate.assert_not_called()
        self.render.assert_not_called()
        self.assertIn("math or physics", self.app.error[0].value)

    def test_review_suggestion_is_rechecked_and_becomes_accepted_topic(self):
        self.check_topic.side_effect = ["Review", "Accepted"]
        self.submit_topic("Derivatives")
        self.assertEqual(self.app.session_state["stage"], "review")
        self.app.radio(key="topic_choice").set_value(SUGGESTIONS[1]).run()
        self.click("Use this topic  →")
        self.assertEqual([call.args[0] for call in self.check_topic.call_args_list], ["Derivatives", SUGGESTIONS[1]])
        self.assertEqual(self.app.session_state["topic"], SUGGESTIONS[1])
        self.assertEqual(self.app.session_state["stage"], "ready")
        self.generate.assert_not_called()

    def test_review_custom_topic_is_rechecked_and_used_for_generation(self):
        self.check_topic.side_effect = ["Review", "Accepted"]
        self.submit_topic("Physics")
        self.app.radio(key="topic_choice").set_value("I'll describe it myself").run()
        custom = "How does gravity change a falling ball's speed?"
        self.app.text_input(key="custom_topic").set_value(custom)
        self.click("Use this topic  →")
        self.check_topic.assert_called_with(custom)
        self.assertEqual(self.app.session_state["topic"], custom)
        self.click("Create my video  →")
        self.generate.assert_called_once_with(custom)
        self.assertEqual(self.app.session_state["stage"], "complete")

    def test_complete_video_survives_rerun_without_regeneration(self):
        self.check_topic.return_value = "Accepted"
        self.submit_topic("Why is slope rise over run?")
        self.click("Create my video  →")
        self.assertEqual(self.app.session_state["stage"], "complete")
        self.assertEqual(len(self.app.get("video")), 1)
        saved_video = Path(self.app.session_state["video_path"])
        self.assertTrue(saved_video.is_file())
        self.assertEqual(saved_video.parent, self.render.call_args.args[0])
        self.assertEqual(self.app.session_state["duration"], 145.0)
        self.app.run()
        self.assert_no_exceptions()
        self.generate.assert_called_once()
        self.render.assert_called_once()
        self.assertEqual(self.app.session_state["video_path"], str(saved_video))
        self.assertEqual(len(self.app.get("video")), 1)

    def test_failed_render_can_retry_saved_code_without_another_ai_request(self):
        self.check_topic.return_value = "Accepted"
        self.render.side_effect = ValueError("Manim could not finish this lesson.")
        self.submit_topic("Why is acceleration a change in velocity?")
        self.click("Create my video  →")
        self.assertEqual(self.app.session_state["stage"], "error")
        self.assertIn("Manim could not finish", self.app.error[0].value)
        directory = self.app.session_state["lesson_directory"]
        self.assertTrue((Path(directory) / "lesson.py").is_file())
        self.render.side_effect = self.fake_render
        self.click("Retry saved animation")
        self.assertEqual(self.app.session_state["stage"], "complete")
        self.generate.assert_called_once()
        self.assertEqual(self.render.call_count, 2)
        self.assertEqual(self.app.session_state["lesson_directory"], directory)


if __name__ == "__main__":
    unittest.main()
