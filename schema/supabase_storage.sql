-- Optional raw HTML archive for Milestone 2.
-- Run in Supabase SQL Editor once.
insert into storage.buckets (id, name, public)
values ('raw-market-data', 'raw-market-data', false)
on conflict (id) do nothing;
