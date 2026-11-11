# Public beta deployment

## Architecture

Streamlit handles sign-in, topic checks, code generation, and playback. Supabase
stores owner-protected job records and private videos. A standard GitHub-hosted
runner renders each queued lesson inside the pinned Manim Docker image.

Generated Python never runs in Streamlit. The rendering container has no network,
a read-only root filesystem, no Linux capabilities, no provider keys, and only
its own temporary job folder. The Supabase service-role key exists only in the
GitHub Actions host process and is never passed into the container.

## Streamlit secrets

Add these through the app's protected Advanced settings, never to GitHub files:

```toml
PUBLIC_DEPLOYMENT = "true"
APP_URL = "https://learnadvancedmath.streamlit.app"
GROQ_API_KEY = "..."
GOOGLE_API_KEY = "..."
MANIM_CODING_MODEL = "gemini-3.8-flash"
MANIM_FALLBACK_MODEL = "gemini-3.5-flash"
SUPABASE_URL = "https://zbitxwoucoqlswlradmt.supabase.co"
SUPABASE_PUBLISHABLE_KEY = "..."
BETA_EMAILS = "..."
GITHUB_REPOSITORY = "raosanjit-oss/learnAdvancedMath"
GITHUB_ACTIONS_TOKEN = "..."
```

Create `GITHUB_ACTIONS_TOKEN` as a fine-grained personal access token restricted
to only `raosanjit-oss/learnAdvancedMath`. Grant Metadata read and Actions
read/write. Do not grant repository contents write, administration, or account
permissions.

## GitHub Actions secrets

In GitHub, open **Settings → Secrets and variables → Actions** and add:

```text
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
```

Copy the URL and service-role key from the selected Supabase project. The
service-role key is a backend secret that bypasses RLS. Never put it in Streamlit,
the repository, a browser, an issue, or a chat message.

The repository must remain public for standard GitHub-hosted Actions runners to
remain free. Do not select a larger runner. GitHub can change its free-use terms,
so check billing settings before inviting more testers.

## Supabase

Project: `zbitxwoucoqlswlradmt` (`learnAdvancedMath`). The current schema has:

- owner-only lesson rows protected by RLS;
- queued, rendering, complete, and failed states;
- generated source stored only until a render completes;
- a private `lesson-videos` bucket;
- signed playback links that expire after one hour;
- a 50 MiB video limit for the initial beta.

Authenticated users can insert and read only their own queue records. They cannot
mark jobs complete or choose a video path. Only the GitHub worker's service role
can do that.

## Verification

1. Run `python -m unittest -v test_mvp test_cloud` locally.
2. Manually dispatch `Render queued Manim lesson` with a real queued lesson UUID.
3. Confirm the workflow uses the standard `ubuntu-latest` runner.
4. Confirm the container has no network and receives no secrets.
5. Confirm the lesson changes from `queued` to `rendering` to `complete`.
6. Confirm the MP4 is 1920 × 1080, 60 FPS, H.264, 2–10 minutes, and under 50 MiB.
7. Confirm its signed URL plays only for the lesson owner.

Do not describe the cloud renderer as complete until one real workflow has
rendered, uploaded, and played a lesson successfully.
