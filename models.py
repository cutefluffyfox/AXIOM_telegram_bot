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
        """
        Change state/cache. If parameter is None, it won't be changed
        :param state: string that represents state from answers.json
        :param cache: string that store some temporary data
        """
        with contextlib.closing(create_session()) as session:
            logging.info(f'Change {self} to ["{state}", "{cache}"]')
            user = session.query(User).filter(User.id == self.id).first()

            if state is not None:
                self.state = user.state = state
            if cache is not None:
                self.cache = user.cache = cache

            session.commit()

    def is_registered(self) -> bool:
        """
        Check if user is already registered in the bot
        :return: True when user is registered (all data filled), False in any other case
        """
        with contextlib.closing(create_session()) as session:
            return session.query(UserInfo).filter(UserInfo.user_id == self.id).first().all_filled()

    @staticmethod
    def add(user_id: int, state: str = None):
        """
        Add user to database
        :param user_id: integer that represents user telegram id
        :param state: string (or None) that represents state from answers.json
        """
        with contextlib.closing(create_session()) as session:
            logging.info(f'Add User(id={user_id}, state="{state}") to database')
            session.add(User(id=user_id, state=state))
            session.commit()

    @staticmethod
    def get(user_id: int):
        """
        Gets User from database by user_id
        :param user_id: integer that represents user telegram id
        :return User(**kwargs) by user_id or None if id is invalid
        """
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
        """
        Change name/surname/patronymic/email/job. If parameter is None, it won't be changed
        :param name: string that represents user's name
        :param surname: string that represents user's surname
        :param patronymic: string (or None) that represents user's patronymic
        :param email: string that represents user's email
        :param job: string that represents user's jobs
        """
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

    def set_patronymic(self, patronymic: str = None):
        """
        Change user's patronymic strictly (None will not be skipped)
        :param patronymic: string (or None) that represents user's patronymic
        """
        with contextlib.closing(create_session()) as session:
            logging.info(f'Change users patronymic from {self} to "{patronymic}"')
            user_info = session.query(UserInfo).filter(UserInfo.user_id == self.user_id).first()

            self.patronymic = user_info.patronymic = patronymic

            session.commit()

    def all_filled(self) -> bool:
        """
        Checks if all essential columns are filled
        :return: True id all column are filled, False in any other case
        """
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
        """
        Add user_info to database
        :param user_id: integer that represents user telegram id
        """
        with contextlib.closing(create_session()) as session:
            logging.info(f'Add UserInfo(id={user_id}) to database')
            session.add(UserInfo(user_id=user_id))
            session.commit()

    @staticmethod
    def get(user_id: int):
        """
        Gets UserInfo from database by user_id
        :param user_id: integer that represents user telegram id
        :return UserInfo(**kwargs) by user_id or None if id is invalid
        """
        with contextlib.closing(create_session()) as session:
            return session.query(UserInfo).filter(UserInfo.user_id == user_id).first()

    def __repr__(self):
        return f'UserInfo(user_id={self.user_id}, name="{self.name}", surname="{self.surname}", email="{self.email})"'


class Discussion(SqlAlchemyBase):
    __tablename__ = 'discussions'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, nullable=False, autoincrement=True)
    server_id = sqlalchemy.Column(sqlalchemy.Integer, unique=True, nullable=True)
    user_id = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("users.id"), nullable=False)
    theme = sqlalchemy.Column(sqlalchemy.TEXT, nullable=False)
    finished = sqlalchemy.Column(sqlalchemy.Boolean, default=False, nullable=False)

    def set(self, theme: str = None, finished: bool = None, server_id: int = None):
        """
        Change theme/finished. If parameter is None, it won't be changed
        :param theme: string that represents discussion's theme
        :param finished: string that represents discussion's state
        """
        with contextlib.closing(create_session()) as session:
            logging.info(f'Set discussion {self} to ["{theme}"", {finished}, {server_id}]')
            discussion = session.query(Discussion).filter(Discussion.id == self.id).first()

            if theme is not None:
                self.theme = discussion.theme = theme
            if finished is not None:
                self.finished = discussion.finished = finished
            if server_id is not None:
                self.server_id = discussion.server_id = server_id

            session.commit()

    def update(self):
        """Updates self with newest data from database"""
        with contextlib.closing(create_session()) as session:
            discussion = session.query(Discussion).filter(Discussion.id == self.id).first()

            self.theme = discussion.theme
            self.finished = discussion.finished

    def get_last_message(self):
        """:return last Dialog(**kwargs) by self.id or None if zero dialogs are found"""
        with contextlib.closing(create_session()) as session:
            return session.query(Dialog).filter(Dialog.discussion_id == self.id).all()[-1]

    def get_last_question(self):
        """
        :return last Dialog(**kwargs) by self.id AND by dialog.moderator == False or None if zero dialogs are found
        """
        with contextlib.closing(create_session()) as session:
            return session.query(Dialog).filter(Dialog.discussion_id == self.id, Dialog.moderator == False).all()[-1]

    def get_questions(self):
        """:return [Dialog(**kwargs), Dialog(**kwargs), ...] by self.id AND by dialog.moderator == False or None if zero dialogs are found"""
        with contextlib.closing(create_session()) as session:
            return session.query(Dialog).filter(Dialog.discussion_id == self.id, Dialog.moderator == False).all()

    def delete(self):
        with contextlib.closing(create_session()) as session:
            session.query(Discussion).filter(Discussion.id == self.id).delete()

            session.commit()


    @staticmethod
    def add(user_id: int, theme: str):
        """
        Add Discussion to database
        :param user_id: integer that represents user telegram id
        :param theme: string that represents discussion's theme
        """
        with contextlib.closing(create_session()) as session:
            logging.info(f'Add Discussion(user_id={user_id}, theme="{theme}") to database')
            session.add(Discussion(user_id=user_id, theme=theme))
            session.commit()

    @staticmethod
    def get(discussion_id: int):
        """
        Gets Discussion from database by discussion_id
        :param discussion_id: integer that represents discussion_id
        :return Discussion(**kwargs) by discussion_id or None if id is invalid
        """
        with contextlib.closing(create_session()) as session:
            return session.query(Discussion).filter(Discussion.id == discussion_id).first()

    @staticmethod
    def get_discussions(user_id: int):
        """
        Gets all active (Discussion.finished == False) Discussion from database by user_id
        :param user_id: integer that represents user telegram id
        :return [Discussion(**kwargs), Discussion(**kwargs), ...] or [] if zero discussions are found
        """
        with contextlib.closing(create_session()) as session:
            return session.query(Discussion).filter(Discussion.user_id == user_id, Discussion.finished == False).all()

    def __repr__(self):
        return f'Discussion(user_id={self.user_id}, theme="{self.theme})"'


