from app.availability import WEEKDAYS, MAX_MINUTES_PER_DAY


class AvailabilityService:
    
    def __init__(self, availability, schedules, transaction):
        self.availability = availability
        self.schedules = schedules
        self.transaction = transaction

    def validate(self, data):
        errors = {}
        for weekday in range(len(WEEKDAYS)):
            key = f"minutes_{weekday}"
            value = str(data.get(key, "")).strip()
            if not value.isdecimal() or len(value) > 4 or int(value) > MAX_MINUTES_PER_DAY:
                errors[key] = f"Enter 0 to {MAX_MINUTES_PER_DAY} minutes for {WEEKDAYS[weekday]}."
        return errors

    def save_week(self, user_id, data):
        errors = self.validate(data)
        if errors:
            raise ValueError(errors)
        minutes = []
        for weekday in range(len(WEEKDAYS)):
            minutes.append(int(data[f"minutes_{weekday}"].strip()))
        with self.transaction():
            self.availability.save_week(user_id, minutes)
            if self.schedules is not None:
                self.schedules.regenerate(user_id)
        return minutes

    def get_week(self, user_id):
        return self.availability.get_week(user_id)
