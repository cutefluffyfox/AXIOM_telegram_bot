import logging
import os
import asyncio

import dotenv
from aiogram import Bot, Dispatcher, executor
from aiogram.types import Message, CallbackQuery, ContentType
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types.reply_keyboard import ReplyKeyboardRemove

import api_v1 as api  # TODO: decide where API should be located (in sqlalchemy or in bot)
import database
import filters
from models import User, UserInfo, Discussion, Dialog, Suggestion
from bot_functions import (get_reply, is_unknown_reply, button_to_command, get_config, has_inline_buttons,
                           has_keyboard_buttons, get_raw_button, parse_link)


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
SERVER = os.getenv('SERVER')

if BOT_TOKEN is None:
    logging.critical('No BOT_TOKEN variable found in project environment')
if CONNECTION_STRING is None:
    logging.critical('No CONNECTION_STRING variable found in project environment')
if SERVER is None:
    logging.critical('No SERVER variable found in project environment')

# Initialize database and models
database.global_init(CONNECTION_STRING)

# Initialize bot and dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)


def get_markup(user_state: str = "*", message_text: str = "", skip: list or tuple = tuple(), safe: bool = True, buttons: list = None, buttons_type: str = None) -> ReplyKeyboardMarkup or InlineKeyboardMarkup or ReplyKeyboardRemove:
    """Returns ButtonMarkup that depends on next User.state"""
    if buttons is not None:  # If buttons already parsed
        if buttons_type == '#KeyboardButtons':
            keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            for button in buttons:
                if button['text'] not in skip:
                    keyboard.add(KeyboardButton(button['text']))
            return keyboard
        elif buttons_type == '#InlineButtons':
            keyboard = InlineKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            for button in buttons:
                keyboard.add(InlineKeyboardButton(button['text'], callback_data=button['command'], url=button.get('url')))
            return keyboard
    elif has_keyboard_buttons(user_state, message_text, safe=safe):  # If next User.state has KeyboardButtons
        keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        for button in get_reply(user_state, message_text, keyboard_buttons=True, safe=safe):
            if button['text'] not in skip:
                keyboard.add(KeyboardButton(button['text']))
        return keyboard
    elif has_inline_buttons(user_state, message_text, safe=safe):  # If next User.state has InlineButtons
        keyboard = InlineKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        for button in get_reply(user_state, message_text, inline_buttons=True, safe=safe):
            keyboard.add(InlineKeyboardButton(button['text'], callback_data=button['command'], url=button.get('url')))
        return keyboard
    return ReplyKeyboardRemove()  # If no buttons needed, deletes all that was


def fill_user_info(keyboard: ReplyKeyboardMarkup or InlineKeyboardMarkup or ReplyKeyboardMarkup, user_info: UserInfo):
    """replace %parameters% in inline buttons"""
    if 'inline_keyboard' in keyboard:
        for button_list in keyboard['inline_keyboard']:
            for button in button_list:
                button['text'] = button['text'].replace('%name%', user_info.name)
                button['text'] = button['text'].replace('%surname%', user_info.surname)
                button['text'] = button['text'].replace('%patronymic%', user_info.patronymic if user_info.patronymic is not None else 'Нет')
                button['text'] = button['text'].replace('%email%', user_info.email)
                button['text'] = button['text'].replace('%job%', user_info.job)


async def send_answer(message: Message or CallbackQuery, reply: dict, keyboard: ReplyKeyboardRemove or InlineKeyboardMarkup or ReplyKeyboardMarkup):
    """Sends extra and message"""
    if reply.get('extra') is not None:
        await message.answer(reply['extra'])
    await message.answer(reply['message'], reply_markup=keyboard)


async def close_discussion_automatically(discussion_id: int):
    """Sets timer for confin.json -> waiting_time seconds & closes menu if no replies was sent"""
    discussion: Discussion = Discussion.get(discussion_id)

    start_time = discussion.get_last_message().time
    await asyncio.sleep(get_config()['waiting_time'])  # sleeping
    discussion.update()  # checking if anything changed
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
    """Special handler for group chat, that helps getting chat_id for config chat"""
    await message.reply(f"id этого чата:\n{message.chat.id}")


