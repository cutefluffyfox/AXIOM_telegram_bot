import logging
import json


def get_reply(state: str, text: str = "", callback: bool = False, keyboard_buttons: bool = False, inline_buttons: bool = False, safe: bool = True) -> dict:
    with open('answers.json', 'r', encoding='UTF-8') as file:
        logging.info(f'Get reply for state={state}, message={text}, callback={callback}, keyboard_buttons={keyboard_buttons}, inline_buttons={inline_buttons}')
        answers = json.load(file)
        state_messages = answers.get(state, answers['*'])
        if callback:
            return state_messages['#']
        if safe:
            text = text if text != '#' else '*'  # message '#' is restricted in this bot
        reply = state_messages.get(text, state_messages['*'])
        if keyboard_buttons:
            return get_reply(reply['next'], '#KeyboardButtons')
        if inline_buttons:
            return get_reply(reply['next'], '#InlineButtons')

        return reply


def button_to_command(state: str, text: str) -> str or None:
    with open('answers.json', 'r', encoding='UTF-8') as file:
        logging.info(f'Get KeyboardButton state for user_state={state}, button_text={text}')
        answers = json.load(file)
        for button in answers.get(state, answers['*']).get('#KeyboardButtons', {}):
            if button['text'] == text:
                return button['command']
    return None


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


def read_config() -> dict:
    with open('answers.json', 'r', encoding='UTF-8') as file:
        return json.load(file)

# def send_independent_message(chat_id: int, text: str, **kwargs):
#     logging.info('Sending independent message')
#     local_bot = Bot(token=BOT_TOKEN)
#     dp = Dispatcher(local_bot)
#     executor.start(dp, local_bot.send_message(chat_id, text, **kwargs))
