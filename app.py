"""Run with: python -m streamlit run app.py"""

import json
import shutil
from pathlib import Path

import streamlit as st

from generate_lesson import (
    check_topic, clean_lesson_code, generate_manim_code,
    generate_topic_suggestions, save_lesson_code,
)
from lesson_tools import recent_lessons, render_video, validate_manim_code
import cloud_lessons
from public_limits import check_budget, generation_slot

project_directory = Path(__file__).resolve().parent
logo_path = str(project_directory / "assets" / "visual-math-purple.jpg")
st.set_page_config(page_title="Visual Math", page_icon=logo_path, layout="wide")
st.logo(logo_path, size="large", icon_image=logo_path)
st.markdown(f"<style>{(project_directory / 'styles.css').read_text()}</style>", unsafe_allow_html=True)
public_mode = cloud_lessons.enabled()
if public_mode:
    cloud_lessons.require_login()

# These values survive Streamlit's reruns when a button or input changes.
defaults = {
    "stage": "input", "topic": "", "suggestions": [], "error": "",
    "video_path": "", "lesson_directory": "", "duration": 0, "job_id": "", "desktop_lesson": "",
}
for name, value in defaults.items():
    if name not in st.session_state:
        st.session_state[name] = value


def show_error(error):
    """Explain failures without sending provider tracebacks/keys to the page."""
    code = getattr(error, "status_code", None) or getattr(error, "code", None)
    try:
        code = int(code)
    except (TypeError, ValueError):
        pass
    if code == 429:
        message = "The AI provider's quota is temporarily exhausted. Wait a little and try again."
    elif code in (500, 502, 503, 504):
        message = "Gemini is temporarily busy. The app retried automatically; wait a minute and generate again."
    elif code in (401, 403):
        message = "The AI provider could not authorize this request. Check the API key and model access in .env."
    elif code == 404:
        message = "The configured AI model is unavailable. Update MANIM_CODING_MODEL in .env to a model your account can use."
    elif isinstance(error, ValueError):
        message = str(error)
    else:
        message = "This attempt could not finish. Please try again; if it persists, check your connection and local setup."
    st.session_state.error = message


def choose_topic(topic):
    topic = topic.strip()
    if not topic:
        st.session_state.error = "Enter a math or physics question to get started."
        return
    st.session_state.update(topic=topic, job_id="", desktop_lesson="", video_path="", lesson_directory="", suggestions=[], error="", stage="input")
    try:
        with st.spinner("Finding the right focus…"):
            if public_mode:
                check_budget("topic", 100)
            decision = check_topic(topic)
            if decision == "Accepted":
                st.session_state.stage = "ready"
            elif decision == "Review":
                st.session_state.stage = "review"
                st.session_state.suggestions = generate_topic_suggestions(topic)
            else:
                st.session_state.error = "Let's focus on math or physics. Try a concept, calculation, or specific question."
    except Exception as error:
        show_error(error)


def create_video(retry_render=False, desktop=False):
    st.session_state.last_desktop = desktop
    if not public_mode:
        return create_video_in_slot(retry_render, desktop)
    try:
        with generation_slot():
            create_video_in_slot(retry_render, desktop)
    except Exception as error:
        show_error(error)


