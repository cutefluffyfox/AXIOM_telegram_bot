import logging

import sqlalchemy

from database import SqlAlchemyBase
from database import create_session


class User(SqlAlchemyBase):
    __tablename__ = 'users'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    state = sqlalchemy.Column(sqlalchemy.TEXT, default='start', nullable=False)

    def get_id(self):
        return self.id

    def get_state(self):
        return self.state

    def set_state(self, state: str):
        logging.info(f'Change state for user {self} to {state}')
        session = create_session()
        user = session.query(User).filter(User.id == self.id).first()
        user.state = self.state = state
        session.commit()

    @staticmethod
    def add(user_id: int, state: str = None):
        logging.info(f'Add User(id={user_id}, state={state}) to database')
        session = create_session()
        session.add(User(id=user_id, state=state))
        session.commit()

    @staticmethod
    def get(user_id: int):
        session = create_session()
        return session.query(User).filter(User.id == user_id).first()

    def __repr__(self):
        return f"User(id={self.id}, state={self.state})"
