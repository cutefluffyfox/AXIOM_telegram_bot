# AXIOM_telegram_bot
Telegram bot for AXIOM platform


## Getting started
In order for bot to work you need to create environment variables:
```.env
BOT_TOKEN=0000000000:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
CONNECTION_STRING=mysql://Login:Password@Host/DatabaseName
```
``BOT_TOKEN`` is token toy get from @BotFather in telegram<br>
``CONNECTION_STRING`` is string to connect to your database<br>


You can make ``.env`` file, copy and paste there block above, or set variable by hand through console
<br>
<br>
<br>
After you done it. You will need to download all needed libraries:
```bash
pip install requirements.txt -r
```


## Bot reply mechanics
``answers.json`` is main file where all bot replies are. You can
change phrases in this file and bot will automatically use them (no reboot needed).
To add new phrase and state you must obey file-format:
```json
{
    "STATE_WHICH_BOT_START": {
        "#": {
            "message": "YOUR_BOT_CALLBACK_ANSWER",
            "next": "NEXT_STATE"
        },
        "MESSAGE_FROM_USER": {
            "message": "YOUR_BOT_ANSWER",
            "next": "NEXT_STATE"
        },
        "*": {
            "message": "BOT_ANSWER_IF_MESSAGE_IS_UNKNOWN",
            "next": "NEXT_STATE_IF_MESSAGE_IF_UNKNOWN"
        }
    }
}
```
``*`` in this case means unknown message (**obligatory** to be in every state)<br>
``#`` in this case means callback message handler (this message is restricted in bot)


