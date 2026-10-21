from flask import session


class AuthService:
    def __init__(self, auth_client):
        self.auth_client = auth_client

    def register(self, email, password):
        if len(password or "") < 8:
            return None, "Password must be at least 8 characters."
        try:
            response = self.auth_client.auth.sign_up({"email": email, "password": password})
            user = response.user
            if user is None:
                return None, "Unable to create account."
        except Exception:
            return None, "Unable to create account."
        
        session.clear()
        session["user_id"] = user.id

        return user, None

    def authenticate(self, email, password):
        try:
            response = self.auth_client.auth.sign_in_with_password(
                {"email": email, "password": password or ""}
            )
            session.clear()
            session["user_id"] = response.user.id

            return response.user
        except Exception:
            return None

    def logout(self):
        session.clear()