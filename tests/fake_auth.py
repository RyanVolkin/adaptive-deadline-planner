from types import SimpleNamespace


class FakeAuthClient:
    def __init__(self):
        self.auth = self
        self._users = {}
        self._next_id = 1

    def sign_up(self, credentials):
        email = credentials["email"]
        if email in self._users:
            raise ValueError("email already registered")
        user = SimpleNamespace(id=str(self._next_id), email=email)
        self._next_id += 1
        self._users[email] = (user, credentials["password"])
        return SimpleNamespace(user=user)

    def sign_in_with_password(self, credentials):
        record = self._users.get(credentials["email"])
        if record is None or record[1] != credentials["password"]:
            raise ValueError("invalid credentials")
        return SimpleNamespace(user=record[0])