-- Private lesson records. Apply once to the selected Supabase project.
create table public.lessons (
    id uuid primary key,
    user_id uuid not null references auth.users(id) on delete cascade,
    topic text not null check (char_length(topic) between 1 and 600),
    status text not null default 'saved' check (status in ('saved', 'complete', 'failed')),
    duration double precision,
    video_path text,
    created_at timestamptz not null default now(),
    check (video_path is null or video_path = user_id::text || '/' || id::text || '/lesson.mp4')
);
create index lessons_user_created on public.lessons(user_id, created_at desc);
alter table public.lessons enable row level security;
revoke all on public.lessons from anon, authenticated;
grant select, insert on public.lessons to authenticated;
grant update(status, duration, video_path) on public.lessons to authenticated;
create policy own_lessons_read on public.lessons for select to authenticated
    using ((select auth.uid()) = user_id);
create policy own_lessons_insert on public.lessons for insert to authenticated
    with check ((select auth.uid()) = user_id);
create policy own_lessons_update on public.lessons for update to authenticated
    using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('lesson-videos', 'lesson-videos', false, 52428800, array['video/mp4']);
create policy own_lesson_videos_read on storage.objects for select to authenticated
    using (bucket_id = 'lesson-videos' and (storage.foldername(name))[1] = (select auth.uid())::text);
create policy own_lesson_videos_insert on storage.objects for insert to authenticated
    with check (bucket_id = 'lesson-videos'
        and (storage.foldername(name))[1] = (select auth.uid())::text
        and exists (select 1 from public.lessons l where l.user_id = (select auth.uid())
            and name = l.user_id::text || '/' || l.id::text || '/lesson.mp4'));