def create_video_in_slot(retry_render=False, desktop=False):
    st.session_state.error = ""
    with st.status("Preparing your lesson…", expanded=True) as status:
        try:
            if retry_render:
                directory = Path(st.session_state.lesson_directory)
            else:
                status.update(label="Writing your visual explanation…")
                code = generate_manim_code(st.session_state.topic)
                status.update(label="Checking your lesson…")
                if desktop:
                    source = clean_lesson_code(code)
                    validate_manim_code(source)
                    document = {"version": 1, "topic": st.session_state.topic, "source": source}
                    st.session_state.update(stage="desktop", desktop_lesson=json.dumps(document), job_id="")
                    status.update(label="Your lesson file is ready", state="complete")
                    return
                directory = save_lesson_code(clean_lesson_code(code), st.session_state.topic)
                if public_mode:
                    status.update(label="Sending your lesson to the secure renderer…")
                    job_id = cloud_lessons.queue_lesson(directory, st.session_state.topic)
                    shutil.rmtree(directory)
                    st.session_state.update(
                        job_id=job_id, lesson_directory="", stage="waiting",
                    )
                    status.update(label="Your lesson is queued", state="complete", expanded=False)
                    return
                st.session_state.lesson_directory = str(directory)
            status.update(label="Animating your video in 1080p…")
            st.write("This can take several minutes. Keep this page open while the video is made.")
            # A storage retry reuses a successfully rendered file.
            saved_metadata = json.loads((directory / "metadata.json").read_text())
            video_path = directory / "lesson.mp4"
            if saved_metadata.get("status") != "complete" or not video_path.is_file():
                video_path = render_video(directory)
            metadata = json.loads((directory / "metadata.json").read_text())
            st.session_state.update(video_path=str(video_path), duration=metadata["duration"], stage="complete")
            status.update(label="Your lesson is ready", state="complete", expanded=False)
        except Exception as error:
            st.session_state.stage = "error"
            show_error(error)
            status.update(label="We couldn't finish this attempt", state="error", expanded=False)


if public_mode:
    try:
        lessons = cloud_lessons.recent_lessons()
    except Exception:
        st.error("Could not load your saved lessons. Please reload the page.")
        st.stop()
else:
    lessons = recent_lessons()


def refresh_cloud_job():
    if not public_mode or not st.session_state.job_id:
        return
    job = cloud_lessons.lesson_status(st.session_state.job_id)
    st.session_state.topic = job["topic"]
    if job["status"] == "complete":
        st.session_state.update(
            stage="complete", video_path=job["video_path"], duration=job["duration"], error="",
        )
    elif job["status"] == "failed":
        st.session_state.update(
            stage="error", error=job["error_message"] or "The rendering worker could not finish this lesson.",
        )
    else:
        st.session_state.stage = "waiting"


if public_mode and st.session_state.job_id:
    try:
        refresh_cloud_job()
    except Exception as error:
        show_error(error)
with st.sidebar:
    st.markdown('<div class="brand"><span>Visual Math</span></div>', unsafe_allow_html=True)
    if st.button("＋  New lesson", use_container_width=True):
        st.session_state.update(defaults)
        for key in ("topic_input", "topic_choice", "custom_topic"):
            st.session_state.pop(key, None)
        st.rerun()
    st.divider()
    st.markdown('<div class="eyebrow">YOUR LESSONS</div>', unsafe_allow_html=True)
    if not lessons:
        st.caption("Your finished lessons will appear here.")
    for lesson in lessons:
        lesson_status = lesson.get("status", "complete")
        label = lesson["topic"]
        if lesson_status in ("queued", "rendering"):
            label = "⏳  " + label
        elif lesson_status == "failed":
            label = "⚠  " + label
        if st.button(label, key=lesson.get("id") or lesson["video_path"], use_container_width=True):
            if lesson_status == "complete":
                stage = "complete"
                error = ""
            elif lesson_status == "failed":
                stage = "error"
                error = lesson.get("error_message") or "The rendering worker could not finish this lesson."
            else:
                stage = "waiting"
                error = ""
            st.session_state.update(
                stage=stage, topic=lesson["topic"], video_path=lesson.get("video_path") or "",
                duration=lesson.get("duration") or 0, error=error, lesson_directory="",
                job_id=lesson.get("id") or "",
            )
            st.rerun()
    st.divider()
    st.caption("Your lessons are private and saved online." if public_mode else "Lessons are saved on this Mac.")

if st.session_state.stage == "desktop":
    st.title(st.session_state.topic)
    st.write("Download the lesson file and open it in Visual Math on your Mac. The app will make the video and save it in your Movies folder.")
    st.download_button("Download lesson file", st.session_state.desktop_lesson, file_name="Lesson.visualmath", mime="application/octet-stream", on_click="ignore")
elif st.session_state.stage == "waiting":
    st.title(st.session_state.topic)
    st.subheader("Your video is being prepared")
    st.caption("You can close this page and find the video under Your lessons when it’s ready.")
    if st.button("Check rendering progress  →", type="primary"):
        st.rerun()