@dp.message_handler(lambda msg: filters.is_group_chat(msg))
async def group_chat(message: Message):
    """Group chat handler (works only in moderator_chat)"""
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
    if (message.reply_to_message.text != moderator_chat_message) and (not discussion.finished):  # if messages are not the same AND discussion not finished
        await bot.edit_message_text(moderator_chat_message, get_config()['moderator_chat'], question.bot_message_id)

    asyncio.get_event_loop().create_task(close_discussion_automatically(discussion.id))  # starts delete timer in another thread


@dp.message_handler(lambda msg: filters.user_not_in_database(msg))
async def add_user_to_database(message: Message):
    """Adds new user to database and sends start message"""
    logging.info(f"New user written a message")
    User.add(message.from_user.id)
    UserInfo.add(message.from_user.id)
    user: User = User.get(message.from_user.id)

    reply = get_reply(user.state, message.text)
    keyboard = get_markup(user.state, message.text)

    user.set(state=reply['next'])
    await send_answer(message=message, reply=reply, keyboard=keyboard)


@dp.message_handler(lambda msg: filters.is_question_menu(msg))
async def question_menu(message: Message):
    """Handler for question menu and it's subpages"""
    user: User = User.get(message.from_user.id)
    logging.info(f'{user} sent "{message.text}"')

    button_to_command(user.state, message)
    reply = get_reply(user.state, message.text)
    keyboard = get_markup(user.state, message.text)

    if user.state == 'question_menu':
        if message.text == '/my_questions':
            keyboard = InlineKeyboardMarkup()
            for discussion in Discussion.get_discussions(message.from_user.id):  # Adds [theme id] buttons
                keyboard.add(InlineKeyboardButton(f"[{discussion.theme} #{discussion.id}]", callback_data=f"{discussion.id}"))
            for button in get_reply(user.state, message.text, inline_buttons=True):  # Adds /cancel button
                keyboard.add(InlineKeyboardButton(button['text'], callback_data=button['command']))

    elif user.state == 'user_questions':
        if message.text != '/cancel':
            keyboard = InlineKeyboardMarkup()
            for discussion in Discussion.get_discussions(message.from_user.id):  # Adds [theme id] buttons
                keyboard.add(InlineKeyboardButton(f"[{discussion.theme} #{discussion.id}]", callback_data=f"{discussion.id}"))
            for button in get_reply(user.state, message.text, inline_buttons=True):  # Adds /cancel button
                keyboard.add(InlineKeyboardButton(button['text'], callback_data=button['command']))

    elif user.state == 'question1':
        if not is_unknown_reply(user.state, message.text):
            Discussion.add(message.from_user.id, message.text)
            discussion = Discussion.get_discussions(message.from_user.id)[-1]
            user.set(cache=str(discussion.id))  # saves discussion_id in cache for question2 state

    elif user.state == 'question2':
        discussion = Discussion.get(int(user.cache))
        moderator_chat_message: str = get_reply('moderator_chat', '#OPEN')['moderator_chat_message']
        moderator_chat_message = moderator_chat_message.replace('%theme%', discussion.theme)
        moderator_chat_message = moderator_chat_message.replace('%id%', str(discussion.id))
        moderator_chat_message = moderator_chat_message.replace('%text%', message.text)
        bot_message = await bot.send_message(get_config()['moderator_chat'], moderator_chat_message)
        Dialog.add(discussion.id, message.text, message.from_user.id, message.message_id, bot_message.message_id, moderator=False)
        user.set(cache='')

    elif user.state == 'user_question1':
        if message.text == '/cancel':
            keyboard = InlineKeyboardMarkup()
            for discussion in Discussion.get_discussions(message.from_user.id):  # Adds [theme id] buttons
                keyboard.add(InlineKeyboardButton(f"[{discussion.theme} #{discussion.id}]", callback_data=f"{discussion.id}"))
            for button in get_reply(user.state, message.text, inline_buttons=True):   # Adds /cancel button
                keyboard.add(InlineKeyboardButton(button['text'], callback_data=button['command']))
        elif message.text == '/close':
            discussion: Discussion = Discussion.get(int(user.cache))
            discussion.set(finished=True)
            user.set(cache="")

            logging.info(f'Closing all questions in moderator_chat about {discussion}')
            for question in discussion.get_questions():
                moderator_chat_message: str = get_reply('moderator_chat', '#CLOSED')['moderator_chat_message']
                moderator_chat_message = moderator_chat_message.replace('%theme%', discussion.theme)
                moderator_chat_message = moderator_chat_message.replace('%id%', str(discussion.id))
                moderator_chat_message = moderator_chat_message.replace('%text%', question.text)

                await bot.edit_message_text(moderator_chat_message, get_config()['moderator_chat'], question.bot_message_id)

    user.set(state=reply['next'])
    await send_answer(message=message, reply=reply, keyboard=keyboard)


