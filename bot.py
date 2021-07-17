import logging
import os

import dotenv
from aiogram import Bot, Dispatcher, executor
from aiogram.types import Message, CallbackQuery
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types.reply_keyboard import ReplyKeyboardRemove

import database
import filters
from models import User, UserInfo, Discussion, Question
from bot_functions import get_reply, is_unknown_reply


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
MODERATOR_CHAT = os.getenv('MODERATOR_CHAT')

if MODERATOR_CHAT is None:
    logging.warning('MODERATOR_CHAT variable is undefined. Set this variable in .env file for proper work')
else:
    MODERATOR_CHAT = int(MODERATOR_CHAT)

# Initialize database and models
database.global_init(CONNECTION_STRING)

# Initialize bot and dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)


@dp.message_handler(commands=['get_chat_id'])
async def send_chat_id(message: Message):
    await message.reply(f"id этого чата:\n{message.chat.id}")


@dp.message_handler(lambda msg: filters.is_group_chat(msg))
async def group_chat(message: Message):
    if message.chat.id != MODERATOR_CHAT:  # bot can only read MODERATOR chat
        return
    if message.reply_to_message is None:
        return
    bot_message_id = message.reply_to_message.message_id
    question = Question.get(bot_message_id)
    if question is None:
        return
    discussion = Discussion.get(question.discussion_id)
    question.set_answer(message.text, message.from_user.id, message.message_id)
    moderator_chat_message = f"[{discussion.theme} #{discussion.id} #WAITING]\n\n{question.question}"
    message_text = f"Ответ на вопрос по теме: [{discussion.theme} #{discussion.id}]\n\n{message.text}\n\nПерейдите на страницу /ask чтобы продолжть обсуждение по этому вопросу"
    await bot.send_message(question.who_asked, message_text, reply_to_message_id=question.question_message_id)
    await bot.edit_message_text(moderator_chat_message, MODERATOR_CHAT, question.bot_message_id)


@dp.message_handler(lambda msg: filters.user_not_in_database(msg))
async def add_user_to_database(message: Message):
    logging.info(f"New user written a message")
    User.add(message.from_user.id)
    UserInfo.add(message.from_user.id)
    user: User = User.get(message.from_user.id)

    reply = get_reply(user.state, message.text)

    user.set(state=reply['next'])
    await message.answer(reply['message'])


@dp.message_handler(lambda msg: filters.state_is(msg, 'registered') and msg.text == '/ask' or filters.is_question_page(msg))
async def question_menu(message: Message):
    user: User = User.get(message.from_user.id)
    logging.info(f'{user} sent "{message.text}"')

    reply = get_reply(user.state, message.text)
    keyboard = ReplyKeyboardRemove()

    if user.state == 'registered':
        keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        keyboard.add(KeyboardButton('/new_question'))
        keyboard.add(KeyboardButton('/my_questions'))
        keyboard.add(KeyboardButton('/help'))
        keyboard.add(KeyboardButton('/leave'))
    elif user.state == 'question_menu':
        if message.text == '/leave':
            pass
        elif message.text == '/new_question':
            keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            keyboard.add(KeyboardButton('Соревнования'))
            keyboard.add(KeyboardButton('Команды'))
            keyboard.add(KeyboardButton('Регистрация'))
            keyboard.add(KeyboardButton('Другое'))
        elif message.text == '/my_questions':
            keyboard = InlineKeyboardMarkup()
            for discussion in Discussion.get_discussions(message.from_user.id):
                keyboard.add(InlineKeyboardButton(f"[{discussion.theme} #{discussion.id}]", callback_data=f"{discussion.id}"))
            keyboard.add(InlineKeyboardButton('/cancel', callback_data='/cancel'))
    elif user.state == 'user_questions':
        keyboard = InlineKeyboardMarkup()
        for discussion in Discussion.get_discussions(message.from_user.id):
            keyboard.add(InlineKeyboardButton(f"[{discussion.theme} #{discussion.id}]", callback_data=f"{discussion.id}"))
        keyboard.add(InlineKeyboardButton('/cancel', callback_data='/cancel'))
    elif user.state == 'question1' and (not is_unknown_reply(user.state, message.text)):
        Discussion.add(message.from_user.id, message.text)
        discussion = Discussion.get_discussions(message.from_user.id)[-1]
        user.set(cache=str(discussion.id))
    elif user.state == 'question2':
        discussion = Discussion.get(int(user.cache))
        moderator_chat_message = f"[{discussion.theme} #{discussion.id} #OPEN]\n\n{message.text}"
        bot_message = await bot.send_message(MODERATOR_CHAT, moderator_chat_message)
        Question.add(discussion.id, message.text, message.from_user.id, message.message_id, bot_message.message_id)
    elif user.state == 'user_question1':
        if is_unknown_reply(user.state, message.text):
            keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            keyboard.add(KeyboardButton('/continue'))
            keyboard.add(KeyboardButton('/close'))
            keyboard.add(KeyboardButton('/cancel'))
        elif message.text == '/cancel':
            keyboard = InlineKeyboardMarkup()
            for discussion in Discussion.get_discussions(message.from_user.id):
                keyboard.add(InlineKeyboardButton(f"[{discussion.theme} #{discussion.id}]", callback_data=f"{discussion.id}"))
            keyboard.add(InlineKeyboardButton('/cancel', callback_data='/cancel'))
        elif message.text == '/close':
            discussion = Discussion.get(user.cache)
            discussion.set(finished=True)
            user.set(cache="")

            logging.info(f'Deleting all messages in moderator_chat about {discussion}')
            for question in discussion.get_questions():
                moderator_chat_message = f"[{discussion.theme} #{discussion.id} #CLOSED]\n\n{question.question}"
                await bot.edit_message_text(moderator_chat_message, MODERATOR_CHAT, question.bot_message_id)

    user.set(state=reply['next'])
    await message.answer(reply['message'], reply_markup=keyboard)


