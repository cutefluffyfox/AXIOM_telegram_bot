# AXIOM_telegram_bot
Telegram bot for AXIOM platform


## Getting started
In order for bot to work you need to create environment variables:
```.env
BOT_TOKEN=0000000000:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
CONNECTION_STRING=mysql://Login:Password@Host/DatabaseName
SERVER=http://HOST:PORT
```
``BOT_TOKEN`` is token toy get from @BotFather in telegram<br>
``CONNECTION_STRING`` is string to connect to your database<br>
``SERVER`` is string to server<br>


You can make ``.env`` file, copy and paste there block above, or set variable by hand through console<br>
<br>
After you set up your environment variables, you will need to download all needed libraries:
```bash
pip install -r requirements.txt
```


## Bot reply mechanics
``answers.json`` is main file where all bot replies are. You can
change phrases in this file and bot will automatically use them (no reboot needed).
To add new phrase and state you must obey file-format:
```json
{
    "CURRENT_STATE": {
        "#": {
            "message": "BOT_InlineButton_ANSWER",
            "next": "NEXT_STATE"
        },
        "/command1": {
            "extra": "This message will be send before 'message'",
            "message": "BOT_ANSWER and %variable%",
            "next": "NEXT_STATE_1"
        },
        "/command2": {
            "message": "BOT_ANSWER",
            "next": "NEXT_STATE_2"
        },
        "*": {
            "message": "BOT_ANSWER_IF_MESSAGE_IS_UNKNOWN",
            "next": "NEXT_STATE_IF_MESSAGE_IF_UNKNOWN"
        },
        "#InlineButtons": [
            {
              "text": "Text on button 1",
              "command": "/command"
            },
            {
              "text": "Text on button 2",
              "command": "/command2"
            }
        ]
    },
    "*": {
        "*": {
            "message": "Something went wrong",
            "next": "/start"
        }
    }
}
```
Base:<br>
``*`` in this case means unknown message <span style="color:#DD7777">(**MUST** to be in every state)</span><br>
``message`` is message that bot will send to user <span style="color:#DD7777">(**MUST** to be in every command)</span><br>
``next`` is next user state <span style="color:#DD7777">(**MUST** to be in every command)</span><br>

Additional:<br>
``extra`` is message that bot will send to user **BEFORE** ``message``<br>
``#`` in this case means answer to InlineButton (when buttons is unknown)<br>
``%variable%`` is variable that bot will automatically change<br>
``#InlineButtons`` and ``#KeyboardButtons`` are lists of buttons (text is text on button, command is what command this button suppose to replace) <br> 
``moderator_chat`` is a special state which contains bot message templates for moderator_chat<br>
``api_problems`` is a special state which contains bot message templates for api error messages<br>

Useful stuff:<br>
``message`` and ``extra`` can have not a string with message, but list with link to another message.
Links have two types:
- link to another state ``"message": ["STATE_TO", "COMMAND"]``
- link to message template ``"message": ["#Template", "TEMPLATE_MESSAGE"]``
```json
{
    "CURRENT_STATE": {
        "#Template": {
            "success": "success_message",
            "bad": "bad_message"
        },
        "/done": {
            "message": ["#Template", "success"],
            "next": "NEXT_STATE"
        },
        "/complete": {
            "message": ["#Template", "success"],
            "next": "NEXT_STATE"
        },
        "/error": {
            "message": ["#Template", "bad"],
            "next": "NEXT_STATE"
        },
        "/leave": {
            "message": ["OTHER_STATE", "/help"],
            "next": "NEXT_STATE"
        },
        "*": {
            "message": "Idk what to write here",
            "next": "CURRENT_STATE"
      }
    },
    "OTHER_STATE": {
        "/help": {
            "message": "Please send /help to me",
            "next": "OTHER_STATE"
        },
        "*": {
            "message": "It's hard to make examples :(",
            "next": "OTHER_STATE"
        }
    }
}
```


## Bot configuration file
``config.json`` is file for all bot variables, here is a list what 
each variable mean:
- ``waiting_time`` is amount of second when question will automatically close
- ``moderator_chat`` is moderator chat id
- ``admin_chat`` is admin chat id (can be same as ``moderator_chat``)
- ``suggestions_limit`` is a print limit for user suggestions
- ``restricted_messages`` messages that bot will replace to * (unknown state)
- ``server_error_messages`` if false, bot will ignore api replies