class Dialog(SqlAlchemyBase):
    __tablename__ = 'dialogs'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, nullable=False, autoincrement=True)
    discussion_id = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("discussions.id"))
    server_id = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("discussions.server_id"))
    text = sqlalchemy.Column(sqlalchemy.TEXT, nullable=False)
    who = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)
    time = sqlalchemy.Column(sqlalchemy.TIMESTAMP, nullable=False)
    message_id = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)
    bot_message_id = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)
    moderator = sqlalchemy.Column(sqlalchemy.Boolean, default=False, nullable=False)

    @staticmethod
    def add(discussion_id: int, text: str, who: int, message_id: int, bot_message_id: int, server_id: int, moderator: bool = None):
        """
        Add Dialog message to database
        :param discussion_id: integer that represents discussion_id
        :param text: string that represents user message
        :param who: integer that represents user telegram id
        :param message_id: integer that represents user message id
        :param bot_message_id: integer that represents bot message id
        :param moderator: bool that represents is this message was from moderator_chat
        """
        with contextlib.closing(create_session()) as session:
            logging.info(f'Add new Dialog(discussion_id={discussion_id}, who={who}, moderator={moderator}) to database')

            session.add(Dialog(
                discussion_id=discussion_id, text=text, who=who, time=datetime.now(),
                message_id=message_id, bot_message_id=bot_message_id, moderator=moderator,
                server_id=server_id)
            )

            session.commit()

    @staticmethod
    def get_question(bot_message_id: int):
        """
        Get Dialog first message by bot_message_id
        :param bot_message_id:
        :return: Dialog(**kwargs) or None if zero bot_message_id is invalid
        """
        with contextlib.closing(create_session()) as session:
            return session.query(Dialog).filter(Dialog.bot_message_id == bot_message_id, Dialog.moderator == False).first()

    @staticmethod
    def get(dialog_id: int):
        """
        Gets Dialog from database by dialog_id
        :param dialog_id: integer that represents dialog_id
        :return Dialog(**kwargs) by dialog_id or None if id is invalid
        """
        with contextlib.closing(create_session()) as session:
            return session.query(Dialog).filter(Dialog.id == dialog_id).first()

    def __repr__(self):
        return f'Dialog(discussion_id={self.discussion_id}, who={self.who}, moderator={self.moderator})'


class Suggestion(SqlAlchemyBase):
    __tablename__ = 'suggestions'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, nullable=False, autoincrement=True)
    user_id = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("users.id"), nullable=False)
    time = sqlalchemy.Column(sqlalchemy.TIMESTAMP, nullable=False)
    theme = sqlalchemy.Column(sqlalchemy.TEXT, nullable=False)
    text = sqlalchemy.Column(sqlalchemy.TEXT, nullable=True)

    def set(self, theme: str = None, text: str = None):
        """
        Change theme/text. If parameter is None, it won't be changed
        :param theme: string that represents suggestion's theme
        :param text: string that represents user message
        """
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
        """
        Add Suggestion to database
        :param user_id: integer that represents user telegram id
        :param theme: string that represents suggestion's theme
        """
        with contextlib.closing(create_session()) as session:
            logging.info(f'Add Suggestion(user_id={user_id}, theme="{theme}") to database')
            session.add(Suggestion(user_id=user_id, theme=theme, time=datetime.now()))
            session.commit()

    @staticmethod
    def get(suggestion_id: int):
        """
        Gets Suggestion from database by siggestion_id
        :param suggestion_id: integer that represents siggestion_id
        :return Suggestion(**kwargs) by siggestion_id or None if id is invalid
        """
        with contextlib.closing(create_session()) as session:
            return session.query(Suggestion).filter(Suggestion.id == suggestion_id).first()

    @staticmethod
    def get_suggestions(user_id: int):
        """
        Gets all Suggestion from database by user_id
        :param user_id: integer that represents user telegram id
        :return [Discussion(**kwargs), Discussion(**kwargs), ...] or [] if zero discussions are found
        """
        with contextlib.closing(create_session()) as session:
            return session.query(Suggestion).filter(Suggestion.user_id == user_id).all()

    def __repr__(self):
        return f'Suggestion(user_id={self.user_id}, theme="{self.theme})"'


