---
title: Visual Math
emoji: ∿
colorFrom: gray
colorTo: green
sdk: docker
app_port: 7860
---

# Visual Math MVP

A local Streamlit app that turns a math or physics question into a Manim video.
The generation prompt asks for a focused 2–10 minute explanation, choosing the
length to suit the topic. Videos render directly at 1920 × 1080 and 60 FPS; there
is no separate preview render and no Manim Slides dependency.

## Start the app

Open a terminal in `math-animation-mvp`, then run:

```bash
source ~/miniforge3/bin/activate manim_env
python -m streamlit run app.py --server.address 127.0.0.1
```

Open the local URL printed by Streamlit, normally `http://127.0.0.1:8501`.
Keep the terminal open while using the app. Press `Ctrl+C` to stop it.

Select this interpreter in VS Code:

```text
/Users/sanjitrao/miniforge3/envs/manim_env/bin/python
```

The existing `.venv` is retained, but the app now uses `manim_env` for both
generation and video rendering. Do not use the editor's Run Python button to
start a Streamlit app.

## API keys

Keep these variables in the project's `.env` file:

```dotenv
GROQ_API_KEY=your_groq_key
GOOGLE_API_KEY=your_google_key
```

The keys are used by the Python backend. Do not publish `.env` or put its contents
in the UI. Model access and quota depend on your provider accounts; an API key by
itself does not guarantee free usage.

## How a lesson is created

1. Enter a topic. Groq returns `Accepted`, `Review`, or `Rejected`.
2. If the topic needs clarification, select a suggestion or describe it yourself.
3. Gemini generates Python code using the instructions in `system_prompt.txt`.
4. The app checks and saves the code in its own folder under `generated_lessons/`.
5. Manim renders that lesson at 1080p/60 FPS. Rendering a long video can take
   several minutes on a laptop.
6. The finished MP4 appears in the page's video player.

Each generated lesson has a separate folder so a new request does not overwrite
another lesson. Existing example files and previous renders are kept separately.

## Where to look in the code

- `app.py`: page design, input controls, progress messages, and the video player.
- `generate_lesson.py`: topic checks, suggestions, and Gemini requests.
- `lesson_tools.py`: generated-code checks, saving, and running Manim.
- `system_prompt.txt`: teaching structure, animation rules, and duration guidance.
- `suggestions.txt`: instructions for generating narrower topics.
- `lesson.py`: a standalone example scene.

## Dependencies

Python packages are listed in `requirements.txt`. To restore them inside the
existing environment:

```bash
source ~/miniforge3/bin/activate manim_env
python -m pip install -r requirements.txt
python -m pip check
```

The environment also contains Cairo, Pango, FFmpeg, and Pycairo from Conda.
TinyTeX and `dvisvgm` are installed inside `manim_env/TinyTeX`; activating the
environment adds their executables to `PATH`. They are needed for mathematical
formulas and are not installed by `pip install -r requirements.txt`.

`manim-slides` was removed from the active environment. The known-working Manim
and PyAV versions remain pinned so the rendering setup is reproducible.

Local mode continues to run on your Mac. The cloud beta adds Supabase sign-in,
private video storage, and a Linux Docker deployment. See `DEPLOYMENT.md` for
configuration and the remaining host verification. Syntax checks alone do not
make generated Python safe to run on a public web server.

## Offline tests

```bash
source ~/miniforge3/bin/activate manim_env
python -m unittest -v test_mvp
```

These tests cover the topic decisions, suggestions, code checks, separate lesson
folders, and Streamlit's clarification, generation, playback, and retry flows.
AI responses and the video render are simulated, so the tests consume no API
quota. The small MP4 fixture checks the UI wiring; an actual render is still
needed to verify Manim output and visual quality. The original `tests.py` remains
your separate experimental script.
