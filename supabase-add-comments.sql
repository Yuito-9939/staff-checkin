-- すでに supabase-setup.sql を実行済みの場合だけ、このファイルを SQL Editor で実行してください。
-- （これから初めて設定する場合は supabase-setup.sql だけで足ります）

-- 会場コメント（プログラムごと。プログラムが終わると画面から消えます） ----
create table if not exists public.comments (
  id         uuid primary key default gen_random_uuid(),
  program_id text not null,
  user_id    uuid not null references public.profiles(id) on delete cascade,
  body       text not null check (char_length(body) between 1 and 200),
  created_at timestamptz not null default now()
);
create index if not exists comments_program_idx on public.comments (program_id, created_at);
alter table public.comments enable row level security;
grant select, insert, delete on public.comments to authenticated;
revoke all on public.comments from anon;
create policy comments_select on public.comments for select to authenticated using (public.is_member());
create policy comments_insert on public.comments for insert to authenticated
  with check (user_id = auth.uid() and public.is_member());
create policy comments_delete on public.comments for delete to authenticated
  using (user_id = auth.uid() or public.is_admin());
alter publication supabase_realtime add table public.comments;
