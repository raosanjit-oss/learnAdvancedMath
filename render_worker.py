"""Ephemeral GitHub Actions worker for one queued Manim lesson.

The Supabase service key stays in this host process. Generated code runs in a
networkless, read-only Docker container that receives only its own job folder.
"""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import tempfile
from uuid import UUID

from lesson_tools import clean_manim_code, validate_manim_code


IMAGE = "manimcommunity/manim:v0.19.0"
MAX_VIDEO_BYTES = 50 * 1024 * 1024


class RenderError(Exception):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def required_setting(name):
    value = os.getenv(name)
    if not value:
        raise ValueError(f"The GitHub Actions secret {name} is missing.")
    return value


def container_command(job_directory, *command, writable=True):
    mount_mode = "rw" if writable else "ro"
    return [
        "docker", "run", "--rm", "--network", "none", "--read-only",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--pids-limit", "128", "--memory", "6g", "--cpus", "2",
        "--user", f"{os.getuid()}:{os.getgid()}",
        "--tmpfs", "/tmp:rw,nosuid,nodev,size=1g",
        "--env", "HOME=/tmp", "--env", "XDG_CACHE_HOME=/tmp/cache",
        "--env", "XDG_CONFIG_HOME=/tmp/config", "--env", "MPLCONFIGDIR=/tmp/matplotlib",
        "--volume", f"{job_directory}:/manim:{mount_mode}", "--workdir", "/manim",
        IMAGE, *command,
    ]


def run_container(job_directory, *command, timeout=3600, writable=True):
    result = subprocess.run(
        container_command(job_directory, *command, writable=writable),
        capture_output=True, text=True, timeout=timeout,
    )
    if result.returncode:
        tail = "\n".join((result.stdout + "\n" + result.stderr).splitlines()[-40:])
        raise RenderError(tail or f"Container exited with status {result.returncode}.")
    return result.stdout


def verify_video(job_directory, video):
    relative_video = "/manim/" + str(video.relative_to(job_directory))
    output = run_container(
        job_directory, "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate,codec_name:format=duration",
        "-of", "json", relative_video, timeout=60, writable=False,
    )
    information = json.loads(output)
    stream = information["streams"][0]
    duration = float(information["format"]["duration"])
    numerator, denominator = stream["r_frame_rate"].split("/")
    fps = float(numerator) / float(denominator)
    if (stream["width"], stream["height"], round(fps), stream["codec_name"]) != (1920, 1080, 60, "h264"):
        raise RenderError("The rendered file was not a 1080p60 H.264 video.")
    if not 119.9 <= duration <= 600.1:
        raise RenderError(f"The generated lesson was {duration:.0f} seconds instead of 2–10 minutes.")
    if video.stat().st_size > MAX_VIDEO_BYTES:
        raise RenderError("The completed video exceeded the beta's 50 MB storage limit.")
    return duration


def safe_error(error):
    message = str(error).strip()
    if "latex" in message.lower():
        heading = "Manim could not compile a generated math expression."
    elif isinstance(error, subprocess.TimeoutExpired):
        heading = "Rendering exceeded one hour. Try a narrower topic."
    else:
        heading = "The isolated Manim worker could not render this generated lesson."
    tail = "\n".join(message.splitlines()[-20:])
    return (heading + ("\n\n" + tail if tail else ""))[:2000]


def main():
    from supabase import create_client

    lesson_id = str(UUID(required_setting("LESSON_ID")))
    database = create_client(required_setting("SUPABASE_URL"), required_setting("SUPABASE_SERVICE_ROLE_KEY"))
    lesson = database.table("lessons").select(
        "id,user_id,status,source_code"
    ).eq("id", lesson_id).single().execute().data
    if lesson["status"] == "complete":
        print("Lesson is already complete.")
        return
    if lesson["status"] not in ("queued", "failed") or not lesson["source_code"]:
        raise ValueError("Lesson is not ready for rendering.")

    database.table("lessons").update({
        "status": "rendering", "error_message": None, "started_at": now(),
    }).eq("id", lesson_id).execute()

    try:
        code = clean_manim_code(lesson["source_code"])
        validate_manim_code(code)
        with tempfile.TemporaryDirectory(prefix="manim-job-") as temporary:
            job_directory = Path(temporary).resolve()
            (job_directory / "lesson.py").write_text(code, encoding="utf-8")
            run_container(
                job_directory, "manim", "render", "-qh", "--renderer", "cairo",
                "--format", "mp4", "--media_dir", "media", "--progress_bar", "none",
                "--verbosity", "WARNING", "--disable_caching", "-o", "lesson",
                "lesson.py", "GeneratedLesson",
            )
            videos = list((job_directory / "media" / "videos").rglob("lesson.mp4"))
            if len(videos) != 1:
                raise RenderError("Manim finished without exactly one lesson.mp4 file.")
            duration = verify_video(job_directory, videos[0])
            storage_path = f"{lesson['user_id']}/{lesson_id}/lesson.mp4"
            with videos[0].open("rb") as video_file:
                database.storage.from_("lesson-videos").upload(
                    storage_path, video_file,
                    file_options={"content-type": "video/mp4", "upsert": "true"},
                )
        database.table("lessons").update({
            "status": "complete", "duration": duration, "video_path": storage_path,
            "source_code": None, "error_message": None, "completed_at": now(),
        }).eq("id", lesson_id).execute()
        print("Lesson rendered and uploaded successfully.")
    except Exception as error:
        database.table("lessons").update({
            "status": "failed", "error_message": safe_error(error), "completed_at": now(),
        }).eq("id", lesson_id).execute()
        raise


if __name__ == "__main__":
    main()
