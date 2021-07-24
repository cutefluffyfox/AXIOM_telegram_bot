import os

import dotenv
import requests

from models import User, UserInfo


dotenv.load_dotenv(dotenv.find_dotenv())
SERVER = os.getenv('SERVER')


def add_user(user: User) -> dict:
    user_info: UserInfo = UserInfo.get(user.id)
    json = {
        'firstName': user_info.name,
        'lastName': user_info.surname,
        'email': user_info.email,
        'profession': user_info.job.split(';'),
        'telegramId': user_info.user_id
    }
    if user_info.patronymic is not None:
        json['middleName'] = user_info.patronymic
    return requests.post(f"{SERVER}/api/v1/user", json=json).json()


def login_user(login: str, password: str) -> dict:
    json = {
        'axiomId': login,
        'password': password
    }
    return requests.get(f"{SERVER}/api/v1/ЧТО-ТО", json=json).json()
