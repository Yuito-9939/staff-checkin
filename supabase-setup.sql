-- ============================================================
-- 会場スタッフ入室ボード（staff_checkin）：Supabase 初期設定
-- Supabase ダッシュボード → SQL Editor に全文を貼り付けて「Run」してください。
--
-- 共有プロジェクトのルールに従い、このシステム専用のスキーマ staff_checkin に置きます
-- （public は使わない。他システムのテーブルには一切触れません）。
-- 実行後、Project Settings → Data API → Exposed schemas に staff_checkin を「追加」してください（既存の名前は消さない）。
--
-- 何度実行してもエラーにならない書き方です（drop policy if exists の行で「destructive」の警告が出ますが、
-- 消えるのはこのシステムの許可設定だけで、データは消えません）。
-- 最初の管理者の登録は、このファイルとは別に SQL Editor で実行します（README 手順2）。
-- ============================================================

create schema if not exists staff_checkin;
grant usage on schema staff_checkin to anon, authenticated, service_role;

-- 1) テーブル ------------------------------------------------
-- スタッフ名簿（ここに登録されたメールアドレスだけがデータを見られます）
create table if not exists staff_checkin.members (
  email      text primary key check (email = lower(email)),
  is_admin   boolean not null default false,
  created_at timestamptz not null default now()
);

-- ログインした本人が入力する氏名
create table if not exists staff_checkin.profiles (
  id         uuid primary key references auth.users(id) on delete cascade,
  email      text not null unique references staff_checkin.members(email) on delete cascade,
  name       text not null check (char_length(name) between 1 and 40),
  updated_at timestamptz not null default now()
);

-- 各プログラムの担当（照明係）
create table if not exists staff_checkin.assignments (
  program_id text not null check (program_id ~ '^d[1-3]v[12]-[0-9]{4}$'),
  email      text not null references staff_checkin.members(email) on delete cascade,
  primary key (program_id, email)
);

-- 入室記録（プログラムごと）
create table if not exists staff_checkin.checkins (
  program_id text not null check (program_id ~ '^d[1-3]v[12]-[0-9]{4}$'),
  user_id    uuid not null references staff_checkin.profiles(id) on delete cascade,
  venue      smallint not null check (venue in (1, 2)),
  created_at timestamptz not null default now(),
  primary key (program_id, user_id)
);

-- 会場コメント（プログラムごと。プログラムが終わると画面から消えます）
create table if not exists staff_checkin.comments (
  id         uuid primary key default gen_random_uuid(),
  program_id text not null check (program_id ~ '^d[1-3]v[12]-[0-9]{4}$'),
  user_id    uuid not null references staff_checkin.profiles(id) on delete cascade,
  body       text not null check (char_length(body) between 1 and 200),
  created_at timestamptz not null default now()
);
create index if not exists comments_program_idx on staff_checkin.comments (program_id, created_at);

-- 設定（今は「テストモード」だけ。value の例: {"on":true,"sim":<表示する時刻ms>,"real":<開始した実時刻ms>}）
create table if not exists staff_checkin.settings (
  key        text primary key check (key in ('test')),
  value      jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);
insert into staff_checkin.settings (key, value) values ('test', '{"on":false}') on conflict (key) do nothing;

-- 2) 権限判定用の関数 ----------------------------------------
create or replace function staff_checkin.my_email() returns text
language sql stable as $$ select lower(auth.jwt() ->> 'email') $$;

create or replace function staff_checkin.is_member() returns boolean
language sql stable security definer set search_path = staff_checkin as $$
  select exists (select 1 from staff_checkin.members where email = lower(auth.jwt() ->> 'email'))
$$;

create or replace function staff_checkin.is_admin() returns boolean
language sql stable security definer set search_path = staff_checkin as $$
  select exists (select 1 from staff_checkin.members where email = lower(auth.jwt() ->> 'email') and is_admin)
$$;

-- ログインメールを送る前に「名簿に載っているか」だけを確かめる（名簿外の人にメールを送らない・共有の送信枠を守るため）
create or replace function staff_checkin.can_login(p_email text) returns boolean
language sql stable security definer set search_path = staff_checkin as $$
  select exists (select 1 from staff_checkin.members where email = lower(trim(p_email)))
$$;

-- テスト期間のデータ（入室記録・コメント）を全消去してテストモードを止める。管理者のみ・学会当日より前のみ
create or replace function staff_checkin.clear_test_data() returns void
language plpgsql security definer set search_path = staff_checkin as $$
begin
  if not staff_checkin.is_admin() then raise exception 'not authorized'; end if;
  if now() >= timestamptz '2026-11-20 00:00:00+09' then
    raise exception '学会当日以降はテストデータを消去できません';
  end if;
  delete from staff_checkin.checkins where true;
  delete from staff_checkin.comments where true;
  update staff_checkin.settings set value = '{"on":false}', updated_at = now() where key = 'test';
end $$;

revoke all on function staff_checkin.can_login(text), staff_checkin.clear_test_data() from public;
grant execute on function staff_checkin.can_login(text) to anon, authenticated;
grant execute on function staff_checkin.clear_test_data() to authenticated;
grant execute on function staff_checkin.my_email(), staff_checkin.is_member(), staff_checkin.is_admin() to authenticated;

-- 3) 行レベルセキュリティ（RLS） ------------------------------
alter table staff_checkin.members     enable row level security;
alter table staff_checkin.profiles    enable row level security;
alter table staff_checkin.assignments enable row level security;
alter table staff_checkin.checkins    enable row level security;
alter table staff_checkin.comments    enable row level security;
alter table staff_checkin.settings    enable row level security;

