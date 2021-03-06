# -*- coding: utf-8 -*-
#!/usr/bin/env python3
from __future__ import unicode_literals

import telegram
from telegram.ext import Updater, CommandHandler, ConversationHandler, MessageHandler, Filters
from telegram.error import TelegramError
import logging

import os
import sys
from threading import Thread
import shutil
import pickle
import datetime
from collections import defaultdict

from functools import wraps

with open("api_key.txt", 'r') as f:
    TOKEN = f.read().rstrip()

# Format is mmddyyyy and then additional letters if I need a hotfix.
PATCHNUMBER = "04262020"

ADMIN = [539621524]

"""
Contains:

amas - Key is telegram_id, value is list of (telegram_id, question) tuples.
users - A list of (telegram_id, name) tuples.
patches - A list of strings representing the patch history.
reply_history - A list of replies in (asker_id, question_text, person_who_made_ama_id, text) tuples.
"""
ama_database = pickle.load(open("./amadatabase", "rb")) if os.path.isfile("./amadatabase") else {}

def send_message(bot, chat_id, text, photo=None):
    try:
        bot.send_message(chat_id=chat_id, text=text, parse_mode=telegram.ParseMode.HTML)
        if photo is not None:
            bot.send_photo(chat_id=chat_id, photo=photo, parse_mode=telegram.ParseMode.HTML)
    except TelegramError as e:
        raise e


def static_handler(command):
    text = open("static_responses/{}.txt".format(command), "r").read()
    return CommandHandler(command,
        lambda bot, update: send_message(bot, update.message.chat.id, text))


