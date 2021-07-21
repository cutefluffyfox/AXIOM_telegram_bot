import logging
from datetime import datetime
import contextlib

import sqlalchemy
from database import SqlAlchemyBase
from database import create_session


class User(SqlAlchemyBase):
    __tablename__ = 'users'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, nullable=False)
    state = sqlalchemy.Column(sqlalchemy.TEXT, default='start', nullable=False)
    cache = sqlalchemy.Column(sqlalchemy.TEXT, nullable=True)

    def set(self, state: str = None, cache: str = None):
        with contextlib.closing(create_session()) as session:
            logging.info(f'Change {self} to ["{state}", "{cache}"]')
            user = session.query(User).filter(User.id == self.id).first()

            if state is not None:
                self.state = user.state = state
            if cache is not None:
                self.cache = user.cache = cache

            session.commit()

    def is_registered(self) -> bool:
        with contextlib.closing(create_session()) as session:
            return session.query(UserInfo).filter(UserInfo.user_id == self.id).first().all_filled()

    @staticmethod
    def add(user_id: int, state: str = None):
        with contextlib.closing(create_session()) as session:
            logging.info(f'Add User(id={user_id}, state="{state}") to database')
            session.add(User(id=user_id, state=state))
            session.commit()

    @staticmethod
    def get(user_id: int):
        with contextlib.closing(create_session()) as session:
            return session.query(User).filter(User.id == user_id).first()

    def __repr__(self):
        return f'User(id={self.id}, state="{self.state}")'


class UserInfo(SqlAlchemyBase):
    __tablename__ = 'user_info'

    user_id = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("users.id"), primary_key=True, nullable=False)
    name = sqlalchemy.Column(sqlalchemy.TEXT, nullable=True)
    surname = sqlalchemy.Column(sqlalchemy.TEXT, nullable=True)
    patronymic = sqlalchemy.Column(sqlalchemy.TEXT, nullable=True)
    email = sqlalchemy.Column(sqlalchemy.TEXT, nullable=True)
    job = sqlalchemy.Column(sqlalchemy.TEXT, nullable=True)

    def set(self, name: str = None, surname: str = None, patronymic: str = None, email: str = None, job: str = None):
        with contextlib.closing(create_session()) as session:
            logging.info(f'Change {self} to ["{name}", "{surname}", "{patronymic}", "{email}", "{job}"]')
            user_info = session.query(UserInfo).filter(UserInfo.user_id == self.user_id).first()

            if name is not None:
                self.name = user_info.name = name
            if surname is not None:
                self.surname = user_info.surname = surname
            if patronymic is not None:
                self.patronymic = user_info.patronymic = patronymic
            if email is not None:
                self.email = user_info.email = email
            if job is not None:
                self.job = user_info.job = job

            session.commit()

    def all_filled(self) -> bool:
        with contextlib.closing(create_session()) as session:
            user_info = session.query(UserInfo).filter(UserInfo.user_id == self.user_id).first()
            return (
                    (user_info.name is not None) and
                    (user_info.surname is not None) and
                    (user_info.email is not None) and
                    (user_info.job is not None)
            )

    @staticmethod
    def add(user_id: int):
        with contextlib.closing(create_session()) as session:
            logging.info(f'Add UserInfo(id={user_id}) to database')
            session.add(UserInfo(user_id=user_id))
            session.commit()

    @staticmethod
    def get(user_id: int):
        with contextlib.closing(create_session()) as session:
            return session.query(UserInfo).filter(UserInfo.user_id == user_id).first()

    def __repr__(self):
        return f'UserInfo(user_id={self.user_id}, name="{self.name}", surname="{self.surname}", email="{self.email})"'


