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

## Public beta

Streamlit hosts the UI and AI requests. It does not execute generated Python.
Public lessons are queued in Supabase, rendered by a standard GitHub-hosted
runner inside a networkless Docker container, uploaded to private Supabase
Storage, and then played in Streamlit.

Deploy `app.py` with Python 3.11 and add these values through Streamlit's
protected Secrets field:

```toml
PUBLIC_DEPLOYMENT = "true"
GROQ_API_KEY = "..."
GOOGLE_API_KEY = "..."
MANIM_CODING_MODEL = "gemini-3.8-flash"
MANIM_FALLBACK_MODEL = "gemini-3.5-flash"
SUPABASE_URL = "https://zbitxwoucoqlswlradmt.supabase.co"
SUPABASE_PUBLISHABLE_KEY = "..."
BETA_EMAILS = "invited@example.com"
GITHUB_REPOSITORY = "raosanjit-oss/learnAdvancedMath"
GITHUB_ACTIONS_TOKEN = "..."
```

Never commit those values. The GitHub token should be fine-grained, restricted
to this repository, and have only Actions read/write plus Metadata read access.
The repository also needs `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` as
GitHub Actions secrets. The service-role key must never be added to Streamlit.

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
5. In local mode, Manim renders on the Mac. In public mode, Streamlit queues the
   code and GitHub Actions renders it inside an isolated Docker container.
6. The worker verifies 1080p60 H.264 output, uploads the MP4 to private Supabase
   Storage, and marks the lesson complete.
7. The finished MP4 appears in the page's video player.

Each generated lesson has a separate folder so a new request does not overwrite
another lesson. Existing example files and previous renders are kept separately.

## Where to look in the code

- `app.py`: page design, input controls, progress messages, and the video player.
- `generate_lesson.py`: topic checks, suggestions, and Gemini requests.
- `lesson_tools.py`: generated-code checks, saving, and running Manim.
- `render_worker.py`: isolated GitHub Actions rendering and Supabase upload.
- `.github/workflows/render_lesson.yml`: one queued cloud render job.
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
private video storage, and a Linux deployment. See `DEPLOYMENT.md` for
configuration and the remaining host verification. Syntax checks alone do not
make generated Python safe to run on a public web server.

## Offline tests

```bash
source ~/miniforge3/bin/activate manim_env
python -m unittest -v test_mvp test_cloud
```

These tests cover the topic decisions, suggestions, code checks, separate lesson
folders, and Streamlit's clarification, generation, playback, and retry flows.
AI responses and the video render are simulated, so the tests consume no API
quota. The small MP4 fixture checks the UI wiring; an actual render is still
needed to verify Manim output and visual quality. The original `tests.py` remains
your separate experimental script.