@dp.callback_query_handler(lambda msg: filters.is_question_menu(msg))
async def question_menu_callback(callback_query: CallbackQuery):
    """Handler for question menu and it's subpages Inline buttons"""
    user: User = User.get(callback_query.from_user.id)
    logging.info(f'{user} pressed button "{callback_query.data}"')

    reply = get_reply(user.state)
    keyboard = get_markup(user.state)

    if user.state == 'user_questions':
        if callback_query.data == '/cancel':
            reply = get_reply(user.state, callback_query.data)
            keyboard = get_markup(user.state, callback_query.data)

        elif any(int(callback_query.data) == discussion.id for discussion in Discussion.get_discussions(callback_query.from_user.id)):  # if correct discussion_id
            reply = get_reply(user.state, callback=True)
            user.set(cache=callback_query.data)
            keyboard = get_markup(user.state, '#', safe=False)

    user.set(state=reply['next'])
    await bot.send_message(callback_query.from_user.id, reply['message'], reply_markup=keyboard)


@dp.message_handler(lambda msg: filters.is_suggestion_menu(msg))
async def suggestion_menu(message: Message):
    """Handler for suggestion menu and it's subpages"""
    user: User = User.get(message.from_user.id)
    logging.info(f'{user} sent "{message.text}"')

    button_to_command(user.state, message)
    reply = get_reply(user.state, message.text)
    keyboard = get_markup(user.state, message.text)

    if user.state == 'suggestion_menu':
        if message.text == '/my_suggestions':
            keyboard = InlineKeyboardMarkup()
            for suggestion in Suggestion.get_suggestions(message.from_user.id)[::-1][:get_config()['suggestions_limit']]:  # Adds [theme id] buttons
                keyboard.add(InlineKeyboardButton(f"[{suggestion.theme} #{suggestion.id}]", callback_data=f"{suggestion.id}"))
            for button in get_reply(user.state, message.text, inline_buttons=True):  # Adds /cancel button
                keyboard.add(InlineKeyboardButton(button['text'], callback_data=button['command']))

    elif user.state == 'user_suggestions':
        if message.text != '/cancel':
            keyboard = InlineKeyboardMarkup()
            for suggestion in Suggestion.get_suggestions(message.from_user.id):
                keyboard.add(InlineKeyboardButton(f"[{suggestion.theme} #{suggestion.id}]", callback_data=f"{suggestion.id}"))  # Adds [theme id] buttons
            for button in get_reply(user.state, message.text, inline_buttons=True):  # Adds /cancel button
                keyboard.add(InlineKeyboardButton(button['text'], callback_data=button['command']))

    elif user.state == 'suggestion1':
        if not is_unknown_reply(user.state, message.text):
            Suggestion.add(message.from_user.id, message.text)
            suggestion = Suggestion.get_suggestions(message.from_user.id)[-1]
            user.set(cache=str(suggestion.id))  # saves suggestion_id in cache for suggestion2 state

    elif user.state == 'suggestion2':
        user_info: UserInfo = UserInfo.get(user.id)
        suggestion = Suggestion.get(int(user.cache))
        admin_chat_message: str = get_reply('moderator_chat', '#Suggestion')['admin_chat_message']
        admin_chat_message = admin_chat_message.replace('%theme%', suggestion.theme)
        admin_chat_message = admin_chat_message.replace('%id%', str(suggestion.id))
        admin_chat_message = admin_chat_message.replace('%email%', user_info.email)
        admin_chat_message = admin_chat_message.replace('%text%', message.text)
        admin_chat_message = admin_chat_message.replace('<', '[[')  # to block all user_html inputs
        admin_chat_message = admin_chat_message.replace('>', ']]')  # to block all user_html inputs
        admin_chat_message = admin_chat_message.replace('%user_id%', f'<a href="tg://user?id={user.id}">телеграм</a>')  # in case when user has no @alias, we are notifying them

        await bot.send_message(get_config()['admin_chat'], admin_chat_message, parse_mode='HTML')  # html to parse %user_id%
        suggestion.set(text=message.text)
        user.set(cache='')

    user.set(state=reply['next'])
    await send_answer(message=message, reply=reply, keyboard=keyboard)