class Team(SqlAlchemyBase):
    __tablename__ = 'teams'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, nullable=False, autoincrement=True)
    chat_id = sqlalchemy.Column(sqlalchemy.BigInteger, unique=True, nullable=False)
    owner_id = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("users.id"), nullable=False)
    competition_id = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)
    title = sqlalchemy.Column(sqlalchemy.TEXT, nullable=True)
    description = sqlalchemy.Column(sqlalchemy.TEXT, nullable=True)

    def set(self, title: str = None, description: str = None, chat_id: int = None):
        with contextlib.closing(create_session()) as session:
            logging.info(f'Set Team {self} to ["{title}", "{description}", {chat_id}]')
            team = session.query(Team).filter(Team.id == self.id).first()

            if chat_id is not None:
                self.chat_id = team.chat_id = chat_id
            if title is not None:
                self.title = team.title = title
            if description is not None:
                self.description = team.description = description

            session.commit()

    def user_in_team(self, user_id: int) -> bool:
        with contextlib.closing(create_session()) as session:
            return session.query(Member).filter(Member.chat_id == self.chat_id, Member.user_id == user_id).first()

    @staticmethod
    def add(chat_id: int, owner_id: int, competition_id: int):
        with contextlib.closing(create_session()) as session:
            logging.info(f'Add Team(chat_id={chat_id}, owner_id={owner_id}, competition_id={competition_id}) to database')
            session.add(Team(chat_id=chat_id, owner_id=owner_id, competition_id=competition_id))
            session.commit()

    @staticmethod
    def get(chat_id: int):
        with contextlib.closing(create_session()) as session:
            return session.query(Team).filter(Team.chat_id == chat_id).first()

    @staticmethod
    def get_members(chat_id: int):
        with contextlib.closing(create_session()) as session:
            return session.query(Member).filter(Member.chat_id == chat_id).all()

    @staticmethod
    def get_all_chats():
        with contextlib.closing(create_session()) as session:
            return session.query(Team.chat_id).all()

    @staticmethod
    def get_all_user_chats(user_id: int):
        with contextlib.closing(create_session()) as session:
            return session.query(Team).filter(Team.owner_id == user_id).all()

    @staticmethod
    def get_current_user_chats(user_id: int):
        with contextlib.closing(create_session()) as session:
            return session.query(Team).filter(Team.owner_id == user_id, Team.description == None).first()

    def __repr__(self):
        return f'Team(chat_id={self.chat_id}, owner_id={self.owner_id}, title="{self.title}")'


class Member(SqlAlchemyBase):
    __tablename__ = 'members'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, nullable=False, autoincrement=True)
    chat_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("teams.chat_id"), nullable=False)
    user_id = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("users.id"), nullable=False)

    @staticmethod
    def add(chat_id: int, user_id: int):
        with contextlib.closing(create_session()) as session:
            logging.info(f'Add Member(chat_id={chat_id}, user_id={user_id}) to database')
            session.add(Member(chat_id=chat_id, user_id=user_id))
            session.commit()

    def __repr__(self):
        return f'Member(chat_id={self.chat_id}, user_id={self.user_id})'


class Application(SqlAlchemyBase):
    __tablename__ = 'applications'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, nullable=False, autoincrement=True)
    user_id = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("users.id"), nullable=False)
    chat_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("teams.chat_id"), nullable=False)
    poll_id = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)
    accepted = sqlalchemy.Column(sqlalchemy.Boolean, nullable=True)

    def set(self, accepted: bool):
        with contextlib.closing(create_session()) as session:
            logging.info(f'Set Application {self} to [{accepted}]')
            application = session.query(Application).filter(Application.id == self.id).first()
            self.accepted = application.accepted = accepted
            session.commit()

    @staticmethod
    def add(chat_id: int, user_id: int, poll_id: int):
        with contextlib.closing(create_session()) as session:
            logging.info(f'Add Application(chat_id={chat_id}, user_id={user_id}, poll_id={poll_id}) to database')
            session.add(Application(chat_id=chat_id, user_id=user_id, poll_id=poll_id))
            session.commit()

    @staticmethod
    def get(user_id: int, chat_id: int):
        with contextlib.closing(create_session()) as session:
            return session.query(Application).filter(Application.user_id == user_id, Application.chat_id == chat_id).first()

    def __repr__(self):
        return f'Application(chat_id={self.chat_id}, user_id={self.user_id}, accepted={self.accepted})'
