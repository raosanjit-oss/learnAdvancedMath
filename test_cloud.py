"""Offline cloud wiring and isolation checks. No paid API calls."""

from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from contextlib import ExitStack
import json

from streamlit.testing.v1 import AppTest
import cloud_lessons
import lesson_tools
import public_limits


class CloudTests(unittest.TestCase):
    def test_model_name_never_comes_from_api_key(self):
        import runpy
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "secret-test-value", "MANIM_CODING_MODEL": "test-model"}):
            values = runpy.run_path(str(Path(__file__).with_name("generate_lesson.py")), run_name="test")
        self.assertEqual(values["manim_coding_model"], "test-model")

    def test_public_mode_stops_without_supabase_configuration(self):
        with patch.dict(os.environ, {"PUBLIC_DEPLOYMENT": "true", "SUPABASE_URL": "", "SUPABASE_PUBLISHABLE_KEY": ""}):
            app = AppTest.from_file(str(Path(__file__).with_name("app.py"))).run()
        self.assertFalse(app.exception)
        self.assertIn("Configure Supabase", app.error[0].value)
        self.assertEqual(len(app.text_area), 0)

    def test_linux_sandbox_excludes_app_and_network(self):
        with patch("lesson_tools.shutil.which", return_value="/usr/bin/tool"):
            cmd = lesson_tools.linux_sandbox_command(["python", "lesson.py"], Path("/jobs/abc"))
        self.assertIn("--unshare-all", cmd)
        self.assertIn("--clearenv", cmd)
        self.assertNotIn("--share-net", cmd)
        self.assertNotIn("/app", cmd)
        self.assertEqual(cmd[cmd.index("--bind") + 1], "/jobs/abc")

    def test_linux_missing_sandbox_fails_closed(self):
        with patch("lesson_tools.shutil.which", return_value=None):
            with self.assertRaises(ValueError):
                lesson_tools.linux_sandbox_command(["python"], Path("/jobs/abc"))

    def test_one_render_at_a_time_and_lock_released_on_error(self):
        with patch.object(public_limits, "counts", {}):
            with self.assertRaises(RuntimeError):
                with public_limits.generation_slot():
                    with self.assertRaises(ValueError):
                        with public_limits.generation_slot():
                            self.fail("Concurrent generation allowed")
                    raise RuntimeError("render failed")
            with public_limits.generation_slot():
                pass

    def test_upload_retry_reuses_existing_object(self):
        db = MagicMock()
        bucket = db.storage.from_.return_value
        state = MagicMock(cloud_user_id="owner")
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "11111111111141118111111111111111"
            directory.mkdir()
            (directory / "lesson.mp4").write_bytes(b"test")
            with patch.object(cloud_lessons, "client", return_value=db), patch.object(cloud_lessons.st, "session_state", state):
                path = cloud_lessons.upload_video(directory, 150)
        bucket.upload.assert_not_called()
        self.assertTrue(path.startswith("owner/"))
        db.table.return_value.update.assert_called_once()

    def test_daily_user_limit_checks_before_reserving(self):
        db = MagicMock()
        db.table.return_value.select.return_value.gte.return_value.execute.return_value.data = [{"id": "1"}, {"id": "2"}]
        with patch.object(cloud_lessons, "client", return_value=db), self.assertRaises(ValueError):
            cloud_lessons.check_allowance()
        db.table.return_value.insert.assert_not_called()

    def test_cloud_generation_uploads_and_plays_remote_video(self):
        import generate_lesson
        from test_mvp import VALID_CODE, StreamlitFlowTests
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            stack.enter_context(patch.object(cloud_lessons, "enabled", return_value=True))
            stack.enter_context(patch.object(cloud_lessons, "require_login"))
            stack.enter_context(patch.object(cloud_lessons, "recent_lessons", return_value=[]))
            stack.enter_context(patch.object(cloud_lessons, "check_allowance"))
            reserve = stack.enter_context(patch.object(cloud_lessons, "reserve_lesson"))
            upload = stack.enter_context(patch.object(cloud_lessons, "upload_video", return_value="owner/lesson/lesson.mp4"))
            stack.enter_context(patch.object(cloud_lessons, "video_url", return_value="https://example.com/lesson.mp4"))
            stack.enter_context(patch.object(public_limits, "counts", {}))
            stack.enter_context(patch.object(lesson_tools, "lessons_directory", Path(tmp)))
            stack.enter_context(patch.object(generate_lesson, "check_topic", return_value="Accepted"))
            stack.enter_context(patch.object(generate_lesson, "generate_manim_code", return_value=VALID_CODE))
            stack.enter_context(patch.object(lesson_tools, "render_video", side_effect=StreamlitFlowTests.fake_render))
            app = AppTest.from_file(str(Path(__file__).with_name("app.py"))).run()
            app.text_area(key="topic_input").set_value("What is slope?")
            next(b for b in app.button if b.label == "Find my lesson  →").click().run()
            next(b for b in app.button if b.label == "Create my video  →").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state["stage"], "complete")
            self.assertEqual(app.session_state["video_path"], "owner/lesson/lesson.mp4")
            self.assertEqual(len(app.get("video")), 1)
            reserve.assert_called_once()
            upload.assert_called_once()
            self.assertEqual(list(Path(tmp).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
