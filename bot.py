#!/usr/bin/env python
from bs4 import BeautifulSoup
import random
import requests
import telebot
import datetime


def get_token():
    with open('tgtoken') as f:
        token = f.read()
    return token


class Events:
    def __init__(self, source, source_type='file'):
        self.source = source
        self.source_type = source_type

    @staticmethod
    def get_games_list():
        try:
            res = requests.request(
                'POST',
                'https://premierliga.ru/ajax/match/',
                data={
                    'ajaxAction': 'getTourStats',
                    'tour': 0,
                    'season': 719
                },
                headers={
                    'Accept': 'application/json'}
            )
        except Exception as exc:
            print(exc)
        if res.status_code == 200:
            return res.json()['contents']
        else:
            print(f'Response code is {res.status_code}')

    @staticmethod
    def get_nearest_round():
        games = Events.get_games_list()

        cur_date = datetime.datetime.now()

        future_rounds = sorted([
            {
                'team1': i['name1'],
                'team2': i['name2'],
                'round': i['stageName'],
                'round_id': i['stage'],
                'date': datetime.datetime.strptime(f"{i['date']} {i['time']}", '%d.%m.%Y %H:%M'),
                'goal1': '',
                'goal2': '',
            } for i in games if cur_date < datetime.datetime.strptime(f"{i['date']} {i['time']}", '%d.%m.%Y %H:%M')
        ], key=lambda e: e['date'])

        return [i for i in future_rounds if i['round_id'] == future_rounds[0]['round_id']]

    def get_events(self):
        if self.source_type == 'file':
            with open(self.source, encoding='utf-8') as f:
                self.events = f.readlines()
        return self.events


class PredictorBot:
    
    round = Events.get_nearest_round()
    
    def __init__(self, token: str, events: list):
        self.bot = telebot.TeleBot(token)
        self.events = events

    def run(self):
        @self.bot.message_handler(commands=['help'])
        def send_help(message):
            help_text = '''
/start - приветственное сообщение
/game - выбор игры
/help - список доступных команд
'''
            self.bot.reply_to(message, help_text)

        @self.bot.message_handler(commands=['start'])
        def send_welcome(message):
            welcome_text = "Привет! Я Бот-предсказатель. Напиши мне /game, чтобы узнать прогноз на игру."
            self.bot.reply_to(message, welcome_text)

        @self.bot.message_handler(commands=['game'])
        def choose_event(message):
            self.prediction()
            keyboard = telebot.types.InlineKeyboardMarkup()
            for game in PredictorBot.round:
                button = telebot.types.InlineKeyboardButton(
                    text=game['event'], callback_data=f"{game['event']}_{game['score']}")
                keyboard.add(button)
            self.bot.send_message(
                message.chat.id, "Выберите нужный матч:", reply_markup=keyboard)

        @self.bot.callback_query_handler(func=lambda call: True)
        def handle_callback_query(call):
            self.bot.send_message(call.message.chat.id,
                                  "Предсказание готовится...")
            self.bot.send_message(
                call.message.chat.id, f"Я только учусь, но думаю что матч {call.data.split('_')[0]} закончится со счетом {call.data.split('_')[1]}")

        self.bot.polling()

    def prediction(self):
        # TODO: change random to ML
        for game in PredictorBot.round:
            game['event'] = f"{game['team1']} - {game['team2']}"
            if not game['goal1'] and not game['goal2']:
                game['goal1'], game['goal2'] = random.randrange(0, 5), random.randrange(0, 5)
            game['score'] = f"{game['goal1']}:{game['goal2']}"


if __name__ == '__main__':
    token = get_token()
    # TODO: suppport few sources of events
    games = Events('./games_list')
    prediction_bot = PredictorBot(token, games.get_events())
    prediction_bot.run()
