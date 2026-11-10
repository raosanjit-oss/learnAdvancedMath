"""File checks and video rendering, kept out of the beginner-friendly AI file.

AST checks catch common mistakes; they are not a security sandbox. On this Mac,
the renderer also runs under sandbox-exec with restricted files and no network.
This is a local MVP, not a public multi-user execution service.
"""

import ast
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
from uuid import uuid4

project_directory = Path(__file__).resolve().parent
lessons_directory = project_directory / "generated_lessons"


def clean_manim_code(code):
    code = code.strip()
    lines = code.splitlines()
    if lines and lines[0].strip().lower() in ("```python", "```py", "```"):
        if lines[-1].strip() != "```":
            raise ValueError("The generated code is incomplete. Please generate again.")
        code = "\n".join(lines[1:-1]).strip()
    if not code:
        raise ValueError("The generated lesson is empty.")
    return code + "\n"


def validate_manim_code(code):
    """Check syntax, the Scene contract, and obvious unwanted operations."""
    try:
        tree = ast.parse(code)
    except SyntaxError as error:
        raise ValueError(f"Generated Python has a syntax error on line {error.lineno}.") from error

    allowed_modules = {"manim", "numpy", "math"}
    blocked_names = {
        "open", "exec", "eval", "compile", "__import__", "getattr", "setattr",
        "delattr", "globals", "locals", "vars", "dir", "input", "breakpoint",
        "help", "exit", "quit", "os", "sys", "subprocess", "socket", "requests",
        "pathlib", "shutil", "importlib", "builtins", "config", "tempconfig",
    }
    classes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
    if len(classes) != 1 or classes[0].name != "GeneratedLesson":
        raise ValueError("The code must define exactly one scene named GeneratedLesson.")
    scene = classes[0]
    if len(scene.bases) != 1 or not isinstance(scene.bases[0], ast.Name) or scene.bases[0].id != "Scene":
        raise ValueError("GeneratedLesson must inherit from Scene, not Slide.")
    if not any(isinstance(node, ast.FunctionDef) and node.name == "construct" for node in scene.body):
        raise ValueError("GeneratedLesson is missing construct(self).")
    if not any(isinstance(node, ast.ImportFrom) and node.module == "manim" for node in tree.body):
        raise ValueError("The lesson must import from manim.")
    for node in tree.body:
        if not isinstance(node, (ast.Import, ast.ImportFrom, ast.ClassDef)):
            if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
                raise ValueError("Place lesson operations inside GeneratedLesson.construct().")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(alias.name not in allowed_modules for alias in node.names):
            raise ValueError("Only Manim, math, and numpy imports are allowed.")
        if isinstance(node, ast.ImportFrom) and (node.level or node.module not in allowed_modules):
            raise ValueError("Only Manim, math, and numpy imports are allowed.")
        if isinstance(node, ast.Name) and (node.id in blocked_names or node.id.startswith("__")):
            raise ValueError(f"The lesson uses a disallowed name: {node.id}.")
        if isinstance(node, ast.Attribute) and (node.attr.startswith("_") or node.attr in {
            "next_slide", "save", "load", "loadtxt", "savetxt", "fromfile", "tofile",
            "system", "popen", "read", "write", "save_image", "save_json",
        }):
            raise ValueError(f"The lesson uses a disallowed operation: {node.attr}.")
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.decorator_list:
            raise ValueError("Generated lessons should not use decorators.")


def save_manim_code(code, topic):
    """Use a new folder so a failed/new lesson cannot replace an older video."""
    code = clean_manim_code(code)
    validate_manim_code(code)
    lesson_directory = lessons_directory / uuid4().hex
    lesson_directory.mkdir(parents=True)
    (lesson_directory / "lesson.py").write_text(code, encoding="utf-8")
    write_metadata(lesson_directory, {"topic": topic, "status": "saved"})
    return lesson_directory