@dp.callback_query_handler(lambda msg: filters.is_question_page(msg))
async def question_menu_callback(callback_query: CallbackQuery):
    user: User = User.get(callback_query.from_user.id)
    logging.info(f'{user} pressed button "{callback_query.data}"')

    reply = dict()
    keyboard = ReplyKeyboardRemove()

    if user.state == 'user_questions':
        if callback_query.data == '/cancel':
            reply = get_reply(user.state, '/cancel')
        elif any(int(callback_query.data) == discussion.id for discussion in Discussion.get_discussions(callback_query.from_user.id)):
            reply = get_reply(user.state, callback=True)
            user.set(cache=callback_query.data)
            keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            keyboard.add(KeyboardButton('/continue'))
            keyboard.add(KeyboardButton('/close'))
            keyboard.add(KeyboardButton('/cancel'))
        else:
            reply = get_reply(user.state)

    user.set(state=reply['next'])
    await bot.send_message(callback_query.from_user.id, reply['message'], reply_markup=keyboard)


@dp.message_handler(lambda msg: filters.state_is_register(msg))
async def register(message: Message):
    user: User = User.get(message.from_user.id)
    user_info: UserInfo = UserInfo.get(message.from_user.id)

    reply = get_reply(user.state, message.text)
    keyboard = ReplyKeyboardRemove()

    if user.state == 'register1':
        user_info.set(surname=message.text)
    elif user.state == 'register2':
        user_info.set(name=message.text)
        keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        keyboard.add(KeyboardButton('Нет отчества'))

    elif user.state == 'register3':
        user_info.set(patronymic=(None if message.text == 'Нет отчества' else message.text))

    elif user.state == 'register4':
        user_info.set(email=message.text)
        keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        keyboard.add(KeyboardButton('Инженер'))
        keyboard.add(KeyboardButton('Химик-биолог'))
        keyboard.add(KeyboardButton('Программист'))
        keyboard.add(KeyboardButton('Копирайтер'))
        keyboard.add(KeyboardButton('Дизайнер'))

    elif user.state == 'register5':
        if is_unknown_reply(user.state, message.text):
            keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            keyboard.add(KeyboardButton('Инженер'))
            keyboard.add(KeyboardButton('Химик-биолог'))
            keyboard.add(KeyboardButton('Программист'))
            keyboard.add(KeyboardButton('Копирайтер'))
            keyboard.add(KeyboardButton('Дизайнер'))
        else:
            user_info.set(job=message.text)
            keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            if user_info.job != 'Инженер': keyboard.add(KeyboardButton('Инженер'))
            if user_info.job != 'Химик-биолог': keyboard.add(KeyboardButton('Химик-биолог'))
            if user_info.job != 'Программист': keyboard.add(KeyboardButton('Программист'))
            if user_info.job != 'Копирайтер': keyboard.add(KeyboardButton('Копирайтер'))
            if user_info.job != 'Дизайнер': keyboard.add(KeyboardButton('Дизайнер'))
            keyboard.add(KeyboardButton('Пропустить'))

    elif user.state == 'register6':
        if is_unknown_reply(user.state, message.text):
            keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            if user_info.job != 'Инженер': keyboard.add(KeyboardButton('Инженер'))
            if user_info.job != 'Химик-биолог': keyboard.add(KeyboardButton('Химик-биолог'))
            if user_info.job != 'Программист': keyboard.add(KeyboardButton('Программист'))
            if user_info.job != 'Копирайтер': keyboard.add(KeyboardButton('Копирайтер'))
            if user_info.job != 'Дизайнер': keyboard.add(KeyboardButton('Дизайнер'))
            keyboard.add(KeyboardButton('Пропустить'))
        else:
            if message.text != 'Пропустить' and message.text != user_info.job:
                user_info.set(job=user_info.job + ';' + message.text)

            # TODO: отправить собранные данные на сервер

    user.set(state=reply['next'])
    await message.answer(reply['message'], reply_markup=keyboard)


@dp.message_handler()
async def simple_commands(message: Message):
    user: User = User.get(message.from_user.id)
    logging.info(f'{user} sent "{message.text}"')

    reply = get_reply(user.state, message.text)

    user.set(state=reply['next'])
    await message.answer(reply['message'], reply_markup=ReplyKeyboardRemove())


if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=False)