@dp.callback_query_handler(lambda msg: filters.is_suggestion_menu(msg))
async def suggestion_menu_callback(callback_query: CallbackQuery):
    """Handler for suggestion menu and it's subpages Inline buttons"""
    user: User = User.get(callback_query.from_user.id)
    logging.info(f'{user} pressed button "{callback_query.data}"')

    reply = get_reply(user.state)
    keyboard = get_markup(user.state, callback_query.data)

    if user.state == 'user_suggestions':
        if callback_query.data == '/cancel':
            reply = get_reply(user.state, callback_query.data)

        elif any(int(callback_query.data) == suggestion.id for suggestion in Suggestion.get_suggestions(callback_query.from_user.id)):  # if correct suggestion_id
            reply = get_reply(user.state, callback=True)
            suggestion: Suggestion = Suggestion.get(int(callback_query.data))
            user_chat_message = reply['user_chat_message']
            user_chat_message = user_chat_message.replace('%theme%', suggestion.theme)
            user_chat_message = user_chat_message.replace('%id%', str(suggestion.id))
            user_chat_message = user_chat_message.replace('%text%', suggestion.text)
            await bot.send_message(callback_query.from_user.id, user_chat_message)
            keyboard = get_markup(user.state, '#', safe=False)

    user.set(state=reply['next'])
    await bot.send_message(callback_query.from_user.id, reply['message'], reply_markup=keyboard)


@dp.message_handler(lambda msg: filters.is_upload_menu(msg), content_types=ContentType.DOCUMENT)
async def upload_menu_document(message: Message):
    """Handler for documents on upload_page"""
    user: User = User.get(message.from_user.id)
    logging.info(f'{user} sent document named "{message.document.file_name}"')

    reply = get_reply(user.state, '#FileHandler', safe=False)
    keyboard = get_markup(user.state, '#FileHandler', safe=False)

    if message.document.mime_type == 'application/pdf':  # Checks is file is .pdf format (watch aiogram documentation)
        await message.reply(reply['success_message'], reply_markup=keyboard)
        # TODO download file & send it to server
    else:
        await message.reply(reply['fail_message'], reply_markup=keyboard)

    user.set(state=reply['next'])


@dp.message_handler(lambda msg: filters.is_upload_menu(msg), content_types=[
    ContentType.PHOTO, ContentType.ANIMATION, ContentType.AUDIO, ContentType.CONTACT,
    ContentType.GAME, ContentType.INVOICE, ContentType.LOCATION, ContentType.PASSPORT_DATA,
    ContentType.POLL, ContentType.STICKER, ContentType.SUCCESSFUL_PAYMENT, ContentType.VENUE,
    ContentType.VIDEO, ContentType.VIDEO_NOTE, ContentType.VOICE])
async def upload_menu_all_files(message: Message):
    """Handler for ALL wrong formats on upload_page"""
    user: User = User.get(message.from_user.id)
    logging.info(f'{user} sent random file')

    reply = get_reply(user.state, '#FileHandler', safe=False)
    keyboard = get_markup(user.state, '#FileHandler')

    await message.reply(reply['fail_message'], reply_markup=keyboard)

    user.set(state=reply['next'])


