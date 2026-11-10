"""Run with: python -m streamlit run app.py"""

import json
import shutil
from pathlib import Path

import streamlit as st

from generate_lesson import (
    check_topic, clean_lesson_code, generate_manim_code,
    generate_topic_suggestions, save_lesson_code,
)
from lesson_tools import recent_lessons, render_video
import cloud_lessons
from public_limits import check_budget, generation_slot

project_directory = Path(__file__).resolve().parent
st.set_page_config(page_title="Visual Math · Understand it", page_icon="∿", layout="wide")
st.markdown(f"<style>{(project_directory / 'styles.css').read_text()}</style>", unsafe_allow_html=True)
public_mode = cloud_lessons.enabled()
if public_mode:
    cloud_lessons.require_login()

# These values survive Streamlit's reruns when a button or input changes.
defaults = {
    "stage": "input", "topic": "", "suggestions": [], "error": "",
    "video_path": "", "lesson_directory": "", "duration": 0,
}
for name, value in defaults.items():
    if name not in st.session_state:
        st.session_state[name] = value


def show_error(error):
    """Explain failures without sending provider tracebacks/keys to the page."""
    code = getattr(error, "status_code", None) or getattr(error, "code", None)
    if code == 429:
        message = "The AI provider's quota is temporarily exhausted. Wait a little and try again."
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
    st.session_state.update(topic=topic, video_path="", lesson_directory="", suggestions=[], error="", stage="input")
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


def create_video(retry_render=False):
    if not public_mode:
        return create_video_in_slot(retry_render)
    try:
        with generation_slot():
            create_video_in_slot(retry_render)
    except Exception as error:
        show_error(error)


def create_video_in_slot(retry_render=False):
    st.session_state.error = ""
    with st.status("Preparing your lesson…", expanded=True) as status:
        try:
            if retry_render:
                directory = Path(st.session_state.lesson_directory)
            else:
                status.update(label="Writing your visual explanation…")
                st.write("Choosing the examples, visuals, and pace for your topic.")
                if public_mode:
                    cloud_lessons.check_allowance()
                code = generate_manim_code(st.session_state.topic)
                status.update(label="Checking your lesson…")
                directory = save_lesson_code(clean_lesson_code(code), st.session_state.topic)
                if public_mode:
                    cloud_lessons.reserve_lesson(directory, st.session_state.topic)
                st.session_state.lesson_directory = str(directory)
            status.update(label="Animating your video in 1080p…")
            st.write("This can take several minutes. Keep this page open while the video is made.")
            # A storage retry reuses a successfully rendered file.
            saved_metadata = json.loads((directory / "metadata.json").read_text())
            video_path = directory / "lesson.mp4"
            if saved_metadata.get("status") != "complete" or not video_path.is_file():
                video_path = render_video(directory)
            metadata = json.loads((directory / "metadata.json").read_text())
            if public_mode:
                status.update(label="Saving your private lesson…")
                video_path = cloud_lessons.upload_video(directory, metadata["duration"])
            st.session_state.update(video_path=str(video_path), duration=metadata["duration"], stage="complete")
            if public_mode:
                shutil.rmtree(directory)
                st.session_state.lesson_directory = ""
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
with st.sidebar:
    st.markdown('<div class="brand">∿ <span>Visual Math</span></div>', unsafe_allow_html=True)
    st.caption("A little curiosity. A clearer picture.")
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
        if st.button(lesson["topic"], key=lesson["video_path"], use_container_width=True):
            st.session_state.update(
                stage="complete", topic=lesson["topic"], video_path=lesson["video_path"],
                duration=lesson["duration"], error="", lesson_directory=str(Path(lesson["video_path"]).parent),
            )
            st.rerun()
    st.divider()
    st.caption("PRE-ALGEBRA → CALCULUS\n\nPHYSICS, TOO")
    st.caption("Your lessons are private and saved online." if public_mode else "Lessons are saved on this Mac.")

st.markdown('<div class="topline"><span>A SPACE TO UNDERSTAND</span><span>MATH &amp; PHYSICS</span></div>', unsafe_allow_html=True)

if st.session_state.stage == "complete":
    st.markdown('<div class="eyebrow">YOUR VISUAL LESSON</div>', unsafe_allow_html=True)
    st.title(st.session_state.topic)
    total_seconds = round(st.session_state.duration)
    st.caption(f"{total_seconds // 60}:{total_seconds % 60:02d} MINUTES  ·  1080p / 60 FPS  ·  LEARN AT YOUR PACE")
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
        with right:
            st.caption("Pause to work through an example. Replay when something clicks.")
    else:
        st.error("This saved video has been moved or deleted. Create a new lesson to continue.")
    if st.button("Explore another question →"):
        st.session_state.update(defaults)
        st.session_state.pop("topic_input", None)
        st.rerun()
else:
    st.markdown('<div class="hero"><div class="eyebrow">CURIOSITY, MEET CLARITY</div><h1>See the idea.<br>Make it yours.</h1><p>Turn the thing you don’t quite get into a visual lesson.<br>One question. A clear explanation. Your pace.</p></div>', unsafe_allow_html=True)
    with st.form("topic_form", border=False):
        st.text_area("What would you like to understand?", key="topic_input", placeholder="e.g. Why is a derivative the slope of a curve?", max_chars=600, height=110)
        col1, col2 = st.columns([1, 2])
        with col1:
            submitted = st.form_submit_button("Find my lesson  →", type="primary", use_container_width=True)
        with col2:
            st.caption("2–10 minutes, chosen to fit the idea.\n\nClear visuals and on-screen explanations.")
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
            st.markdown('<div class="eyebrow">A GOOD PLACE TO START</div>', unsafe_allow_html=True)
            st.subheader(st.session_state.topic)
            st.caption("We'll build the intuition, work through an example, and bring the idea together.")
            if st.button("Create my video  →", type="primary", use_container_width=True):
                create_video()
                st.rerun()
    elif st.session_state.stage == "error":
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Generate again", use_container_width=True):
                create_video()
                st.rerun()
        with c2:
            if st.session_state.lesson_directory and st.button("Retry saved animation", use_container_width=True):
                create_video(retry_render=True)
                st.rerun()
        if st.session_state.lesson_directory and not public_mode:
            log = Path(st.session_state.lesson_directory) / "render.log"
            if log.is_file():
                with st.expander("Troubleshooting"):
                    st.caption("The render log can help debug the saved lesson.")
                    st.download_button("Download render log", log.read_bytes(), file_name="render.log", on_click="ignore")

    if st.session_state.stage == "input":
        st.markdown('<div class="section-label">A FEW PLACES TO BEGIN</div>', unsafe_allow_html=True)
        columns = st.columns(3)
        examples = [
            ("01 / ALGEBRA", "Why does the slope formula work?"),
            ("02 / CALCULUS", "How do derivatives describe change?"),
            ("03 / PHYSICS", "How do forces change an object's motion?"),
        ]
        for column, (label, question) in zip(columns, examples):
            with column:
                with st.container(border=True):
                    st.caption(label)
                    st.write(question)
                    if st.button("Explore →", key=label, use_container_width=True):
                        choose_topic(question)
                        st.rerun()

st.markdown('<div class="page-footer">Built for the moment it clicks.<span>VISUAL MATH · BETA</span></div>', unsafe_allow_html=True)