def restricted(func):
    @wraps(func)
    def wrapped(update, context, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in ADMIN:
            print("Unauthorized access denied for {}.".format(user_id))
            return
        return func(update, context, *args, **kwargs)
    return wrapped


def send_patchnotes(bot):
    path = "./static_responses/patchnotes_" + PATCHNUMBER + ".txt"

    if PATCHNUMBER in ama_database["patches"] or not os.path.isfile(path):
        return

    text = open(path, "r").read()

    for (telegram_id, name) in ama_database["users"]:
        send_message(bot, telegram_id, text)

    ama_database["patches"].append(PATCHNUMBER)


def get_username(user):
    username = ""
    if user.username is not None:
        username = user.username
        if user.first_name is not None:
            username += " (" + user.first_name
        if user.last_name is not None:
            username += " " + user.last_name + ")"
        else:
            username += ")"
    else:
        if user.first_name is not None:
            username += user.first_name
        if user.last_name is not None:
            username += " " + user.last_name
    return username


def confirm_ama_handler(bot, update, user_data):
    chat_id = update.message.chat.id
    user = update.message.from_user

    if user_data.get("current_ama_id_and_text") is None:
        send_message(bot, chat_id, "No pending confirmation found!")
        return

    user_id, text = user_data["current_ama_id_and_text"]

    if user_id < 0 or user_id >= len(ama_database["users"]):
        send_message(bot, chat_id, "That (%s) is not a valid ID in the range [%s, %s)!" %
                     (user_id, 0, len(ama_database["users"])))
        return

    telegram_id = ama_database["users"][user_id][0]

    if telegram_id == user.id:
        send_message(bot, chat_id, "You can't ask yourself a question!")
        return

    ama_database["amas"][telegram_id].append((user.id, text))

    new_question_id = len(ama_database["amas"][telegram_id]) - 1
    send_message(bot, chat_id, "Your question has been asked!")
    send_message(bot, telegram_id, "You have a new question (%s): %s" % (new_question_id, text))
    send_message(bot, telegram_id, "You can reply to the sender with /reply %s {text}." % new_question_id)

    user_data["current_ama_id_and_text"] = None


def ama_handler(bot, update, user_data, args):
    chat_id = update.message.chat.id
    user = update.message.from_user

    if len(args) < 2:
        send_message(bot, chat_id, "Usage: /ama {ID from /users or name} {text}")
        return

    text = " ".join(args[1:])

    try:
        user_id = int(args[0])
    except ValueError:
        user_id = -1
        name = str(args[0])
        official_name = ""
        for i, tup in enumerate(ama_database["users"]):
            if name.lower() in tup[1].lower():
                user_id = i
                official_name = tup[1]
                break
        if user_id == -1:
            send_message(bot, chat_id, "Error: Could not find a matching name!")
            return
        if user_id != -1:
            user_data["current_ama_id_and_text"] = (user_id, text)
            send_message(bot, chat_id, "Are you sure you want to ask %s this question? If so, use /confirmama." % official_name)
            return

    if user_id < 0 or user_id >= len(ama_database["users"]):
        send_message(bot, chat_id, "That (%s) is not a valid ID in the range [%s, %s)!" %
                     (user_id, 0, len(ama_database["users"])))
        return

    telegram_id = ama_database["users"][user_id][0]

    if telegram_id == user.id:
        send_message(bot, chat_id, "You can't ask yourself a question!")
        return

    ama_database["amas"][telegram_id].append((user.id, text))

    new_question_id = len(ama_database["amas"][telegram_id]) - 1
    send_message(bot, chat_id, "Your question has been asked!")
    send_message(bot, telegram_id, "You have a new question (%s): %s\n\n"
                          "You can reply to the sender with /reply %s {text}." %
                 (new_question_id, text, new_question_id))


def users_handler(bot, update):
    chat_id = update.message.chat.id

    text = "Users:\n\n"
    for i, tup in enumerate(ama_database["users"]):
        text += "(%s): %s\n" % (i, tup[1])
    send_message(bot, chat_id, text)


def display_handler(bot, update, args):
    chat_id = update.message.chat.id
    user = update.message.from_user

    if len(args) < 1:
        username = ""
        for (id, name) in ama_database["users"]:
            if id == user.id:
                username = name
                break

        if username == "":
            send_message(bot, chat_id, "You haven't made an AMA by joining using /am!")
            return

        text = "<b>AMA for %s:</b>\n\n" % username
        count = 0
        for telegram_id, question in ama_database["amas"][user.id]:
            text += "(%s) %s\n\n" % (count, question)
            count += 1
        send_message(bot, chat_id, text)
        return

    if len(args) > 1:
        send_message(bot, chat_id, "Usage: /display {ID from /users or name}")
        return

    try:
        user_id = int(args[0])
    except ValueError:
        user_id = -1
        name = " ".join(args)
        for i, tup in enumerate(ama_database["users"]):
            if name.lower() in tup[1].lower():
                user_id = i
                break
        if user_id == -1:
            send_message(bot, chat_id, "Error: Could not find a matching name!")
            return

    if user_id < 0 or user_id >= len(ama_database["users"]):
        send_message(bot, chat_id, "That (%s) is not a valid ID in the range [%s, %s)!" %
                     (user_id, 0, len(ama_database["users"])))
        return

    text = "<b>AMA for %s:</b>\n\n" % ama_database["users"][user_id][1]
    count = 0
    for telegram_id, question in ama_database["amas"][ama_database["users"][user_id][0]]:
        text += "(%s) %s\n\n" % (count, question)
        count += 1
    send_message(bot, chat_id, text)


def add_me_handler(bot, update, args):
    chat_id = update.message.chat.id
    user = update.message.from_user

    if len(args) == 0:
        username = get_username(user)
    else:
        username = " ".join(args)

    for id, name in ama_database["users"]:
        if id == user.id:
            send_message(bot, chat_id, "You're already in the database!")
            return

    ama_database["users"].append((user.id, username))
    # Sort by name
    ama_database["users"] = sorted(ama_database["users"], key=lambda x: str(x[1]).lower())

    send_message(bot, chat_id, "You've been added! Make sure to DM the bot with /start to be able to get messages!")


def remove_me_confirmed_handler(bot, update):
    chat_id = update.message.chat.id
    user = update.message.from_user

    for id, name in ama_database["users"]:
        if id == user.id:
            ama_database["users"].remove((id, name))
            break

    for id in ama_database["amas"].keys():
        if id == user.id:
            del ama_database["amas"][user.id]
            break

    send_message(bot, chat_id, "You've been removed!")


def remove_me_handler(bot, update):
    chat_id = update.message.chat.id
    user = update.message.from_user

    if user.id not in [t[0] for t in ama_database["users"]]:
        send_message(bot, chat_id, "You haven't made an AMA by joining using /am!")
        return

    send_message(bot, chat_id, "Are you sure you want to leave? If so, use /rmc.")


def reply_handler(bot, update, args):
    chat_id = update.effective_chat.id
    user = update.effective_message.from_user

    try:
        photo = update.effective_message.photo[-1]
    except Exception as e:
        photo = None

    if user.id not in [t[0] for t in ama_database["users"]]:
        send_message(bot, chat_id, "You haven't made an AMA by joining using /am!")
        return

    if len(args) < 2:
        send_message(bot, chat_id, "Usage: /reply {question ID} {text}")
        return

    text = " ".join(args[1:])

    try:
        question_id = int(args[0])
    except ValueError:
        send_message(bot, chat_id, "That (%s) was not a valid question ID." % args[0])
        return

    if question_id < 0 or question_id >= len(ama_database["amas"][user.id]):
        send_message(bot, chat_id, "That (%s) is not a valid question ID in the range [%s, %s)!" %
                     (question_id, 0, len(ama_database["amas"][user.id])))
        return

    telegram_id, question_text = ama_database["amas"][user.id][question_id]

    username = ""
    for id, name in ama_database["users"]:
        if user.id == id:
            username = name
            break

    ama_database["reply_history"].append((telegram_id, ama_database["amas"][user.id][question_id][1], user.id, text))

    send_message(bot, chat_id, "%s just replied to the question (%s): %s" % (username, question_id, question_text))
    send_message(bot, telegram_id, "You asked the following question on the AMA for %s: "
                                   "%s\n\nHere is their reply: %s" % (username, question_text, text), photo=photo)
    send_message(bot, user.id, "Your reply has been sent!")


def clear_handler(bot, update, args):
    chat_id = update.message.chat.id
    user = update.message.from_user

    if user.id not in [t[0] for t in ama_database["users"]]:
        send_message(bot, chat_id, "You haven't made an AMA by joining using /am!")
        return

    if len(args) == 0:
        ama_database["amas"][user.id] = []
        send_message(bot, chat_id, "Your AMA has been cleared!")
        return

    try:
        question_id = int(args[0])
    except ValueError:
        send_message(bot, chat_id, "That (%s) was not a valid question ID." % args[0])
        return

    if question_id < 0 or question_id >= len(ama_database["amas"][user.id]):
        send_message(bot, chat_id, "That (%s) is not a valid question ID in the range [%s, %s)!" %
                     (question_id, 0, len(ama_database["amas"][user.id])))
        return

    ama_database["amas"][user.id] = ama_database["amas"][user.id][:question_id] + ama_database["amas"][user.id][question_id + 1:]
    send_message(bot, chat_id, "Question (%s) has been removed from your AMA!" % question_id)


def mass_ama_handler(bot, update, args):
    chat_id = update.message.chat.id
    user = update.message.from_user

    if len(args) < 1:
        send_message(bot, chat_id, "Usage: /massama {text}")
        return

    text = " ".join(args)

    for id, name in ama_database["users"]:
        if id != user.id:
            ama_database["amas"][id].append((user.id, text))

            new_question_id = len(ama_database["amas"][id]) - 1
            send_message(bot, id, "You have a new question (%s): %s\n\n"
                                  "You can reply to the sender with /reply %s {text}." %
                                  (new_question_id, text, new_question_id))
    send_message(bot, chat_id, "Your question has been asked!")


def feedback_handler(bot, update, args):
    user = update.message.from_user

    username = ""
    for id, name in ama_database["users"]:
        if id == user.id:
            username = name
            break

    if args and len(args) > 0:
        feedback = open("feedback.txt", "a+")

        feedback.write(str(update.message.from_user.id) +
                       " (" + username + ") at " +
                       str(datetime.datetime.now()) + "\n")
        feedback.write(" ".join(args) + "\n\n")

        feedback.close()

        send_message(bot, update.message.chat_id, text="Your response has been recorded!")
    else:
        send_message(bot, update.message.chat_id, text="Error: You must input a non-empty string.")


def save_database(bot, update):
    if os.path.exists("amadatabase"):
        shutil.copy("amadatabase", "amadatabasebackup")
    pickle.dump(ama_database, open("amadatabase", "wb"))


def handle_error(bot, update, error):
    try:
        raise error
    except TelegramError:
        logging.getLogger(__name__).warning('Telegram Error! %s caused by this update: %s', error, update)


if __name__ == "__main__":
    bot = telegram.Bot(token=TOKEN)
    updater = Updater(token=TOKEN)
    dispatcher = updater.dispatcher

    # Init setup

    if ama_database.get("amas") is None:
        ama_database["amas"] = defaultdict(list)

    if ama_database.get("users") is None:
        ama_database["users"] = []

    if ama_database.get("patches") is None:
        ama_database["patches"] = []

    if ama_database.get("reply_history") is None:
        ama_database["reply_history"] = []

    # Static commands

    static_commands = ["start", "help"]
    for c in static_commands:
        dispatcher.add_handler(static_handler(c))

    # Main commands

    ama_aliases = ["ama", "ask"]
    reply_aliases = ["reply", "r"]
    display_aliases = ["display", "view", "d"]
    users_aliases = ["users", "u"]
    add_me_aliases = ["addme", "setname", "am", "sn"]
    remove_me_aliases = ["removeme", "rm"]
    feedback_aliases = ["feedback", "report"]
    clear_aliases = ["clear"]
    mass_ama_aliases = ["massama", "massask", "ma"]

    commands = [("ama", 4, ama_aliases),
                ("reply", 1, reply_aliases),
                ("display", 1, display_aliases),
                ("users", 0, users_aliases),
                ("add_me", 1, add_me_aliases),
                ("remove_me", 0, remove_me_aliases),
                ("remove_me_confirmed", 0, ["rmc"]),
                ("feedback", 1, feedback_aliases),
                ("confirm_ama", 3, ["confirmama"]),
                ("clear", 1, clear_aliases),
                ("mass_ama", 1, mass_ama_aliases)]

    for c in commands:
        func = locals()[c[0] + "_handler"]
        if c[1] == 0:
            dispatcher.add_handler(CommandHandler(c[2], func))
        elif c[1] == 1:
            dispatcher.add_handler(CommandHandler(c[2], func, pass_args=True))
        elif c[1] == 2:
            dispatcher.add_handler(CommandHandler(c[2], func, pass_chat_data=True))
        elif c[1] == 3:
            dispatcher.add_handler(CommandHandler(c[2], func, pass_user_data=True))
        elif c[1] == 4:
            dispatcher.add_handler(CommandHandler(c[2], func, pass_user_data=True, pass_args=True))

    # Set up job queue for repeating automatic tasks.

    jobs = updater.job_queue

    save_database_job = jobs.run_repeating(save_database, interval=3600, first=0)
    save_database_job.enabled = True

    # Error handler

    dispatcher.add_error_handler(handle_error)

    # Logger

    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO, filename='logging.txt', filemode='a+')

    # Restart

    def stop_and_restart():
        updater.stop()
        os.execl(sys.executable, sys.executable, *sys.argv)

    def restart(bot, update):
        save_database(bot, update)
        update.message.reply_text('Bot is restarting...')
        Thread(target=stop_and_restart).start()

    dispatcher.add_handler(CommandHandler("restart",
                                          restart,
                                          filters=Filters.user(username='@thweaver')))

    # Run the bot

    send_patchnotes(bot)

    updater.start_polling()
    updater.idle()
