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
import render_worker


class CloudTests(unittest.TestCase):
    def test_generation_has_a_distinct_fallback_model(self):
        import generate_lesson
        with patch.object(generate_lesson, "manim_coding_model", "preferred"), patch.object(
            generate_lesson, "manim_fallback_model", "fallback"
        ):
            self.assertEqual(generate_lesson.coding_model_choices(), ["preferred", "fallback"])

    def test_auth_redirect_uses_deployed_app_url(self):
        with patch.object(cloud_lessons, "setting", side_effect=lambda name, default=None: {
            "APP_URL": "https://example.streamlit.app/",
        }.get(name, default)):
            self.assertEqual(
                cloud_lessons.auth_options(),
                {"email_redirect_to": "https://example.streamlit.app"},
            )

    def test_auth_redirect_is_optional_for_local_development(self):
        with patch.object(cloud_lessons, "setting", return_value=""):
            self.assertEqual(cloud_lessons.auth_options(), {})

    def test_email_confirmation_code_request(self):
        self.assertEqual(
            cloud_lessons.confirmation_details(" student@example.com ", " 123456 "),
            {"email": "student@example.com", "token": "123456", "type": "email"},
        )

    def test_model_name_never_comes_from_api_key(self):
        import runpy
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "secret-test-value", "MANIM_CODING_MODEL": "test-model"}):
            values = runpy.run_path(str(Path(__file__).with_name("generate_lesson.py")), run_name="test")
        self.assertEqual(values["manim_coding_model"], "test-model")

    def test_settings_prefer_environment_and_support_cloud_secrets(self):
        import app_settings
        with patch.dict(os.environ, {"SETTING_TEST": "local"}):
            self.assertEqual(app_settings.get_setting("SETTING_TEST"), "local")
        with patch.dict(os.environ, {}, clear=True), patch("streamlit.secrets", {"SETTING_TEST": "cloud"}):
            self.assertEqual(app_settings.get_setting("SETTING_TEST"), "cloud")

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

    def test_bubblewrap_host_failure_has_a_clear_message(self):
        log = "bwrap: Creating new namespace failed: Operation not permitted"
        self.assertIn("blocks the secure Bubblewrap sandbox", lesson_tools.render_failure_message(log))

    def test_latex_failure_has_a_clear_message(self):
        self.assertIn("LaTeX", lesson_tools.render_failure_message("LaTeX compilation error"))

    def test_github_worker_container_has_no_network_or_secrets(self):
        command = render_worker.container_command(Path("/tmp/job"), "manim", "lesson.py")
        self.assertIn("none", command)
        self.assertIn("--read-only", command)
        self.assertIn("no-new-privileges", command)
        self.assertIn("ALL", command)
        self.assertNotIn("SUPABASE_SERVICE_ROLE_KEY", " ".join(command))

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

    def test_queue_stores_validated_source_then_dispatches(self):
        db = MagicMock()
        state = MagicMock(cloud_user_id="owner")
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "11111111111141118111111111111111"
            directory.mkdir()
            (directory / "lesson.py").write_text("from manim import *\n")
            with patch.object(cloud_lessons, "client", return_value=db), patch.object(
                cloud_lessons.st, "session_state", state
            ), patch.object(cloud_lessons, "check_allowance"), patch.object(
                cloud_lessons, "render_settings", return_value=("token", "owner/repository")
            ), patch.object(cloud_lessons, "dispatch_render") as dispatch:
                lesson_id = cloud_lessons.queue_lesson(directory, "Slope")
        inserted = db.table.return_value.insert.call_args.args[0]
        self.assertEqual(inserted["status"], "queued")
        self.assertEqual(inserted["source_code"], "from manim import *\n")
        dispatch.assert_called_once_with(lesson_id)

    def test_dispatch_failure_removes_unstarted_queue_record(self):
        db = MagicMock()
        state = MagicMock(cloud_user_id="owner")
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "11111111111141118111111111111111"
            directory.mkdir()
            (directory / "lesson.py").write_text("from manim import *\n")
            with patch.object(cloud_lessons, "client", return_value=db), patch.object(
                cloud_lessons.st, "session_state", state
            ), patch.object(cloud_lessons, "check_allowance"), patch.object(
                cloud_lessons, "render_settings", return_value=("token", "owner/repository")
            ), patch.object(cloud_lessons, "dispatch_render", side_effect=ValueError("GitHub unavailable")):
                with self.assertRaisesRegex(ValueError, "GitHub unavailable"):
                    cloud_lessons.queue_lesson(directory, "Slope")
        db.table.return_value.delete.assert_called_once()

    def test_daily_user_limit_checks_before_reserving(self):
        db = MagicMock()
        db.table.return_value.select.return_value.in_.return_value.gte.return_value.execute.return_value.data = [{"id": "1"}, {"id": "2"}]
        with patch.object(cloud_lessons, "client", return_value=db), self.assertRaises(ValueError):
            cloud_lessons.check_allowance()
        db.table.return_value.insert.assert_not_called()

    def test_cloud_generation_queues_then_plays_completed_video(self):
        import generate_lesson
        from test_mvp import VALID_CODE
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            stack.enter_context(patch.object(cloud_lessons, "enabled", return_value=True))
            stack.enter_context(patch.object(cloud_lessons, "require_login"))
            stack.enter_context(patch.object(cloud_lessons, "recent_lessons", return_value=[]))
            queue = stack.enter_context(patch.object(
                cloud_lessons, "queue_lesson", return_value="11111111-1111-4111-8111-111111111111"
            ))
            status = stack.enter_context(patch.object(cloud_lessons, "lesson_status", return_value={
                "id": "11111111-1111-4111-8111-111111111111", "topic": "What is slope?",
                "status": "queued", "duration": None, "video_path": None, "error_message": None,
            }))
            stack.enter_context(patch.object(cloud_lessons, "video_url", return_value="https://example.com/lesson.mp4"))
            stack.enter_context(patch.object(public_limits, "counts", {}))
            stack.enter_context(patch.object(lesson_tools, "lessons_directory", Path(tmp)))
            stack.enter_context(patch.object(generate_lesson, "check_topic", return_value="Accepted"))
            stack.enter_context(patch.object(generate_lesson, "generate_manim_code", return_value=VALID_CODE))
            render = stack.enter_context(patch.object(lesson_tools, "render_video"))
            app = AppTest.from_file(str(Path(__file__).with_name("app.py"))).run()
            app.text_area(key="topic_input").set_value("What is slope?")
            next(b for b in app.button if b.label == "Find my lesson  →").click().run()
            next(b for b in app.button if b.label == "Create my video  →").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state["stage"], "waiting")
            queue.assert_called_once()
            render.assert_not_called()
            self.assertEqual(list(Path(tmp).iterdir()), [])
            status.return_value = {
                "id": "11111111-1111-4111-8111-111111111111", "topic": "What is slope?",
                "status": "complete", "duration": 145.0,
                "video_path": "owner/lesson/lesson.mp4", "error_message": None,
            }
            next(b for b in app.button if b.label == "Check rendering progress  →").click().run()
            self.assertEqual(app.session_state["stage"], "complete")
            self.assertEqual(app.session_state["video_path"], "owner/lesson/lesson.mp4")
            self.assertEqual(len(app.get("video")), 1)


if __name__ == "__main__":
    unittest.main()
