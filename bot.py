import logging
import os
import asyncio
from datetime import datetime, timedelta

import dotenv
from aiogram import Bot, Dispatcher, executor
from aiogram.types import Message, CallbackQuery, ContentType
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types.reply_keyboard import ReplyKeyboardRemove
from aiogram.types.chat_member_updated import ChatMemberUpdated
from aiogram.utils import markdown

import api_v1 as api
import database
import filters
from models import User, UserInfo, Discussion, Dialog, Suggestion, Team, Application, Member
from bot_functions import (get_reply, is_unknown_reply, button_to_command, get_config, has_inline_buttons,
                           has_keyboard_buttons, get_raw_button, parse_link)


# Configure logging
logging.basicConfig(
    format='%(asctime)s %(levelname)-8s %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S',
    filename=get_config()['logging_file']
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


async def send_answer(chat_id: int, reply: dict, keyboard: ReplyKeyboardRemove or InlineKeyboardMarkup or ReplyKeyboardMarkup = ReplyKeyboardRemove()):
    """Sends extra and message"""
    if reply.get('extra') is not None:
        await bot.send_message(chat_id, reply['extra'])
    await bot.send_message(chat_id, reply['message'], reply_markup=keyboard, parse_mode=reply.get('parse_mode'))


async def close_discussion_automatically(discussion_id: int):
    """Sets timer for config.json -> waiting_time seconds & closes menu if no replies was sent"""
    discussion: Discussion = Discussion.get(discussion_id)

    start_time = discussion.get_last_message().time
    await asyncio.sleep(get_config()['waiting_time'])  # sleeping
    discussion.update()  # checking if anything changed
    end_time = discussion.get_last_message().time

    if start_time == end_time and discussion.finished == False:
        discussion.set(finished=True)
        api.close_discussion(discussion.user_id, discussion.server_id)

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


async def close_poll_automatically(chat_id: int, message_id: int, edit_message_id: int, user_id: int):
    await asyncio.sleep(get_config()['poll_life_time'])  # sleeping
    res = await bot.stop_poll(chat_id, message_id)
    yes, no = res['options']

    team = Team.get(chat_id)
    reply_messages = get_reply('team_chat', 'new_member')
    team_chat_message = reply_messages['message3_accepted'] if yes['voter_count'] > no['voter_count'] else reply_messages['message3_denied']
    user_chat_message = reply_messages['user_accepted'] if yes['voter_count'] > no['voter_count'] else reply_messages['user_denied']
    user_chat_message = user_chat_message.replace('%title%', team.title)
    user_chat_message = user_chat_message.replace('%link%', (await bot.create_chat_invite_link(chat_id, member_limit=1))['invite_link'])

    await bot.edit_message_text(team_chat_message, chat_id, edit_message_id)
    await bot.send_message(user_id, user_chat_message)


def send_error_message(reply: dict, keyboard: InlineKeyboardMarkup or ReplyKeyboardMarkup or ReplyKeyboardRemove, response: dict, problem: str) -> (dict, InlineKeyboardMarkup or ReplyKeyboardMarkup or ReplyKeyboardRemove):
    if get_config()['server_error_messages'] and (not response['success']):
        text = ''
        if response['data'] is not None:
            for error in response['data']:
                text += f"{error['path']} : {error['error']}\n"
        if (response.get('error') is not None) and (response['error'].get('message') is not None):
            text += "Server message: " + response['error']['message']
        reply = get_reply('api_problems', problem)
        reply['extra'] = reply['extra'].replace('%error%', text)
        keyboard = get_markup('api_problems', problem)
    return reply, keyboard


@dp.message_handler(content_types=["migrate_to_chat_id"])
async def group_upgrade_to(message: Message):  # when group migrate from group to supergroup
    team: Team = Team.get(message.chat.id)
    if team is not None:
        team.set(chat_id=message.migrate_to_chat_id)


@dp.message_handler(lambda msg: filters.is_group_chat(msg), commands=['get_chat_id'])
async def send_chat_id(message: Message):
    """Special handler for group chat, that helps getting chat_id for config chat"""
    await message.reply(f"id этого чата:\n{message.chat.id}")


@dp.message_handler(lambda msg: filters.is_group_chat(msg))
async def group_chat(message: Message):
    """Group chat handler (works only in moderator_chat)"""

    if message.chat.id == get_config()['moderator_chat']:  # bot can only read MODERATOR chat
        if message.reply_to_message is None:  # only read replies
            return
        bot_message_id = message.reply_to_message.message_id
        question: Dialog = Dialog.get_question(bot_message_id)
        if question is None:  # if it's not random reply
            return
        discussion = Discussion.get(question.discussion_id)

        Dialog.add(question.discussion_id, message.text, message.from_user.id, message.message_id, bot_message_id, question.server_id, moderator=True)
        moderator_chat_message: str = get_reply('moderator_chat', '#WAITING')['moderator_chat_message']
        moderator_chat_message = moderator_chat_message.replace('%theme%', discussion.theme)
        moderator_chat_message = moderator_chat_message.replace('%id%', str(discussion.id))
        moderator_chat_message = moderator_chat_message.replace('%text%', question.text)

        user_chat_message: str = get_reply('moderator_chat', '#WAITING')['user_chat_message']
        user_chat_message = user_chat_message.replace('%theme%', discussion.theme)
        user_chat_message = user_chat_message.replace('%id%', str(discussion.id))
        user_chat_message = user_chat_message.replace('%text%', message.text)

        await bot.send_message(question.who, user_chat_message, reply_to_message_id=question.message_id)
        api.add_dialog(question.who, question.server_id, message.text, datetime.now(), message.from_user.id)

        if (message.reply_to_message.text != moderator_chat_message) and (not discussion.finished):  # if messages are not the same AND discussion not finished
            await bot.edit_message_text(moderator_chat_message, get_config()['moderator_chat'], question.bot_message_id)

        asyncio.get_event_loop().create_task(close_discussion_automatically(discussion.id))  # starts delete timer in another thread

    elif (message.chat.id,) in Team.get_all_chats():
        team: Team = Team.get(message.chat.id)
        if team.owner_id != message.from_user.id:  # only owner can change group info
            return
        chat = await bot.get_chat(message.chat.id)
        commands = get_reply('team_chat', 'commands')
        if message.text.startswith(commands['change_title']):
            team.set(title=message.text[len(commands['change_title']) + 1:])
            await chat.set_title(message.text[len(commands['change_title']) + 1:])
            await message.reply(commands['change_title_message'])

        elif message.text.startswith(commands['change_description']):
            team.set(description=message.text[len(commands['change_description']) + 1:])
            await chat.set_description(message.text[len(commands['change_description']) + 1:])
            await message.reply(commands['change_description_message'])

        elif message.text.startswith(commands['invite']):
            axiom_id = message.text[len(commands['invite']) + 1:]

            res = api.get_user_by_axiom_id(axiom_id)
            if not res['success']:
                chat_message = chat['user_invitation_invalid_id']
                chat_message = chat_message.replace('%axiom_id%', axiom_id)
                await message.reply(chat_message)
                return

            # TODO check
            user_id = int(res['data']['telegramId'])

            user_message: str = commands['user_invitation']
            user_message = user_message.replace('%title%', team.title)
            user_message = user_message.replace('%link%', (await bot.create_chat_invite_link(message.chat.id, member_limit=1))['invite_link'])

            await message.reply(commands['invite_message'])
            await bot.send_message(user_id, user_message)


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
    await send_answer(chat_id=message.chat.id, reply=reply, keyboard=keyboard)


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

            response = api.add_discussion(discussion)
            if not response['success']:
                reply, keyboard = send_error_message(reply, keyboard, response, 'add_discussion')
                discussion.delete()
            else:
                discussion.set(server_id=response['data']['dialogId'])

    elif user.state == 'question2':
        discussion = Discussion.get(int(user.cache))
        moderator_chat_message: str = get_reply('moderator_chat', '#OPEN')['moderator_chat_message']
        moderator_chat_message = moderator_chat_message.replace('%theme%', discussion.theme)
        moderator_chat_message = moderator_chat_message.replace('%id%', str(discussion.id))
        moderator_chat_message = moderator_chat_message.replace('%text%', message.text)
        bot_message = await bot.send_message(get_config()['moderator_chat'], moderator_chat_message)
        Dialog.add(discussion.id, message.text, message.from_user.id, message.message_id, bot_message.message_id, discussion.server_id, moderator=False)
        api.add_dialog(message.from_user.id, discussion.server_id, message.text, datetime.now())

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
            api.close_discussion(discussion.user_id, discussion.server_id)
            user.set(cache="")

            logging.info(f'Closing all questions in moderator_chat about {discussion}')
            for question in discussion.get_questions():
                moderator_chat_message: str = get_reply('moderator_chat', '#CLOSED')['moderator_chat_message']
                moderator_chat_message = moderator_chat_message.replace('%theme%', discussion.theme)
                moderator_chat_message = moderator_chat_message.replace('%id%', str(discussion.id))
                moderator_chat_message = moderator_chat_message.replace('%text%', question.text)

                await bot.edit_message_text(moderator_chat_message, get_config()['moderator_chat'], question.bot_message_id)

    user.set(state=reply['next'])
    await send_answer(chat_id=message.chat.id, reply=reply, keyboard=keyboard)


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
    await send_answer(chat_id=callback_query.from_user.id, reply=reply, keyboard=keyboard)


@dp.message_handler(lambda msg: filters.is_join_menu(msg))
async def join_menu(message: Message):
    """Handler for join menu and it's subpages"""
    user: User = User.get(message.from_user.id)
    logging.info(f'{user} sent "{message.text}"')

    button_to_command(user.state, message)
    reply = get_reply(user.state, message.text)
    keyboard = get_markup(user.state, message.text)

    if user.state == 'join' or user.state == 'join_competitions':
        if reply['next'] != 'join':
            keyboard = InlineKeyboardMarkup()
            for competition in api.get_competitions()['data']:  # Adds [name] buttons
                keyboard.add(InlineKeyboardButton(competition['name'], callback_data=f"{competition['id']}"))
            for button in get_reply(user.state, message.text, inline_buttons=True):  # Adds /cancel button
                keyboard.add(InlineKeyboardButton(button['text'], callback_data=button['command']))
    elif user.state == 'join_team':
        keyboard = InlineKeyboardMarkup()
        for team in api.get_teams(competition_id=int(user.cache))['data']:  # Adds [name] buttons
            application = Application.get(user.id, team['chatId'])
            team_ = Team.get(team['chatId'])
            if ((application is None) or (application.accepted is not None) and application.accepted) and ((team_ is None) or (not team_.user_in_team(user.id))):
                keyboard.add(InlineKeyboardButton(team['name'], callback_data=team['chatId']))
        for button in get_reply(user.state, message.text, inline_buttons=True):  # Adds /cancel button
            keyboard.add(InlineKeyboardButton(button['text'], callback_data=button['command']))

    user.set(state=reply['next'])
    await send_answer(chat_id=message.chat.id, reply=reply, keyboard=keyboard)


@dp.callback_query_handler(lambda msg: filters.is_join_menu(msg))
async def join_menu_callback(callback_query: CallbackQuery):
    """Handler for join menu and it's subpages Inline buttons"""
    user: User = User.get(callback_query.from_user.id)
    logging.info(f'{user} pressed button "{callback_query.data}"')

    reply = get_reply(user.state)
    keyboard = get_markup(user.state, callback_query.data)

    if user.state == 'join_competitions':
        if callback_query.data == '/leave':
            reply = get_reply(user.state, callback_query.data)
        elif callback_query.data.lstrip('-').isdigit():  # if correct competition_id
            user.set(cache=callback_query.data)
            reply = get_reply(user.state, callback=True)

            keyboard = InlineKeyboardMarkup()
            for team in api.get_teams(competition_id=int(user.cache))['data']:  # Adds [name] buttons
                application = Application.get(user.id, team['chatId'])
                team_ = Team.get(team['chatId'])
                if ((application is None) or (application.accepted is not None) and application.accepted) and ((team_ is None) or (not team_.user_in_team(user.id))):
                    keyboard.add(InlineKeyboardButton(team['name'], callback_data=team['chatId']))
            for button in get_reply(user.state, '*', inline_buttons=True):  # Adds /cancel button
                keyboard.add(InlineKeyboardButton(button['text'], callback_data=button['command']))

    elif user.state == 'join_team':
        if callback_query.data == '/leave':
            reply = get_reply(user.state, callback_query.data)
        elif callback_query.data.lstrip('-').isdigit():  # if correct team_id
            team = Team.get(int(callback_query.data))

            application = Application.get(user.id, team.chat_id)
            if (application is not None) and (not application.accepted):
                reply['message'] = get_reply('team_chat', 'new_member')['user_done']
                reply['next'] = user.state
            else:
                reply = get_reply(user.state, callback=True)
                reply['extra'] = reply['extra'].replace('%title%', team.title)
                keyboard = InlineKeyboardMarkup()
                for team in api.get_teams(competition_id=int(user.cache))['data']:  # Adds [name] buttons
                    application = Application.get(user.id, team['chatId'])
                    team_ = Team.get(team['chatId'])
                    if ((application is None) or (application.accepted is not None) and application.accepted) and ((team_ is None) or (not team_.user_in_team(user.id))):
                        keyboard.add(InlineKeyboardButton(team['name'], callback_data=team['chatId']))
                for button in get_reply(user.state, '*', inline_buttons=True):  # Adds /cancel button
                    keyboard.add(InlineKeyboardButton(button['text'], callback_data=button['command']))

                user_info = api.get_user(user)['data']
                reply_messages = get_reply('team_chat', 'new_member')
                team: Team = Team.get(int(callback_query.data))
                team_chat_message = reply_messages['message1']
                team_chat_message = team_chat_message.replace('%job%', ' & '.join(user_info['profession']))
                team_chat_message = team_chat_message.replace('%AXIOM_ID%', user_info['axiomId'])
                team_chat_message = team_chat_message.replace('<', '[[')  # to block all user_html inputs
                team_chat_message = team_chat_message.replace('>', ']]')  # to block all user_html inputs
                team_chat_message = team_chat_message.replace('%user_id%', f'<a href="tg://user?id={user.id}">{user_info["firstName"]} {user_info["lastName"]}</a>')  # in case when user has no @alias, we are notifying them
                await bot.send_message(team.chat_id, team_chat_message, parse_mode='HTML')  # html to parse %user_id%

                poll = await bot.send_poll(team.chat_id, question=reply_messages['message2_title'], options=['Да', 'Нет'], is_anonymous=False)

                team_chat_message = reply_messages['message3_waiting']
                team_chat_message = team_chat_message.replace('%time%', str((datetime.now() + timedelta(seconds=get_config()['poll_life_time'])).strftime('%m/%d/%Y, %H:%M:%S')))
                edit_message = await bot.send_message(team.chat_id, team_chat_message)

                Application.add(team.chat_id, user.id, poll.message_id)
                asyncio.get_event_loop().create_task(close_poll_automatically(poll.chat.id, poll.message_id, edit_message.message_id, user.id))  # starts delete timer in another thread

    user.set(state=reply['next'])
    await send_answer(chat_id=callback_query.from_user.id, reply=reply, keyboard=keyboard)


@dp.message_handler(lambda msg: filters.is_create_menu(msg))
async def create_menu(message: Message):
    """Handler for create menu and it's subpages"""
    user: User = User.get(message.from_user.id)
    logging.info(f'{user} sent "{message.text}"')

    button_to_command(user.state, message)
    reply = get_reply(user.state, message.text)
    keyboard = get_markup(user.state, message.text)

    if user.state == 'create_competitions':
        keyboard = InlineKeyboardMarkup()
        for competition in api.get_competitions()['data']:  # Adds [name] buttons
            keyboard.add(InlineKeyboardButton(competition['name'], callback_data=f"{competition['id']}"))
        for button in get_reply(user.state, message.text, inline_buttons=True):  # Adds /cancel button
            keyboard.add(InlineKeyboardButton(button['text'], callback_data=button['command']))

    elif user.state == 'create_team1':
        if message.text == '/next':
            teams = Team.get_all_user_chats(user.id)
            if (len(teams) == 0) or (teams[-1].title is not None):
                reply['message'] = get_reply(user.state, '#Template', safe=False)['fail_no_group']
                reply['next'] = user.state
                keyboard = get_markup(user.state, '*')
            else:
                required_rights = list(get_config()['bot_admin_access'])
                rights = list(filter(lambda a: a[1], map(list, (await bot.get_chat_member(teams[-1].chat_id, BOT_TOKEN)))))[1:]
                if rights != required_rights:
                    reply['message'] = get_reply(user.state, '#Template', safe=False)['fail_no_rights']
                    rights_str = ""
                    for right in required_rights:
                        rights_str += f"{right[0]} : {right[1]}\n"
                    reply['message'] = reply['message'].replace('%rights%', markdown.code(rights_str))
                    reply['next'] = user.state
                    reply['parse_mode'] = 'MarkdownV2'
                    keyboard = get_markup(user.state, '*')
                else:
                    reply['message'] = get_reply(user.state, '#Template', safe=False)['success']
                    reply['next'] = get_reply(user.state, '#Template', safe=False)['success_next']

    elif user.state == 'create_team2':
        team: Team = Team.get_current_user_chats(user.id)
        team.set(title=message.text)
        chat = await bot.get_chat(team.chat_id)
        await chat.set_title(message.text)

    elif user.state == 'create_team3':
        team: Team = Team.get_current_user_chats(user.id)
        team.set(description=message.text)
        chat = await bot.get_chat(team.chat_id)
        await chat.set_description(message.text)
        Member.add(team.chat_id, user.id)

        response = api.add_team(team)
        reply, keyboard = send_error_message(reply, keyboard, response, 'add_team')

    user.set(state=reply['next'])
    await send_answer(chat_id=message.chat.id, reply=reply, keyboard=keyboard)


@dp.callback_query_handler(lambda msg: filters.is_create_menu(msg))
async def create_menu_callback(callback_query: CallbackQuery):
    """Handler for create menu and it's subpages Inline buttons"""
    user: User = User.get(callback_query.from_user.id)
    logging.info(f'{user} pressed button "{callback_query.data}"')

    reply = get_reply(user.state)
    keyboard = get_markup(user.state, callback_query.data)

    if user.state == 'create_competitions':
        if callback_query.data == '/cancel':
            reply = get_reply(user.state, callback_query.data)
        elif callback_query.data.lstrip('-').isdigit():  # if correct competition_id
            user.set(cache=callback_query.data)
            reply = get_reply(user.state, callback=True)
            keyboard = get_markup(user.state, '#', safe=False)

    user.set(state=reply['next'])
    await send_answer(chat_id=callback_query.from_user.id, reply=reply, keyboard=keyboard)


@dp.my_chat_member_handler()
async def team_new_member(member: ChatMemberUpdated):
    user = User.get(member.from_user.id)
    if member.old_chat_member.status == 'left' and member.new_chat_member.status == 'member':

        team: Team = Team.get_current_user_chats(user.id)
        if member.new_chat_member.user.id == bot.id and user.state == 'create_team1' and team is None:
            Team.add(member.chat.id, user.id, int(user.cache))
            return

        application: Application = Application.get(user.id, member.chat.id)
        if (member.new_chat_member.user.id != user.state) and (application is not None) and (application.accepted is None):
            application.set(accepted=True)
            Member.add(chat_id=member.chat.id, user_id=user.id)


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
        api.add_suggestion(suggestion)
        user.set(cache='')

    user.set(state=reply['next'])
    await send_answer(chat_id=message.chat.id, reply=reply, keyboard=keyboard)


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
            response = api.add_user(user)

            reply, keyboard = send_error_message(reply, keyboard, response, 'user_registration')

    user.set(state=reply['next'])
    await send_answer(chat_id=message.chat.id, reply=reply, keyboard=keyboard)


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
    await send_answer(chat_id=message.chat.id, reply=reply, keyboard=keyboard)


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
        api.add_user(user, edit=True)
    elif user.state == 'edit_name':
        user_info.set(name=message.text)
        api.add_user(user, edit=True)
    elif user.state == 'edit_patronymic':
        if message.text == '/skip':
            user_info.set_patronymic(patronymic=None)
        else:
            user_info.set(patronymic=message.text)
        api.add_user(user, edit=True)
    elif user.state == 'edit_email':
        prev = user_info.email
        user_info.set(email=message.text)
        response = api.add_user(user, edit=True)
        if not response['success']:
            reply, keyboard = send_error_message(reply, keyboard, response, 'edit_info')
            user_info.set(email=prev)
    elif user.state == 'edit_job1':
        if not is_unknown_reply(user.state, message.text):
            user.set(cache=message.text)
            keyboard = get_markup(user.state, message.text, skip=(user.cache,))  # skip same profession
    elif user.state == 'edit_job2':
        prev = user_info.job
        if is_unknown_reply(user.state, message.text):
            user_info.set(job=user.cache)
            keyboard = get_markup(user.state, '*', skip=(user.cache,))  # skip same profession
        else:
            if message.text != '/skip' and message.text != user_info.job:  # if user decided to /skip or written same profession
                user_info.set(job=user_info.job + ';' + message.text)
            user.set(cache='')
        response = api.add_user(user, edit=True)
        if not response['success']:
            reply, keyboard = send_error_message(reply, keyboard, response, 'edit_info')
            user_info.set(job=prev)

    fill_user_info(keyboard=keyboard, user_info=user_info)
    user.set(state=reply['next'])
    await send_answer(chat_id=message.chat.id, reply=reply, keyboard=keyboard)


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
    await send_answer(chat_id=message.chat.id, reply=reply, keyboard=keyboard)


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
    await send_answer(chat_id=message.chat.id, reply=reply, keyboard=keyboard)


@dp.callback_query_handler()
async def simple_callback(callback_query: CallbackQuery):
    """Handler for ALL simple callbacks (or wrong buttons) that do not requires any extra data"""
    user: User = User.get(callback_query.from_user.id)
    logging.info(f'{user} pressed button "{callback_query.data}" : simple query handler')

    keyboard = get_markup(user.state)
    reply = get_reply(user.state)

    user.set(state=reply['next'])
    await send_answer(chat_id=callback_query.from_user.id, reply=reply, keyboard=keyboard)


if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=False)
