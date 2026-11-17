class AvailabilityRepository:
    def __init__(self, connection):
        self.connection = connection

    def get_week(self, user_id):
        rows = self.connection.execute(
            "SELECT weekday, minutes FROM public.availability WHERE user_id = %s ORDER BY weekday",
            (user_id,),
        ).fetchall()
        week = [0] * 7
        for row in rows:
            week[row["weekday"]] = row["minutes"]
        return week

    def save_week(self, user_id, minutes_by_day):
        for weekday, minutes in enumerate(minutes_by_day):
            self.connection.execute(
                """INSERT INTO public.availability (user_id, weekday, minutes
                ) VALUES (%s, %s, %s
                ) ON CONFLICT (user_id, weekday) DO UPDATE SET minutes = EXCLUDED.minutes
                """,
                (user_id, weekday, minutes),
            )
