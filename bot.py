import logging
import os
import asyncio

import dotenv
from aiogram import Bot, Dispatcher, executor
from aiogram.types import Message, CallbackQuery
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types.reply_keyboard import ReplyKeyboardRemove

import database
import filters
from models import User, UserInfo, Discussion, Dialog, Suggestion
from bot_functions import get_reply, is_unknown_reply, button_to_command, get_config, has_buttons


# Configure logging
logging.basicConfig(
    format='%(asctime)s %(levelname)-8s %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)


# Initialize environment variables from .env file (if it exists)
dotenv.load_dotenv(dotenv.find_dotenv())
BOT_TOKEN = os.getenv('BOT_TOKEN')
CONNECTION_STRING = os.getenv('CONNECTION_STRING')

if BOT_TOKEN is None:
    logging.critical('No BOT_TOKEN variable found in project environment')
if CONNECTION_STRING is None:
    logging.critical('No CONNECTION_STRING variable found in project environment')

# Initialize database and models
database.global_init(CONNECTION_STRING)

# Initialize bot and dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)


def get_keyboard_markup(user_state: str, message_text: str, safe: bool = True, skip: list or tuple = tuple()) -> ReplyKeyboardMarkup:
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for button in get_reply(user_state, message_text, keyboard_buttons=True, safe=safe):
        if button['text'] not in skip:
            keyboard.add(KeyboardButton(button['text']))
    return keyboard


def get_inline_markup(user_state: str, message_text: str, safe: bool = True) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for button in get_reply(user_state, message_text, inline_buttons=True, safe=safe):
        keyboard.add(InlineKeyboardButton(button['text'], callback_data=button['command']))
    return keyboard


async def close_discussion_automatically(discussion_id: int):
    discussion: Discussion = Discussion.get(discussion_id)

    start_time = discussion.get_last_message().time
    await asyncio.sleep(get_config()['waiting_time'])
    discussion.update()
    end_time = discussion.get_last_message().time

    if start_time == end_time and discussion.finished == False:
        discussion.set(finished=True)

        logging.info(f'Closing all questions in moderator_chat about {discussion} due to time limit')
        for question in discussion.get_questions():
            moderator_chat_message: str = get_reply('moderator_chat', '#CLOSED')['moderator_chat_message']
            moderator_chat_message = moderator_chat_message.replace('%theme%', discussion.theme)
            moderator_chat_message = moderator_chat_message.replace('%id%', str(discussion.id))
            moderator_chat_message = moderator_chat_message.replace('%text%', question.text)

            await bot.edit_message_text(moderator_chat_message, get_config()['moderator_chat'], question.bot_message_id)

        user_chat_message: str = get_reply('moderator_chat', '#CLOSED')['user_chat_message']
        user_chat_message = user_chat_message.replace('%theme%', discussion.theme)
        user_chat_message = user_chat_message.replace('%id%', str(discussion.id))
        await bot.send_message(discussion.user_id, user_chat_message, reply_to_message_id=discussion.get_last_question().message_id)


@dp.message_handler(lambda msg: filters.is_group_chat(msg), commands=['get_chat_id'])
async def send_chat_id(message: Message):
    await message.reply(f"id этого чата:\n{message.chat.id}")


@dp.message_handler(lambda msg: filters.is_group_chat(msg))
async def group_chat(message: Message):
    if message.chat.id != get_config()['moderator_chat']:  # bot can only read MODERATOR chat
        return
    if message.reply_to_message is None:  # only read replies
        return
    bot_message_id = message.reply_to_message.message_id
    question: Dialog = Dialog.get_question(bot_message_id)
    if question is None:  # if it's not random reply
        return
    discussion = Discussion.get(question.discussion_id)

    Dialog.add(question.discussion_id, message.text, message.from_user.id, message.message_id, bot_message_id, moderator=True)
    moderator_chat_message: str = get_reply('moderator_chat', '#WAITING')['moderator_chat_message']
    moderator_chat_message = moderator_chat_message.replace('%theme%', discussion.theme)
    moderator_chat_message = moderator_chat_message.replace('%id%', str(discussion.id))
    moderator_chat_message = moderator_chat_message.replace('%text%', question.text)

    user_chat_message: str = get_reply('moderator_chat', '#WAITING')['user_chat_message']
    user_chat_message = user_chat_message.replace('%theme%', discussion.theme)
    user_chat_message = user_chat_message.replace('%id%', str(discussion.id))
    user_chat_message = user_chat_message.replace('%text%', message.text)

    await bot.send_message(question.who, user_chat_message, reply_to_message_id=question.message_id)
    if (message.reply_to_message.text != moderator_chat_message) and (not discussion.finished):  # if messages are not the same AND discussion not
        await bot.edit_message_text(moderator_chat_message, get_config()['moderator_chat'], question.bot_message_id)

    asyncio.get_event_loop().create_task(close_discussion_automatically(discussion.id))


@dp.message_handler(lambda msg: filters.user_not_in_database(msg))
async def add_user_to_database(message: Message):
    logging.info(f"New user written a message")
    User.add(message.from_user.id)
    UserInfo.add(message.from_user.id)
    user: User = User.get(message.from_user.id)

    reply = get_reply(user.state, message.text)
    keyboard = ReplyKeyboardRemove()

    user.set(state=reply['next'])
    await message.answer(reply['message'], reply_markup=keyboard)


@dp.message_handler(lambda msg: filters.state_is(msg, 'registered') and msg.text == '/ask' or filters.is_question_menu(msg))
async def question_menu(message: Message):
    user: User = User.get(message.from_user.id)
    logging.info(f'{user} sent "{message.text}"')

    if button_to_command(user.state, message.text) is not None:  # если это текст кнопки, то заменяем текст на комманду
        message.text = button_to_command(user.state, message.text)
    reply = get_reply(user.state, message.text)
    keyboard = ReplyKeyboardRemove()

    if user.state == 'registered':
        keyboard = get_keyboard_markup(user.state, message.text)

    elif user.state == 'question_menu':
        if message.text == '/leave':
            keyboard = get_keyboard_markup(user.state, message.text)
        elif message.text == '/new_question':
            reply = get_reply(user.state, '/new_question')
            keyboard = get_keyboard_markup(user.state, message.text)

        elif message.text == '/my_questions':
            keyboard = InlineKeyboardMarkup()
            for discussion in Discussion.get_discussions(message.from_user.id):
                keyboard.add(InlineKeyboardButton(f"[{discussion.theme} #{discussion.id}]", callback_data=f"{discussion.id}"))
            for button in get_reply(user.state, message.text, inline_buttons=True):
                keyboard.add(InlineKeyboardButton(button['text'], callback_data=button['command']))
        else:
            keyboard = get_keyboard_markup(user.state, '*')

    elif user.state == 'user_questions':
        if message.text == '/cancel':
            keyboard = get_keyboard_markup(user.state, message.text)
        else:
            keyboard = InlineKeyboardMarkup()
            for discussion in Discussion.get_discussions(message.from_user.id):
                keyboard.add(InlineKeyboardButton(f"[{discussion.theme} #{discussion.id}]", callback_data=f"{discussion.id}"))
            for button in get_reply(user.state, message.text, inline_buttons=True):
                keyboard.add(InlineKeyboardButton(button['text'], callback_data=button['command']))
    elif user.state == 'question1':
        if not is_unknown_reply(user.state, message.text):
            Discussion.add(message.from_user.id, message.text)
            discussion = Discussion.get_discussions(message.from_user.id)[-1]
            user.set(cache=str(discussion.id))
        else:
            keyboard = get_keyboard_markup(user.state, '*')
    elif user.state == 'question2':
        discussion = Discussion.get(int(user.cache))
        moderator_chat_message: str = get_reply('moderator_chat', '#OPEN')['moderator_chat_message']
        moderator_chat_message = moderator_chat_message.replace('%theme%', discussion.theme)
        moderator_chat_message = moderator_chat_message.replace('%id%', str(discussion.id))
        moderator_chat_message = moderator_chat_message.replace('%text%', message.text)
        bot_message = await bot.send_message(get_config()['moderator_chat'], moderator_chat_message)
        Dialog.add(discussion.id, message.text, message.from_user.id, message.message_id, bot_message.message_id, moderator=False)
        user.set(cache='')
        keyboard = get_keyboard_markup(user.state, '*')

    elif user.state == 'user_question1':
        if message.text == '/cancel':
            keyboard = InlineKeyboardMarkup()
            for discussion in Discussion.get_discussions(message.from_user.id):
                keyboard.add(InlineKeyboardButton(f"[{discussion.theme} #{discussion.id}]", callback_data=f"{discussion.id}"))
            for button in get_reply(user.state, message.text, inline_buttons=True):
                keyboard.add(InlineKeyboardButton(button['text'], callback_data=button['command']))
        elif message.text == '/close':
            discussion: Discussion = Discussion.get(int(user.cache))
            discussion.set(finished=True)
            user.set(cache="")
            keyboard = get_keyboard_markup(user.state, message.text)

            logging.info(f'Closing all questions in moderator_chat about {discussion}')
            for question in discussion.get_questions():
                moderator_chat_message: str = get_reply('moderator_chat', '#CLOSED')['moderator_chat_message']
                moderator_chat_message = moderator_chat_message.replace('%theme%', discussion.theme)
                moderator_chat_message = moderator_chat_message.replace('%id%', str(discussion.id))
                moderator_chat_message = moderator_chat_message.replace('%text%', question.text)

                await bot.edit_message_text(moderator_chat_message, get_config()['moderator_chat'], question.bot_message_id)
        else:
            keyboard = get_keyboard_markup(user.state, '*')

    user.set(state=reply['next'])
    await message.answer(reply['message'], reply_markup=keyboard)


@dp.callback_query_handler(lambda msg: filters.is_question_menu(msg))
async def question_menu_callback(callback_query: CallbackQuery):
    user: User = User.get(callback_query.from_user.id)
    logging.info(f'{user} pressed button "{callback_query.data}"')

    reply = dict()
    keyboard = ReplyKeyboardRemove()

    if user.state == 'user_questions':
        if callback_query.data == '/cancel':
            reply = get_reply(user.state, callback_query.data)
            keyboard = get_keyboard_markup(user.state, callback_query.data)
        elif any(int(callback_query.data) == discussion.id for discussion in Discussion.get_discussions(callback_query.from_user.id)):
            reply = get_reply(user.state, callback=True)
            user.set(cache=callback_query.data)
            keyboard = get_keyboard_markup(user.state, '#', safe=False)
        else:
            reply = get_reply(user.state)
    else:
        reply = get_reply(user.state, '*')

    user.set(state=reply['next'])
    await bot.send_message(callback_query.from_user.id, reply['message'], reply_markup=keyboard)


@dp.message_handler(lambda msg: filters.state_is(msg, 'registered') and msg.text == '/suggest' or filters.is_suggestion_menu(msg))
async def suggestion_menu(message: Message):
    user: User = User.get(message.from_user.id)
    logging.info(f'{user} sent "{message.text}"')

    if button_to_command(user.state, message.text) is not None:  # если это текст кнопки, то заменяем текст на комманду
        message.text = button_to_command(user.state, message.text)
    reply = get_reply(user.state, message.text)
    keyboard = ReplyKeyboardRemove()

    if user.state == 'registered':
        keyboard = get_keyboard_markup(user.state, message.text)

    elif user.state == 'suggestion_menu':
        if message.text == '/leave':
            keyboard = get_keyboard_markup(user.state, message.text)
        elif message.text == '/new_suggestion':
            reply = get_reply(user.state, message.text)
            keyboard = get_keyboard_markup(user.state, message.text)

        elif message.text == '/my_suggestions':
            keyboard = InlineKeyboardMarkup()
            for suggestion in Suggestion.get_suggestions(message.from_user.id)[::-1][:get_config()['suggestions_limit']]:
                keyboard.add(InlineKeyboardButton(f"[{suggestion.theme} #{suggestion.id}]", callback_data=f"{suggestion.id}"))
            for button in get_reply(user.state, message.text, inline_buttons=True):
                keyboard.add(InlineKeyboardButton(button['text'], callback_data=button['command']))
        else:
            keyboard = get_keyboard_markup(user.state, '*')

    elif user.state == 'user_suggestions':
        if message.text == '/cancel':
            keyboard = get_keyboard_markup(user.state, message.text)
        else:
            keyboard = InlineKeyboardMarkup()
            for suggestion in Suggestion.get_suggestions(message.from_user.id):
                keyboard.add(InlineKeyboardButton(f"[{suggestion.theme} #{suggestion.id}]", callback_data=f"{suggestion.id}"))
            for button in get_reply(user.state, message.text, inline_buttons=True):
                keyboard.add(InlineKeyboardButton(button['text'], callback_data=button['command']))
    elif user.state == 'suggestion1':
        if not is_unknown_reply(user.state, message.text):
            Suggestion.add(message.from_user.id, message.text)
            suggestion = Suggestion.get_suggestions(message.from_user.id)[-1]
            user.set(cache=str(suggestion.id))
        else:
            keyboard = get_keyboard_markup(user.state, '*')
    elif user.state == 'suggestion2':
        user_info: UserInfo = UserInfo.get(user.id)
        suggestion = Suggestion.get(int(user.cache))
        admin_chat_message: str = get_reply('moderator_chat', '#Suggestion')['admin_chat_message']
        admin_chat_message = admin_chat_message.replace('%theme%', suggestion.theme)
        admin_chat_message = admin_chat_message.replace('%id%', str(suggestion.id))
        admin_chat_message = admin_chat_message.replace('%email%', user_info.email)
        admin_chat_message = admin_chat_message.replace('%text%', message.text)
        admin_chat_message = admin_chat_message.replace('%user_id%', str(user.id))

        admin_chat_message = admin_chat_message.replace('<', '[[')
        admin_chat_message = admin_chat_message.replace('>', ']]')
        await bot.send_message(get_config()['admin_chat'], admin_chat_message, parse_mode='HTML')
        suggestion.set(text=message.text)
        user.set(cache='')
        keyboard = get_keyboard_markup(user.state, '*')

    user.set(state=reply['next'])
    await message.answer(reply['message'], reply_markup=keyboard)


@dp.callback_query_handler(lambda msg: filters.is_suggestion_menu(msg))
async def suggestion_menu_callback(callback_query: CallbackQuery):
    user: User = User.get(callback_query.from_user.id)
    logging.info(f'{user} pressed button "{callback_query.data}"')

    reply = dict()
    keyboard = ReplyKeyboardRemove()

    if user.state == 'user_suggestions':
        if callback_query.data == '/cancel':
            reply = get_reply(user.state, callback_query.data)
            keyboard = get_keyboard_markup(user.state, callback_query.data)
        elif any(int(callback_query.data) == suggestion.id for suggestion in Suggestion.get_suggestions(callback_query.from_user.id)):
            reply = get_reply(user.state, callback=True)
            suggestion: Suggestion = Suggestion.get(int(callback_query.data))
            user_chat_message = reply['user_chat_message']
            user_chat_message = user_chat_message.replace('%theme%', suggestion.theme)
            user_chat_message = user_chat_message.replace('%id%', str(suggestion.id))
            user_chat_message = user_chat_message.replace('%text%', suggestion.text)
            await bot.send_message(callback_query.from_user.id, user_chat_message)
            keyboard = get_keyboard_markup(user.state, '#', safe=False)
        else:
            reply = get_reply(user.state)
    else:
        reply = get_reply(user.state, '*')
        if has_buttons(user.state):
            keyboard = get_keyboard_markup(user.state, '*')

    user.set(state=reply['next'])
    await bot.send_message(callback_query.from_user.id, reply['message'], reply_markup=keyboard)


@dp.message_handler(lambda msg: filters.is_register_menu(msg))
async def register(message: Message):
    user: User = User.get(message.from_user.id)
    user_info: UserInfo = UserInfo.get(message.from_user.id)

    if button_to_command(user.state, message.text) is not None:  # если это текст кнопки, то заменяем текст на комманду
        message.text = button_to_command(user.state, message.text)
    reply = get_reply(user.state, message.text)
    keyboard = ReplyKeyboardRemove()

    if user.state == 'register1':
        user_info.set(surname=message.text)
    elif user.state == 'register2':
        user_info.set(name=message.text)
        keyboard = get_inline_markup(user.state, '*')

    elif user.state == 'register3':
        if message.text != '/skip':
            user_info.set(patronymic=message.text)

    elif user.state == 'register4':
        user_info.set(email=message.text)
        keyboard = get_keyboard_markup(user.state, '*')

    elif user.state == 'register5':
        if is_unknown_reply(user.state, message.text):
            keyboard = get_keyboard_markup(user.state, '*')
        else:
            user_info.set(job=message.text)
            user.set(cache=message.text)
            keyboard = get_keyboard_markup(user.state, message.text, skip=(user.cache,))

    elif user.state == 'register6':
        if is_unknown_reply(user.state, message.text):
            keyboard = get_keyboard_markup(user.state, '*', skip=(user.cache,))
        else:
            if message.text != 'Пропустить' and message.text != user_info.job:
                user_info.set(job=user_info.job + ';' + message.text)
            user.set(cache='')

            # TODO: отправить собранные данные на сервер

    user.set(state=reply['next'])
    await message.answer(reply['message'], reply_markup=keyboard)


@dp.callback_query_handler(lambda msg: filters.is_register_menu(msg))
async def register_callback(callback_query: CallbackQuery):
    user: User = User.get(callback_query.from_user.id)
    logging.info(f'{user} pressed button "{callback_query.data}"')

    reply = dict()
    keyboard = ReplyKeyboardRemove()

    if user.state == 'register3':
        if callback_query.data == '/skip':
            reply = get_reply(user.state, callback_query.data)
        else:
            reply = get_reply(user.state)
    else:
        reply = get_reply(user.state)

    user.set(state=reply['next'])
    await bot.send_message(callback_query.from_user.id, reply['message'], reply_markup=keyboard)


@dp.message_handler()
async def simple_commands(message: Message):
    user: User = User.get(message.from_user.id)
    logging.info(f'{user} sent "{message.text}"')

    keyboard = ReplyKeyboardRemove()
    if has_buttons(user.state):
        if button_to_command(user.state, message.text) is not None:  # если это текст кнопки, то заменяем текст на комманду
            message.text = button_to_command(user.state, message.text)
            reply = get_reply(user.state, message.text)
            if has_buttons(reply['next']):
                keyboard = get_keyboard_markup(user.state, message.text)
        else:
            keyboard = get_keyboard_markup(user.state, '*')
    reply = get_reply(user.state, message.text)

    user.set(state=reply['next'])
    await message.answer(reply['message'], reply_markup=keyboard)


if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=False)