@dp.message_handler(lambda msg: filters.is_register_menu(msg))
async def register(message: Message):
    """Handler for registration menu"""
    user: User = User.get(message.from_user.id)
    user_info: UserInfo = UserInfo.get(user.id)
    logging.info(f'{user} sent "{message.text}"')

    button_to_command(user.state, message)
    reply = get_reply(user.state, message.text)
    keyboard = get_markup(user.state, message.text)

    if user.state == 'register1':
        user_info.set(surname=message.text)

    elif user.state == 'register2':
        user_info.set(name=message.text)

    elif user.state == 'register3':
        if message.text != '/skip':
            user_info.set(patronymic=message.text)

    elif user.state == 'register4':
        user_info.set(email=message.text)

    elif user.state == 'register5':
        if not is_unknown_reply(user.state, message.text):
            user_info.set(job=message.text)
            user.set(cache=message.text)
            keyboard = get_markup(user.state, message.text, skip=(user.cache,))  # skip same profession

    elif user.state == 'register6':
        if is_unknown_reply(user.state, message.text):
            keyboard = get_markup(user.state, '*', skip=(user.cache,))  # skip same profession
        else:
            if message.text != '/skip' and message.text != user_info.job:  # if user decided to /skip or written same profession
                user_info.set(job=user_info.job + ';' + message.text)
            user.set(cache='')

            # !!! API ADDITION IS UNDER DISCUSSION !!!
            #
            # response = api.add_user(user)
            # if get_config()['server_error_messages'] and not response['success']:
            #     text = ''
            #     for error in response['data']:
            #         text += f"{error['path']} : {error['error']}\n"
            #     reply = get_reply('api_problems', 'user_registration')
            #     reply['extra'] = reply['extra'].replace('%error%', text)
            #     keyboard = get_markup('api_problems', 'user_registration')

    user.set(state=reply['next'])
    await send_answer(message=message, reply=reply, keyboard=keyboard)


@dp.callback_query_handler(lambda msg: filters.is_register_menu(msg))
async def register_callback(callback_query: CallbackQuery):
    """Handler for registration menu Inline buttons"""
    user: User = User.get(callback_query.from_user.id)
    logging.info(f'{user} pressed button "{callback_query.data}"')

    reply = get_reply(user.state)
    keyboard = get_markup(user.state, callback_query.data)

    if user.state == 'register3':
        if callback_query.data == '/skip':
            reply = get_reply(user.state, callback_query.data)

    user.set(state=reply['next'])
    await bot.send_message(callback_query.from_user.id, reply['message'], reply_markup=keyboard)


@dp.message_handler(lambda msg: filters.is_login_menu(msg))
async def login_menu(message: Message):
    """Handler for login menu"""
    user: User = User.get(message.from_user.id)
    logging.info(f'{user} sent "{message.text}"')

    button_to_command(user.state, message)
    keyboard = get_markup(user.state, message.text)
    reply = get_reply(user.state, message.text)

    if user.state == 'login1':
        user.set(cache=message.text)
    elif user.state == 'login2':
        # !!! API ADDITION IS UNDER DISCUSSION !!!
        #
        # response = api.login_user(user.cache, message.text)
        # if get_config()['server_error_messages'] and not response['success']:
        #     reply = get_reply('api_problems', 'user_login')
        #     keyboard = get_markup('api_problems', 'user_login')
        await bot.delete_message(message.chat.id, message.message_id)  # deletes password for user safety
        user.set(cache='')

    user.set(state=reply['next'])
    await send_answer(message=message, reply=reply, keyboard=keyboard)


