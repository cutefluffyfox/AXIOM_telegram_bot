from aiogram.types import Message

from models import User


def user_not_in_database(message: Message) -> bool:
    return User.get(message.from_user.id) is None


def is_group_chat(message: Message) -> bool:
    return message.chat.id != message.from_user.id


def state_is(message: Message, state: str) -> bool:
    return User.get(message.from_user.id).state == state


def state_is_register(message: Message) -> bool:
    """
    Returns True when User.state is like 'registerID' where ID is positive integer number
    """
    state = User.get(message.from_user.id).state
    return state[:8] == 'register' and state[8:].isdigit()


def is_question_page(message: Message) -> bool:
    return 'question' in User.get(message.from_user.id).state