def write_metadata(directory, metadata):
    (directory / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def render_environment(directory):
    """Find rendering tools even when VS Code did not activate Conda first."""
    bin_directory = Path(sys.prefix) / "bin"
    tex_directory = Path(sys.prefix) / "TinyTeX" / "bin" / "universal-darwin"
    tool_path = os.pathsep.join([str(tex_directory), str(bin_directory), "/usr/bin", "/bin", "/usr/sbin", "/sbin"])
    env = {name: os.environ[name] for name in ("HOME", "LANG", "LC_ALL") if name in os.environ}
    for name, folder in (("TMPDIR", "tmp"), ("XDG_CACHE_HOME", "cache"), ("XDG_CONFIG_HOME", "config")):
        path = directory / folder
        path.mkdir(exist_ok=True)
        env[name] = str(path)
    env.update(PATH=tool_path, PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1")
    for tool in ("ffmpeg", "ffprobe", "latex", "dvisvgm"):
        if not shutil.which(tool, path=tool_path):
            raise ValueError(f"Missing {tool}. Start the app with the manim_env interpreter.")
    return env


def sandbox_command(command, directory):
    if sys.platform == "linux":
        return linux_sandbox_command(command, directory)
    if sys.platform != "darwin" or not Path("/usr/bin/sandbox-exec").exists():
        raise ValueError("This local renderer currently requires macOS sandbox-exec.")
    # macOS needs its OS resources. Deny personal files, including the project's
    # .env, while allowing the Python environment and this lesson's own files.
    job_path = json.dumps(str(directory.resolve()))
    python_path = json.dumps(str(Path(sys.prefix).resolve()))
    private_read_rules = " ".join(
        f'(deny file-read-data (require-all (subpath "{root}") '
        f'(require-not (subpath {python_path})) (require-not (subpath {job_path}))))'
        for root in ("/Users", "/Volumes", "/private/var/folders", "/private/tmp")
    )
    profile = (
        '(version 1) (allow default) (deny network*) (deny file-write*) '
        f'(allow file-write* (subpath {job_path}) (literal "/dev/null")) '
        + private_read_rules
    )
    return ["/usr/bin/sandbox-exec", "-p", profile, *command]


def linux_sandbox_command(command, directory):
    """Fail closed if the host cannot provide isolated Linux namespaces.

    Only system dependencies and this job are mounted. App code, other jobs,
    host processes, network interfaces, and provider keys are not available.
    """
    if not shutil.which("bwrap") or not shutil.which("prlimit"):
        raise ValueError("The server needs Bubblewrap and prlimit for isolated rendering.")
    sandbox = ["bwrap", "--unshare-all", "--die-with-parent", "--new-session",
               "--cap-drop", "ALL", "--clearenv"]
    for path in ("/usr", "/bin", "/sbin", "/lib", "/lib64", "/etc/fonts", "/etc/texmf", "/var/lib/texmf", "/var/cache/fontconfig"):
        if Path(path).exists():
            sandbox.extend(["--ro-bind", path, path])
    sandbox.extend([
        "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
        "--bind", str(directory), str(directory), "--chdir", str(directory),
        "--setenv", "PATH", "/usr/local/bin:/usr/bin:/bin",
        "--setenv", "HOME", str(directory),
        "--setenv", "TMPDIR", "/tmp", "--setenv", "LANG", "C.UTF-8",
        "--setenv", "PYTHONDONTWRITEBYTECODE", "1",
        "--setenv", "OPENBLAS_NUM_THREADS", "1",
        "--setenv", "OMP_NUM_THREADS", "1",
        "--", *command,
    ])
    return ["prlimit", "--as=8589934592", "--cpu=3600", "--fsize=1073741824", "--nofile=256", "--nproc=128", "--", *sandbox]


def render_failure_message(log_text):
    """Turn common Manim/host failures into a useful, secret-free message."""
    lower_log = log_text.lower()
    if "bwrap" in lower_log and any(problem in lower_log for problem in (
        "operation not permitted", "permission denied", "creating new namespace failed",
    )):
        return "This host blocks the secure Bubblewrap sandbox required to render generated code."
    if "latex error" in lower_log or "latex failed" in lower_log or "latex compilation" in lower_log:
        return "Manim could not compile one of the generated math expressions with LaTeX. Generate again."
    if "no space left on device" in lower_log:
        return "The rendering server ran out of temporary storage. Try again after the app restarts."
    if "killed" in lower_log or "out of memory" in lower_log:
        return "The rendering server ran out of memory while making this video. Try a narrower topic."
    return "Manim could not finish this lesson. Open Render details below for the final log lines."


def render_video(lesson_directory):
    """Render once, directly at 1080p/60 fps. Return only a verified final MP4."""
    directory = Path(lesson_directory).resolve()
    metadata = json.loads((directory / "metadata.json").read_text())
    metadata["status"] = "rendering"
    write_metadata(directory, metadata)
    try:
        env = render_environment(directory)
        command = [
            sys.executable, "-m", "manim", "render", "-qh", "--renderer", "cairo",
            # Relative paths avoid LaTeX interpreting the '~' in iCloud's path.
            "--format", "mp4", "--media_dir", "media",
            "--progress_bar", "none", "--verbosity", "WARNING", "--silent",
            "-o", "lesson", "lesson.py", "GeneratedLesson",
        ]
        command = sandbox_command(command, directory)
        with (directory / "render.log").open("w", encoding="utf-8") as log:
            process = subprocess.Popen(command, cwd=directory, env=env, stdout=log, stderr=log, start_new_session=True)
            try:
                return_code = process.wait(timeout=3600)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                raise ValueError("Rendering exceeded one hour. Try a narrower topic.")
        if return_code != 0:
            log_text = (directory / "render.log").read_text(encoding="utf-8", errors="replace")
            # Streamlit's deployment log is visible only to the app owner. Avoid
            # printing the generated source; the final renderer lines are enough.
            print("Manim renderer failure:\n" + "\n".join(log_text.splitlines()[-40:]), file=sys.stderr, flush=True)
            raise ValueError(render_failure_message(log_text))
        videos = list((directory / "media" / "videos").rglob("lesson.mp4"))
        if len(videos) != 1:
            raise ValueError("Rendering finished without the expected video file.")
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=width,height,r_frame_rate,codec_name:format=duration", "-of", "json", str(videos[0])],
            env=env, capture_output=True, text=True, check=True, timeout=30,
        )
        video_info = json.loads(probe.stdout)
        stream = video_info["streams"][0]
        duration = float(video_info["format"]["duration"])
        numerator, denominator = stream["r_frame_rate"].split("/")
        if (stream["width"], stream["height"], float(numerator) / float(denominator), stream["codec_name"]) != (1920, 1080, 60, "h264"):
            raise ValueError("The video did not meet the 1080p/60 fps output settings.")
        if not 119.9 <= duration <= 600.1:
            raise ValueError(f"The generated lesson was {duration:.0f} seconds. Please regenerate for the required 2–10 minutes.")
        video_path = directory / "lesson.mp4"
        shutil.move(str(videos[0]), video_path)
        metadata.update(status="complete", duration=duration, video="lesson.mp4")
        write_metadata(directory, metadata)
        return video_path
    except Exception:
        metadata["status"] = "failed"
        write_metadata(directory, metadata)
        raise


def recent_lessons():
    """Local lesson history; no accounts or database needed for this MVP."""
    lessons = []
    for path in sorted(lessons_directory.glob("*/metadata.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            video = path.parent / "lesson.mp4"
            if record.get("status") == "complete" and video.is_file():
                lessons.append({"topic": record["topic"], "duration": record["duration"], "video_path": str(video)})
        except (OSError, KeyError, ValueError):
            continue
    return lessons[:12]
