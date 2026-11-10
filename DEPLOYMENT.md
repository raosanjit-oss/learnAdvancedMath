# Deployment status and setup

The local app works. Cloud deployment is not verified until the Linux image
builds, `verify_host.py` passes, and an actual signed-in generation/upload/playback
test succeeds on the host. Do not describe a successful build as a successful render.

## Accounts and storage

Supabase project: `zbitxwoucoqlswlradmt` (learnAdvancedMath).
`cloud_schema.sql` is the setup SQL applied to that project's initially empty
database. Do not reapply it to the existing project. It creates a private
`lesson-videos` bucket and an owner-protected `lessons` table. Each video has a
50 MiB maximum, and signed playback links expire after one hour.

Use Supabase Authentication's dashboard to invite/create the first test accounts.
The app has sign-in only, not public registration. Set `BETA_EMAILS` to the exact
comma-separated email addresses that may use the AI generation service. Never
set a service-role key in this app: it uses a publishable key and each user's
authenticated session. No student videos are bundled in the repository/image.

## Free host

Use a Hugging Face Docker Space with **CPU Basic**, without paid hardware or paid
persistent storage. Free account availability must be checked when creating it.
Set these in Space settings (provider keys as Secrets, never files in the repo):

```
GROQ_API_KEY=<your key>
GOOGLE_API_KEY=<your key>
MANIM_CODING_MODEL=<a model your account can access on its free tier>
SUPABASE_URL=https://zbitxwoucoqlswlradmt.supabase.co
SUPABASE_PUBLISHABLE_KEY=<publishable key from Supabase>
BETA_EMAILS=<invited testers' emails>
```

`PUBLIC_DEPLOYMENT=true` is set by the Dockerfile. On a Mac, omit it to keep the
existing local experience. To test cloud sign-in locally, set it in your shell
with the Supabase settings above; the Mac renderer is still used.

The Linux renderer uses Bubblewrap with separate process/network namespaces,
read-only system libraries, only one writable job folder, a scrubbed environment,
and process/time/memory/file limits. Some shared hosts block nested namespaces.
**If `verify_host.py` fails, do not remove isolation flags or run code directly.**
That host is not compatible with this renderer; use a separately isolated renderer.
No Docker build or Linux render has yet been verified on this Mac (Docker is absent).

One video job runs at a time; busy users are asked to retry. Initial beta limits:
five video attempts and 100 topic checks per server/day, two saved generation
attempts per account/day. Server-wide counters reset on process restart; these
are beta throttles, not a billing guarantee or durable distributed queue. Provider
accounts must remain on free billing configurations. Storage and bandwidth quotas
still apply. Invite only a handful of testers initially.

Completed videos upload to Supabase before local files are removed. An upload
retry reuses the rendered MP4. Failed jobs remain on the host for debugging and
are lost on restart; they are not exposed in another user's sidebar. A browser
reload can require signing in again; sessions are not persisted in cookies yet.

## Checks before sharing the link

1. Build the Docker image and pass its startup isolation check.
2. Verify an invited account signs in and an uninvited account is blocked.
3. Generate one lesson using confirmed free API tiers; verify 1080p/60 FPS,
   upload, playback, and that another account cannot access its record/video.
4. Restart the host and verify the saved lesson still appears from Supabase.
5. Keep CPU Basic selected. Do not upgrade hardware automatically.
