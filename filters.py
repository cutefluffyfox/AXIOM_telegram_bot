from aiogram.types import Message

from models import User


def user_not_in_database(message: Message):
    return User.get(message.from_user.id) is None


def is_group_chat(message: Message):
    return message.chat.id != message.from_user.id


def state_is(message: Message, state: str):
    return User.get(message.from_user.id).state == state


