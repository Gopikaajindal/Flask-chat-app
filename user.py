# secure_group_chat/user.py

from werkzeug.security import check_password_hash

class User:
    def __init__(self, username, email, password):
        self.username = username
        self.email = email
        self.password = password

    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        return self.username

    def check_password(self, password_input):
        return check_password_hash(self.password, password_input)
