-- Private lesson records. Apply once to the selected Supabase project.
create table public.lessons (
    id uuid primary key,
    user_id uuid not null references auth.users(id) on delete cascade,
    topic text not null check (char_length(topic) between 1 and 600),
    status text not null default 'saved' check (status in ('saved', 'queued', 'rendering', 'complete', 'failed')),
    duration double precision,
    video_path text,
    source_code text check (source_code is null or char_length(source_code) between 1 and 300000),
    error_message text check (error_message is null or char_length(error_message) <= 2000),
    started_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz not null default now(),
    check (status not in ('queued', 'rendering') or source_code is not null),
    check (video_path is null or video_path = user_id::text || '/' || id::text || '/lesson.mp4')
);
create index lessons_user_created on public.lessons(user_id, created_at desc);
alter table public.lessons enable row level security;
revoke all on public.lessons from anon, authenticated;
grant select on public.lessons to authenticated;
grant insert(id, user_id, topic, status, source_code) on public.lessons to authenticated;
grant delete on public.lessons to authenticated;
create policy own_lessons_read on public.lessons for select to authenticated
    using ((select auth.uid()) = user_id);
create policy own_lessons_insert on public.lessons for insert to authenticated
    with check ((select auth.uid()) = user_id);
create policy own_unfinished_lessons_delete on public.lessons for delete to authenticated
    using ((select auth.uid()) = user_id and status in ('saved', 'queued', 'failed'));

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('lesson-videos', 'lesson-videos', false, 52428800, array['video/mp4']);
create policy own_lesson_videos_read on storage.objects for select to authenticated
    using (bucket_id = 'lesson-videos' and (storage.foldername(name))[1] = (select auth.uid())::text);
create policy own_lesson_videos_insert on storage.objects for insert to authenticated
    with check (bucket_id = 'lesson-videos'
        and (storage.foldername(name))[1] = (select auth.uid())::text
        and exists (select 1 from public.lessons l where l.user_id = (select auth.uid())
            and name = l.user_id::text || '/' || l.id::text || '/lesson.mp4'));