class Discussion(SqlAlchemyBase):
    __tablename__ = 'discussions'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, nullable=False, autoincrement=True)
    user_id = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("users.id"), nullable=False)
    theme = sqlalchemy.Column(sqlalchemy.TEXT, nullable=False)
    finished = sqlalchemy.Column(sqlalchemy.Boolean, default=False, nullable=False)

    def set(self, theme: str = None, finished: bool = None):
        with contextlib.closing(create_session()) as session:
            logging.info(f'Set discussion {self} to ["{theme}"", {finished}]')
            discussion = session.query(Discussion).filter(Discussion.id == self.id).first()

            if theme is not None:
                self.theme = discussion.theme = theme
            if finished is not None:
                self.finished = discussion.finished = finished

            session.commit()

    def update(self):
        with contextlib.closing(create_session()) as session:
            discussion = session.query(Discussion).filter(Discussion.id == self.id).first()

            self.theme = discussion.theme
            self.finished = discussion.finished

    def get_last_message(self):
        with contextlib.closing(create_session()) as session:
            return session.query(Dialog).filter(Dialog.discussion_id == self.id).all()[-1]

    def get_last_question(self):
        with contextlib.closing(create_session()) as session:
            return session.query(Dialog).filter(Dialog.discussion_id == self.id, Dialog.moderator == False).all()[-1]

    def get_questions(self):
        with contextlib.closing(create_session()) as session:
            return session.query(Dialog).filter(Dialog.discussion_id == self.id, Dialog.moderator == False).all()

    @staticmethod
    def add(user_id: int, theme: str):
        with contextlib.closing(create_session()) as session:
            logging.info(f'Add Discussion(user_id={user_id}, theme="{theme}") to database')
            session.add(Discussion(user_id=user_id, theme=theme))
            session.commit()

    @staticmethod
    def get(discussion_id: int):
        with contextlib.closing(create_session()) as session:
            return session.query(Discussion).filter(Discussion.id == discussion_id).first()

    @staticmethod
    def get_discussions(user_id: int):
        with contextlib.closing(create_session()) as session:
            return session.query(Discussion).filter(Discussion.user_id == user_id, Discussion.finished == False).all()

    def __repr__(self):
        return f'Discussion(user_id={self.user_id}, theme="{self.theme})"'


class Dialog(SqlAlchemyBase):
    __tablename__ = 'dialogs'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, nullable=False, autoincrement=True)
    discussion_id = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("discussions.id"))
    text = sqlalchemy.Column(sqlalchemy.TEXT, nullable=False)
    who = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)
    time = sqlalchemy.Column(sqlalchemy.TIMESTAMP, nullable=False)
    message_id = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)
    bot_message_id = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)
    moderator = sqlalchemy.Column(sqlalchemy.Boolean, default=False, nullable=False)

    @staticmethod
    def add(discussion_id: int, text: str, who: int, message_id: int, bot_message_id: int, moderator: bool = None):
        with contextlib.closing(create_session()) as session:
            logging.info(f'Add new Dialog(discussion_id={discussion_id}, who={who}, moderator={moderator}) to database')

            session.add(Dialog(
                discussion_id=discussion_id, text=text, who=who, time=datetime.now(),
                message_id=message_id, bot_message_id=bot_message_id, moderator=moderator)
            )

            session.commit()

    @staticmethod
    def get_question(bot_message_id: int):
        with contextlib.closing(create_session()) as session:
            return session.query(Dialog).filter(Dialog.bot_message_id == bot_message_id, Dialog.moderator == False).first()

    def __repr__(self):
        return f'Dialog(discussion_id={self.discussion_id}, who={self.who}, moderator={self.moderator})'


class Suggestion(SqlAlchemyBase):
    __tablename__ = 'suggestions'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, nullable=False, autoincrement=True)
    user_id = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("users.id"), nullable=False)
    theme = sqlalchemy.Column(sqlalchemy.TEXT, nullable=False)
    text = sqlalchemy.Column(sqlalchemy.TEXT, nullable=True)

    def set(self, theme: str = None, text: str = None):
        with contextlib.closing(create_session()) as session:
            logging.info(f'Set discussion {self} to ["{theme}", "{text[:20]}..."]')
            suggestion = session.query(Suggestion).filter(Suggestion.id == self.id).first()

            if theme is not None:
                self.theme = suggestion.theme = theme
            if text is not None:
                self.text = suggestion.text = text

            session.commit()

    @staticmethod
    def add(user_id: int, theme: str):
        with contextlib.closing(create_session()) as session:
            logging.info(f'Add Suggestion(user_id={user_id}, theme="{theme}") to database')
            session.add(Suggestion(user_id=user_id, theme=theme))
            session.commit()

    @staticmethod
    def get(suggestion_id: int):
        with contextlib.closing(create_session()) as session:
            return session.query(Suggestion).filter(Suggestion.id == suggestion_id).first()

    @staticmethod
    def get_suggestions(user_id: int):
        with contextlib.closing(create_session()) as session:
            return session.query(Suggestion).filter(Suggestion.user_id == user_id).all()

    def __repr__(self):
        return f'Suggestion(user_id={self.user_id}, theme="{self.theme})"'

