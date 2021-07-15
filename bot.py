import logging
import os

import dotenv
from aiogram import Bot, Dispatcher, executor
from aiogram.types import Message

import database
import filters
from models import User
from bot_functions import get_reply


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

# Initialize database and models
database.global_init(CONNECTION_STRING)

# Initialize bot and dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)


@dp.message_handler(lambda msg: filters.user_not_in_database(msg))
async def add_user_to_database(message: Message):
    logging.info(f"New user written a message")
    User.add(message.from_user.id)
    user = User.get(message.from_user.id)

    reply = get_reply(user.state, message.text)

    user.set_state(reply['next'])
    await message.answer(reply['message'])


@dp.message_handler(lambda msg: filters.is_group_chat(msg))
async def group_chat(message: Message):
    pass


@dp.message_handler(lambda msg: filters.state_is(msg, 'register1'))
async def register1(message: Message):
    user = User.get(message.from_user.id)
    # TODO: complete /register


@dp.message_handler()
async def simple_commands(message: Message):
    user = User.get(message.from_user.id)
    logging.info(f'{user} sent "{message.text}"')

    reply = get_reply(user.state, message.text)

    user.set_state(reply['next'])
    await message.answer(reply['message'])


if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