elif st.session_state.stage == "complete":
    st.title(st.session_state.topic)
    total_seconds = round(st.session_state.duration)
    st.caption(f"{total_seconds // 60}:{total_seconds % 60:02d} · 1080p · 60 fps")
    video_path = Path(st.session_state.video_path)
    if public_mode:
        try:
            url = cloud_lessons.video_url(st.session_state.video_path)
            st.video(url)
            st.link_button("Open / download video", url)
        except Exception:
            st.error("Could not load this video. Please reload the page to get a fresh link.")
    elif video_path.is_file():
        st.video(str(video_path))
        left, right = st.columns([1, 2])
        with left:
            with video_path.open("rb") as file:
                st.download_button("↓  Download video", file, file_name="visual-math-lesson.mp4", mime="video/mp4", use_container_width=True, on_click="ignore")
    else:
        st.error("This saved video has been moved or deleted. Create a new lesson to continue.")
    if st.button("Explore another question →"):
        st.session_state.update(defaults)
        st.session_state.pop("topic_input", None)
        st.rerun()
else:
    st.title("What are you working on?")
    st.write("Ask a question from math or physics and we’ll make a short video that walks through it with an example.")
    with st.form("topic_form", border=False):
        st.text_area("Your question", key="topic_input", placeholder="How can I find the slope of a curve at one point?", max_chars=600, height=110)
        col1, col2 = st.columns([1, 2])
        with col1:
            submitted = st.form_submit_button("Find my lesson  →", type="primary", use_container_width=True)
        with col2:
            st.caption("Lessons run between 2 and 10 minutes.")
    if submitted:
        choose_topic(st.session_state.topic_input)

    if st.session_state.stage == "review":
        st.divider()
        st.subheader("Let's make it a little more specific.")
        st.caption("Choose the part you want to understand, or describe it in your own words.")
        custom_option = "I'll describe it myself"
        options = st.session_state.suggestions + [custom_option]
        choice = st.radio("Choose your focus", options, key="topic_choice")
        with st.form("refinement_form", border=False):
            if choice == custom_option:
                custom_topic = st.text_input("What specifically is confusing?", key="custom_topic", max_chars=600)
            else:
                custom_topic = choice
            refine = st.form_submit_button("Use this topic  →", type="primary")
        if refine:
            choose_topic(custom_topic)
            st.rerun()

    if st.session_state.error:
        st.error(st.session_state.error)
    if st.session_state.stage == "ready":
        with st.container(border=True):
            st.subheader(st.session_state.topic)
            destination = st.radio("Where should we make the video?", ["On my Mac", "Here in the browser"], index=0 if st.query_params.get("render") == "mac" else 1, horizontal=True)
            if st.button("Create my video  →", type="primary", use_container_width=True):
                create_video(desktop=destination == "On my Mac")
                st.rerun()
    elif st.session_state.stage == "error":
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Generate again", use_container_width=True):
                create_video(desktop=st.session_state.get("last_desktop", False))
                st.rerun()
        with c2:
            if st.session_state.lesson_directory and st.button("Retry saved animation", use_container_width=True):
                create_video(retry_render=True)
                st.rerun()
        if st.session_state.lesson_directory:
            log = Path(st.session_state.lesson_directory) / "render.log"
            if log.is_file():
                with st.expander("Render details"):
                    st.caption("The final renderer lines identify dependency, sandbox, and generated-code problems.")
                    final_lines = "\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-40:])
                    st.code(final_lines or "The renderer did not produce a log.", language="text")
                    st.download_button("Download render log", log.read_bytes(), file_name="render.log", on_click="ignore")

    if st.session_state.stage == "input":
        st.subheader("Example questions")
        columns = st.columns(3)
        examples = [
            ("Algebra", "Why does the slope formula work?"),
            ("Calculus", "How do derivatives describe change?"),
            ("Physics", "How do forces change an object's motion?"),
        ]
        for column, (label, question) in zip(columns, examples):
            with column:
                with st.container(border=True):
                    st.caption(label)
                    st.write(question)
                    if st.button("Explore →", key=label, use_container_width=True):
                        choose_topic(question)
                        st.rerun()

