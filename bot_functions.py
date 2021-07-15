import logging
import json


def get_reply(state: str, message: str):
    logging.info(f'Get reply for state={state}, message={message}')
    answers = json.load(open('answers.json', 'r', encoding='UTF-8'))
    state_messages = answers.get(state, answers['*'])
    reply = state_messages.get(message, state_messages['*'])
    return reply


# def send_independent_message(chat_id: int, text: str, **kwargs):
#     logging.info('Sending independent message')
#     local_bot = Bot(token=BOT_TOKEN)
#     dp = Dispatcher(local_bot)
#     executor.start(dp, local_bot.send_message(chat_id, text, **kwargs))
