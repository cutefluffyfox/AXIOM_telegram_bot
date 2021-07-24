from aiogram.types import Message

from models import User


def user_not_in_database(message: Message) -> bool:
    """Returns True when User is not in database"""
    return User.get(message.from_user.id) is None


def is_group_chat(message: Message) -> bool:
    """Returns True when message.chat.id != message.from_user.id"""
    return message.chat.id != message.from_user.id


def state_is(message: Message, state: str) -> bool:
    """Returns True when User.state == state"""
    return User.get(message.from_user.id).state == state


def is_register_menu(message: Message) -> bool:
    """Returns True when User.state is like 'registerID' where ID is positive integer number"""
    state = User.get(message.from_user.id).state
    return state[:8] == 'register' and state[8:].isdigit()


def is_question_menu(message: Message) -> bool:
    """Returns True when 'question' in User.state"""
    return 'question' in User.get(message.from_user.id).state


def is_suggestion_menu(message: Message) -> bool:
    """Returns True when 'suggest' in User.state"""
    return 'suggest' in User.get(message.from_user.id).state


def is_upload_menu(message: Message) -> bool:
    """Returns True when 'upload' in User.state"""
    return 'upload' in User.get(message.from_user.id).state


def is_faq_menu(message: Message) -> bool:
    """Returns True when 'faq' in User.state"""
    return 'faq' in User.get(message.from_user.id).state


def is_login_menu(message: Message) -> bool:
    """Returns True when 'login' in User.state"""
    return 'login' in User.get(message.from_user.id).state


def is_edit_menu(message: Message) -> bool:
    """Returns True when 'edit' in User.state"""
    return 'edit' in User.get(message.from_user.id).state

