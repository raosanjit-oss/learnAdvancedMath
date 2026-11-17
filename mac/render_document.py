"""Host-side entry point. Only the sandboxed Manim process executes lesson code."""

import json
from pathlib import Path
import sys

import lesson_tools


def render_document(document, library):
    with document.open("rb") as file:
        data = file.read(500_001)
    if len(data) > 500_000:
        raise ValueError("This lesson file is too large.")
    lesson = json.loads(data)
    if not isinstance(lesson, dict) or lesson.get("version") != 1:
        raise ValueError("Choose a .visualmath file downloaded from Visual Math.")
    topic, code = lesson.get("topic"), lesson.get("source")
    if not isinstance(topic, str) or not topic.strip() or len(topic) > 600 or not isinstance(code, str):
        raise ValueError("This lesson file is missing its question or animation.")
    lesson_tools.lessons_directory = library
    directory = lesson_tools.save_manim_code(code, topic)
    return lesson_tools.render_video(directory)


if __name__ == "__main__":
    try:
        print(render_document(Path(sys.argv[1]), Path(sys.argv[2])))
    except Exception as error:
        sys.exit(str(error))