@dp.message_handler(lambda msg: filters.is_edit_menu(msg))
async def edit_menu(message: Message):
    """Handler for edit menu and it's subpages"""
    user: User = User.get(message.from_user.id)
    user_info: UserInfo = UserInfo.get(user.id)
    logging.info(f'{user} sent "{message.text}"')

    button_to_command(user.state, message)
    keyboard = get_markup(user.state, message.text)
    reply = get_reply(user.state, message.text)

    if user.state == 'edit_surname':
        user_info.set(surname=message.text)
    elif user.state == 'edit_name':
        user_info.set(name=message.text)
    elif user.state == 'edit_patronymic':
        if message.text == '/skip':
            user_info.set_patronymic(patronymic=None)
        else:
            user_info.set(patronymic=message.text)
    elif user.state == 'edit_email':
        user_info.set(email=message.text)
    elif user.state == 'edit_job1':
        if not is_unknown_reply(user.state, message.text):
            user_info.set(job=message.text)
            user.set(cache=message.text)
            keyboard = get_markup(user.state, message.text, skip=(user.cache,))  # skip same profession
    elif user.state == 'edit_job2':
        if is_unknown_reply(user.state, message.text):
            keyboard = get_markup(user.state, '*', skip=(user.cache,))  # skip same profession
        else:
            if message.text != '/skip' and message.text != user_info.job:  # if user decided to /skip or written same profession
                user_info.set(job=user_info.job + ';' + message.text)
            user.set(cache='')

    fill_user_info(keyboard=keyboard, user_info=user_info)
    user.set(state=reply['next'])
    await send_answer(message=message, reply=reply, keyboard=keyboard)


@dp.callback_query_handler(lambda msg: filters.is_edit_menu(msg))
async def edit_callback(callback_query: CallbackQuery):
    """Handler for edit menu Inline buttons"""
    user: User = User.get(callback_query.from_user.id)
    user_info: UserInfo = UserInfo.get(user.id)
    logging.info(f'{user} pressed button "{callback_query.data}"')

    reply = get_reply(user.state, callback_query.data)
    keyboard = get_markup(user.state, callback_query.data)

    if user.state == 'edit_patronymic':
        if callback_query.data == '/skip':  # if user skipped patronymic
            user_info.set_patronymic(patronymic=None)

    fill_user_info(keyboard=keyboard, user_info=user_info)
    user.set(state=reply['next'])
    await bot.send_message(callback_query.from_user.id, reply['message'], reply_markup=keyboard)


@dp.message_handler(lambda msg: filters.is_faq_menu(msg))
async def faq_menu(message: Message):
    """Handler for faq menu and automatic /leave"""
    user: User = User.get(message.from_user.id)
    logging.info(f'{user} sent "{message.text}"')

    button_to_command(user.state, message)
    keyboard = get_markup(user.state, message.text)
    reply = get_reply(user.state, message.text)

    if message.text == '/leave':
        auto_next = 'registered' if user.is_registered() else 'not_registered'

        reply['message'] = [auto_next, '*']
        reply['next'] = auto_next
        reply = parse_link(reply, user.state)
        keyboard = get_markup(buttons=get_raw_button(auto_next, '#KeyboardButtons'), buttons_type='#KeyboardButtons')

    user.set(state=reply['next'])
    await send_answer(message=message, reply=reply, keyboard=keyboard)


@dp.message_handler()
async def simple_commands(message: Message):
    """Handler for ALL simple commands that do not requires any extra data"""
    user: User = User.get(message.from_user.id)
    user_info: UserInfo = UserInfo.get(user.id)
    logging.info(f'{user} sent "{message.text}" : simple command handler')

    button_to_command(user.state, message)
    keyboard = get_markup(user.state, message.text)
    reply = get_reply(user.state, message.text)

    fill_user_info(keyboard=keyboard, user_info=user_info)
    user.set(state=reply['next'])
    await send_answer(message=message, reply=reply, keyboard=keyboard)


@dp.callback_query_handler()
async def simple_callback(callback_query: CallbackQuery):
    """Handler for ALL simple callbacks (or wrong buttons) that do not requires any extra data"""
    user: User = User.get(callback_query.from_user.id)
    logging.info(f'{user} pressed button "{callback_query.data}" : simple query handler')

    keyboard = get_markup(user.state)
    reply = get_reply(user.state)

    user.set(state=reply['next'])
    await send_answer(message=callback_query, reply=reply, keyboard=keyboard)


if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=False)
