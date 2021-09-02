import datetime
import os
import logging

import dotenv
import requests

from models import User, UserInfo, Dialog, Discussion, Team, Suggestion


dotenv.load_dotenv(dotenv.find_dotenv())
SERVER = os.getenv('SERVER')
API_KEY = os.getenv('API_KEY')


def get(link: str, json: dict = None, params: dict = None):
    logging.info(f"GET {SERVER}/api/v1{link}")
    return requests.get(f"{SERVER}/api/v1{link}", params=params, json=json, headers={'Authorization': f"Bearer {API_KEY}"}).json()


def post(link: str, json: dict = None, params: dict = None):
    logging.info(f"POST {SERVER}/api/v1{link}")
    return requests.post(f"{SERVER}/api/v1{link}", params=params, json=json, headers={'Authorization': f"Bearer {API_KEY}"}).json()


def patch(link: str, json: dict = None, params: dict = None):
    logging.info(f"PATCH {SERVER}/api/v1{link}")
    return requests.patch(f"{SERVER}/api/v1{link}", params=params, json=json, headers={'Authorization': f"Bearer {API_KEY}"}).json()


def add_user(user: User, edit: bool = False) -> dict:
    user_info: UserInfo = UserInfo.get(user.id)
    json = {
        'firstName': user_info.name,
        'lastName': user_info.surname,
        'email': user_info.email,
        'professionByLabel': user_info.job.split(';'),
        'telegramId': str(user_info.user_id)
    }
    if user_info.patronymic is not None:
        json['middleName'] = user_info.patronymic
    return post("/user", json=json) if (not edit) else patch(f"/user/tg-id/{user.id}", json=json)


def login_user(login: str, password: str) -> dict:
    json = {
        'axiomId': login,
        'password': password
    }
    return get("/ЧТО-ТО", json=json)


def get_user(user: User) -> dict:
    return get(f'/user/tg-id/{user.id}')


def get_user_by_axiom_id(axiom_id: str) -> dict:
    return get(f'/user/{axiom_id}')


def add_discussion(discussion: Discussion) -> dict:
    json = {
        'topicByLabel': discussion.theme
    }
    return post(f'/user/tg-id/{discussion.user_id}/dialog', json=json)


def add_dialog(who: int, discussion_id: int, text: str, time: datetime, moderator: int = None) -> dict:
    json = {
        'text': text,
        'timestamp': int(round(time.timestamp() * 1000))

    }
    if moderator is not None:
        json['fromModerator'] = moderator
    return post(f'/user/tg-id/{who}/dialog/{discussion_id}/add-message', json=json)


def close_discussion(who: int, discussion_id: int) -> dict:
    return post(f'/user/tg-id/{who}/dialog/{discussion_id}/resolve')


def add_suggestion(suggestion: Suggestion):
    json = {
        'timestamp': int(round(suggestion.time.timestamp() * 1000)),
        'message': suggestion.text,
        'topicByLabel': suggestion.theme
    }
    return post(f'/user/tg-id/{suggestion.user_id}/feedback', json=json)


def get_competitions() -> dict:
    return get('/competitions')


def get_teams(competition_id: int) -> dict:
    json = {
        'competitionId': competition_id
    }
    return get('/teams', params=json)


def add_team(team: Team):
    params = {
        'telegramId': team.owner_id
    }
    json = {
        'name': team.title,
        'chatId': team.chat_id,
        'competitionId': team.competition_id
    }
    res = post('/team', params=params, json=json)

    return res  # TODO add chat_id

    if not res['success']:
        return res
    json = {
        'chatId': team.chat_id
    }
    return post(f'/team/{res["data"]["id"]}/assign-chat', json=json)
