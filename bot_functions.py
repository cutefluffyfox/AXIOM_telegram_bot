import logging
import json

from aiogram.types import Message


def get_reply(state: str, text: str = "", callback: bool = False, keyboard_buttons: bool = False, inline_buttons: bool = False, safe: bool = True) -> dict or list:
    with open('answers.json', 'r', encoding='UTF-8') as file:
        logging.info(f'Get reply for state={state}, message={text}, callback={callback}, keyboard_buttons={keyboard_buttons}, inline_buttons={inline_buttons}')
        answers = json.load(file)
        state_messages = answers.get(state, answers['*'])
        if callback:
            return parse_link(state_messages['#'], state)
        if safe:
            text = '*' if (text in get_config()['restricted_messages']) else text
        reply: dict = state_messages.get(text, state_messages['*'])
        if keyboard_buttons:
            return get_raw_button(reply['next'], '#KeyboardButtons')
        if inline_buttons:
            return get_raw_button(reply['next'], '#InlineButtons')

        return parse_link(reply, state)


def get_raw_button(state: str, button_type: str) -> list:
    return get_reply(state, button_type, safe=False)


def parse_link(reply: dict or list, state: str) -> dict or list:
    if (type(reply) == dict) and (reply.get('message') is None) and (reply.get('message_link') is not None):
        if reply['message_link'][0] == '#Template':
            reply['message'] = get_reply(state, "#Template", safe=False)[reply['message_link'][1]]
        else:
            reply['message'] = get_reply(*reply['message_link'])['message']
    return reply


def button_to_command(state: str, message: Message) -> str or None:
    with open('answers.json', 'r', encoding='UTF-8') as file:
        logging.info(f'Get KeyboardButton state for user_state={state}, button_text={message.text}')
        answers = json.load(file)
        for button in answers.get(state, answers['*']).get('#KeyboardButtons', {}):
            if button['text'] == message.text:
                message.text = button['command']


def is_unknown_reply(state: str, text: str) -> bool:
    with open('answers.json', 'r', encoding='UTF-8') as file:
        answers = json.load(file)
        state_messages = answers.get(state, answers['*'])
        reply = state_messages.get(text, None)
        return (reply is None) or (text in ['#', '#KeyboardButtons', '#InlineButtons'])


def get_keywords(state: str) -> dict:
    with open('answers.json', 'r', encoding='UTF-8') as file:
        answers = json.load(file)
        state_messages = answers.get(state, answers['*'])
        state_messages.pop('*', None)
        return state_messages


def get_config() -> dict:
    with open('config.json', 'r', encoding='UTF-8') as file:
        return json.load(file)


def has_keyboard_buttons(state: str, text: str, safe: bool = True) -> bool:
    with open('answers.json', 'r', encoding='UTF-8') as file:
        answers = json.load(file)
        state_messages = answers.get(state, answers['*'])
        if safe:
            text = '*' if text in get_config()['restricted_messages'] else text
        reply = state_messages.get(text, state_messages['*'])
        next_state_messages = answers.get(reply['next'], answers['*'])
        return next_state_messages.get('#KeyboardButtons') is not None


def has_inline_buttons(state: str, text: str, safe: bool = True) -> bool:
    with open('answers.json', 'r', encoding='UTF-8') as file:
        answers = json.load(file)
        state_messages = answers.get(state, answers['*'])
        if safe:
            text = '*' if text in get_config()['restricted_messages'] else text
        reply = state_messages.get(text, state_messages['*'])
        next_state_messages = answers.get(reply['next'], answers['*'])
        return next_state_messages.get('#InlineButtons') is not None

# def send_independent_message(chat_id: int, text: str, **kwargs):
#     logging.info('Sending independent message')
#     local_bot = Bot(token=BOT_TOKEN)
#     dp = Dispatcher(local_bot)
#     executor.start(dp, local_bot.send_message(chat_id, text, **kwargs))
