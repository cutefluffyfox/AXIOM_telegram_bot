import logging
import json


def get_reply(state: str, text: str = "", callback: bool = False) -> dict:
    with open('answers.json', 'r', encoding='UTF-8') as file:
        logging.info(f'Get reply for state={state}, message={text}, callback={callback}')
        answers = json.load(file)
        state_messages = answers.get(state, answers['*'])
        reply = state_messages.get(text if text != '#' else '*', state_messages['*'])  # message '#' is restricted in this bot
        return reply if (not callback) else state_messages['#']


def is_unknown_reply(state: str, text: str) -> bool:
    answers = json.load(open('answers.json', 'r', encoding='UTF-8'))
    state_messages = answers.get(state, answers['*'])
    reply = state_messages.get(text, '*')
    return reply == '*'


def get_keywords(state: str) -> dict:
    answers = json.load(open('answers.json', 'r', encoding='UTF-8'))
    state_messages = answers.get(state, answers['*'])
    state_messages.pop('*', None)
    return state_messages

# def send_independent_message(chat_id: int, text: str, **kwargs):
#     logging.info('Sending independent message')
#     local_bot = Bot(token=BOT_TOKEN)
#     dp = Dispatcher(local_bot)
#     executor.start(dp, local_bot.send_message(chat_id, text, **kwargs))
