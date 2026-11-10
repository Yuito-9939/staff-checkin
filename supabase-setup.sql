-- ============================================================
-- 会場スタッフ入室ボード：Supabase 初期設定
-- Supabase ダッシュボード → SQL Editor に全文を貼り付けて「Run」してください。
-- ★ 一番下の「管理者のメールアドレス」を必ず書き換えてから実行してください。
-- ============================================================

-- 1) テーブル ------------------------------------------------
-- スタッフ名簿（ここに登録されたメールアドレスだけがデータを見られます）
create table if not exists public.members (
  email      text primary key check (email = lower(email)),
  is_admin   boolean not null default false,
  created_at timestamptz not null default now()
);

-- ログインした本人が入力する氏名
create table if not exists public.profiles (
  id         uuid primary key references auth.users(id) on delete cascade,
  email      text not null unique references public.members(email) on delete cascade,
  name       text not null check (char_length(name) between 1 and 40),
  updated_at timestamptz not null default now()
);

-- 各プログラムの担当（照明係）
create table if not exists public.assignments (
  program_id text not null,
  email      text not null references public.members(email) on delete cascade,
  primary key (program_id, email)
);

-- 入室記録（プログラムごと）
create table if not exists public.checkins (
  program_id text not null,
  user_id    uuid not null references public.profiles(id) on delete cascade,
  venue      smallint not null check (venue in (1, 2)),
  created_at timestamptz not null default now(),
  primary key (program_id, user_id)
);

-- 2) 権限判定用の関数 ----------------------------------------
create or replace function public.my_email() returns text
language sql stable as $$ select lower(auth.jwt() ->> 'email') $$;

create or replace function public.is_member() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from members where email = lower(auth.jwt() ->> 'email'))
$$;

create or replace function public.is_admin() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from members where email = lower(auth.jwt() ->> 'email') and is_admin)
$$;

-- 3) 行レベルセキュリティ（RLS） ------------------------------
alter table public.members     enable row level security;
alter table public.profiles    enable row level security;
alter table public.assignments enable row level security;
alter table public.checkins    enable row level security;

grant select, insert, update, delete
  on public.members, public.profiles, public.assignments, public.checkins to authenticated;
revoke all on public.members, public.profiles, public.assignments, public.checkins from anon;

-- 名簿：名簿に載っている人は閲覧可、管理者のみ変更可
create policy members_select on public.members for select to authenticated using (public.is_member());
create policy members_insert on public.members for insert to authenticated with check (public.is_admin());
create policy members_update on public.members for update to authenticated using (public.is_admin()) with check (public.is_admin());
create policy members_delete on public.members for delete to authenticated using (public.is_admin());

-- 氏名：名簿の人は閲覧可、自分の分だけ登録・変更可
create policy profiles_select on public.profiles for select to authenticated using (public.is_member());
create policy profiles_insert on public.profiles for insert to authenticated
  with check (id = auth.uid() and email = public.my_email() and public.is_member());
create policy profiles_update on public.profiles for update to authenticated
  using (id = auth.uid()) with check (id = auth.uid() and email = public.my_email());

-- 担当：名簿の人は閲覧可、管理者のみ変更可
create policy assignments_select on public.assignments for select to authenticated using (public.is_member());
create policy assignments_insert on public.assignments for insert to authenticated with check (public.is_admin());
create policy assignments_delete on public.assignments for delete to authenticated using (public.is_admin());

-- 入室：名簿の人は閲覧可、自分の入室・取消のみ可（管理者は他人の取消も可）
create policy checkins_select on public.checkins for select to authenticated using (public.is_member());
create policy checkins_insert on public.checkins for insert to authenticated
  with check (user_id = auth.uid() and public.is_member());
create policy checkins_delete on public.checkins for delete to authenticated
  using (user_id = auth.uid() or public.is_admin());

-- 4) リアルタイム配信 ----------------------------------------
alter publication supabase_realtime add table public.members, public.profiles, public.assignments, public.checkins;

-- 5) 会場コメント（プログラムごと。プログラムが終わると画面から消えます） ----
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

-- 6) 最初の管理者 --------------------------------------------
-- ★ 下のアドレスを、あなた（管理者）のメールアドレス（すべて小文字）に書き換えてください。
insert into public.members (email, is_admin)
values ('admin@example.com', true)
on conflict (email) do update set is_admin = true;
