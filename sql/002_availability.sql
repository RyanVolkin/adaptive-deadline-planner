BEGIN;

CREATE TABLE public.availability (	
	user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
	weekday smallint NOT NULL CHECK(weekday BETWEEN 0 AND 6),
	minutes integer NOT NULL CHECK(minutes BETWEEN 0 AND 1440),
	PRIMARY KEY (user_id, weekday)
);

ALTER TABLE public.availability ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public avaialability FROM PUBLIC, anon, authenticated;

COMMIT;