grant select, insert, update, delete on all tables in schema staff_checkin to authenticated;
grant all on all tables in schema staff_checkin to service_role;
revoke all on all tables in schema staff_checkin from anon;

drop policy if exists members_select on staff_checkin.members;
drop policy if exists members_insert on staff_checkin.members;
drop policy if exists members_update on staff_checkin.members;
drop policy if exists members_delete on staff_checkin.members;
drop policy if exists profiles_select on staff_checkin.profiles;
drop policy if exists profiles_insert on staff_checkin.profiles;
drop policy if exists profiles_update on staff_checkin.profiles;
drop policy if exists assignments_select on staff_checkin.assignments;
drop policy if exists assignments_insert on staff_checkin.assignments;
drop policy if exists assignments_delete on staff_checkin.assignments;
drop policy if exists checkins_select on staff_checkin.checkins;
drop policy if exists checkins_insert on staff_checkin.checkins;
drop policy if exists checkins_delete on staff_checkin.checkins;
drop policy if exists comments_select on staff_checkin.comments;
drop policy if exists comments_insert on staff_checkin.comments;
drop policy if exists comments_delete on staff_checkin.comments;
drop policy if exists settings_select on staff_checkin.settings;
drop policy if exists settings_insert on staff_checkin.settings;
drop policy if exists settings_update on staff_checkin.settings;

-- 名簿：名簿に載っている人は閲覧可、管理者のみ変更可
create policy members_select on staff_checkin.members for select to authenticated using (staff_checkin.is_member());
create policy members_insert on staff_checkin.members for insert to authenticated with check (staff_checkin.is_admin());
create policy members_update on staff_checkin.members for update to authenticated using (staff_checkin.is_admin()) with check (staff_checkin.is_admin());
create policy members_delete on staff_checkin.members for delete to authenticated using (staff_checkin.is_admin());

-- 氏名：名簿の人は閲覧可、自分の分だけ登録・変更可
create policy profiles_select on staff_checkin.profiles for select to authenticated using (staff_checkin.is_member());
create policy profiles_insert on staff_checkin.profiles for insert to authenticated
  with check (id = auth.uid() and email = staff_checkin.my_email() and staff_checkin.is_member());
create policy profiles_update on staff_checkin.profiles for update to authenticated
  using (id = auth.uid()) with check (id = auth.uid() and email = staff_checkin.my_email());

-- 担当：名簿の人は閲覧可、管理者のみ変更可
create policy assignments_select on staff_checkin.assignments for select to authenticated using (staff_checkin.is_member());
create policy assignments_insert on staff_checkin.assignments for insert to authenticated with check (staff_checkin.is_admin());
create policy assignments_delete on staff_checkin.assignments for delete to authenticated using (staff_checkin.is_admin());

-- 入室：名簿の人は閲覧可、自分の入室・取消のみ可（管理者は他人の取消も可）
create policy checkins_select on staff_checkin.checkins for select to authenticated using (staff_checkin.is_member());
create policy checkins_insert on staff_checkin.checkins for insert to authenticated
  with check (user_id = auth.uid() and staff_checkin.is_member());
create policy checkins_delete on staff_checkin.checkins for delete to authenticated
  using (user_id = auth.uid() or staff_checkin.is_admin());

-- コメント：名簿の人は閲覧・投稿可、削除は本人か管理者
create policy comments_select on staff_checkin.comments for select to authenticated using (staff_checkin.is_member());
create policy comments_insert on staff_checkin.comments for insert to authenticated
  with check (user_id = auth.uid() and staff_checkin.is_member());
create policy comments_delete on staff_checkin.comments for delete to authenticated
  using (user_id = auth.uid() or staff_checkin.is_admin());

-- 設定：名簿の人は閲覧可、管理者のみ変更可（テストモードは学会当日より前だけ変更可）
create policy settings_select on staff_checkin.settings for select to authenticated using (staff_checkin.is_member());
create policy settings_insert on staff_checkin.settings for insert to authenticated
  with check (staff_checkin.is_admin() and now() < timestamptz '2026-11-20 00:00:00+09');
create policy settings_update on staff_checkin.settings for update to authenticated
  using (staff_checkin.is_admin())
  with check (staff_checkin.is_admin() and now() < timestamptz '2026-11-20 00:00:00+09');

-- 4) リアルタイム配信（まだ登録されていないテーブルだけ追加） ------
do $$
declare t text;
begin
  foreach t in array array['members','profiles','assignments','checkins','comments','settings'] loop
    if not exists (select 1 from pg_publication_tables
                   where pubname = 'supabase_realtime' and schemaname = 'staff_checkin' and tablename = t) then
      execute format('alter publication supabase_realtime add table staff_checkin.%I', t);
    end if;
  end loop;
end $$;

-- 5) 共有プロジェクトの管理台帳に登録（台帳がある場合のみ。Storage は使わないが列が必須のため同名で予約）
do $$
begin
  if to_regclass('public.systems') is not null then
    insert into public.systems (schema_name, bucket_name, display_name, repo_url, status)
    values ('staff_checkin', 'staff_checkin', '会場スタッフ入室ボード', 'https://github.com/Yuito-9939/staff-checkin', 'active')
    on conflict (schema_name) do nothing;
  end if;
end $$;

select (select count(*) from staff_checkin.members) as "名簿の人数",
       (select count(*) from staff_checkin.members where is_admin) as "管理者の人数";
