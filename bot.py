#!/usr/bin/env python
import datetime
import logging
import requests
import telebot
import yaml
from bs4 import BeautifulSoup
from sklearn.linear_model import LinearRegression

logger = logging.getLogger(__name__)
logging.basicConfig(encoding='utf-8', level=logging.INFO)

def get_token():
    with open('/opt/diploma/tgtoken') as f:
        token = f.read()
    return token


class Events:
    def __init__(self, source: str = '', source_type: str = 'file'):
        self.source = source
        self.source_type = source_type
        try:
            with open("/opt/diploma/teams.yaml", "r") as f:
                self.teams_list = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            logger.exception(exc)
            self.teams_list = []

    def get_games_list(self):
        try:
            res = requests.request(
                'POST',
                self.source,
                data={
                    'ajaxAction': 'getTourStats',
                    'tour': 0,
                    'season': 719
                },
                headers={
                    'Accept': 'application/json'}
            )
            if res.status_code == 200:
                self.games = res.json()['contents']
            else:
                logger.error(f'Response code is {res.status_code}')
        except Exception as exc:
            logger.exception(exc)
            self.games = []

    def team_name_convert(self, team_name: str) -> str:
        for t in self.teams_list:
            if team_name in t:
                return t[team_name].lower()

    def get_nearest_round(self):
        self.get_games_list()
        cur_date = datetime.datetime(2024, 5, 25)
        # cur_date = datetime.datetime.now()

        future_rounds = sorted([
            {
                'team1': i['name1'],
                'team2': i['name2'],
                'en_team1': self.team_name_convert(i['name1']),
                'en_team2': self.team_name_convert(i['name2']),
                'round': i['stageName'],
                'round_id': i['stage'],
                'date': datetime.datetime.strptime(f"{i['date']} {i['time']}", '%d.%m.%Y %H:%M'),
                'goal1': '',
                'goal2': '',
                'p_team1': '',
                'p_team2': '',
            } for i in self.games if cur_date < datetime.datetime.strptime(f"{i['date']} {i['time']}", '%d.%m.%Y %H:%M')
        ], key=lambda e: e['date'])

        self.events = [i for i in future_rounds if i['round_id'] == future_rounds[0]['round_id']]

    def get_events(self):
        if self.source_type == 'file':
            try:
                with open(self.source, encoding='utf-8') as f:
                    self.events = yaml.safe_load(f)
            except Exception as exc:
                logger.exception(exc)
                self.events = []
        elif self.source_type == 'url':
            self.get_nearest_round()
        return self.events


class PredictorBot:

    # it's class attribute, because bot creates new instance of class for every user
    round = []

    @classmethod
    def round_prepare(cls):
        for g in cls.round:
            del g['date']
            g['event'] = f"{g['team1']} - {g['team2']}"

    def __init__(self, token: str, predict_model, games):
        self.bot = telebot.TeleBot(token)
        self.predictor = predict_model
        self.games = games
        self.prediction()

    def run(self):
        @self.bot.message_handler(commands=['help'])
        def send_help(message):
            logger.info('help was called')
            help_text = '''
/start - приветственное сообщение
/game - выбор игры
/refresh - обновление списка игр
/help - список доступных команд
'''
            self.bot.reply_to(message, help_text)

        @self.bot.message_handler(commands=['start'])
        def send_welcome(message):
            logger.info('start was called')
            welcome_text = "Привет! Я Бот-предсказатель. Напиши мне /game, чтобы узнать прогноз на игру."
            self.bot.reply_to(message, welcome_text)

        @self.bot.message_handler(commands=['refresh'])
        def send_refresh(message):
            logger.info('refresh was called')
            text = "Обновляю список ближайших игр"
            PredictorBot.round = self.games.get_events()
            PredictorBot.round_prepare()
            self.prediction()            
            logger.info('we\'ve refreshed games for the closest round')
            self.bot.reply_to(message, text)

        @self.bot.message_handler(commands=['game'])
        def choose_event(message):
            logger.info('game was called')
            keyboard = telebot.types.InlineKeyboardMarkup()
            for game in PredictorBot.round:
                button = telebot.types.InlineKeyboardButton(
                    text=game['event'], callback_data=game['event'])
                keyboard.add(button)
            self.bot.send_message(
                message.chat.id, "Выберите нужный матч:", reply_markup=keyboard)

        @self.bot.callback_query_handler(func=lambda call: True)
        def handle_callback_query(call):
            for g in PredictorBot.round:
                if g['event'] == call.data:
                    game = g

            text = f'''
Матч {game['event']}
С вероятностью {round(game['p_team1'][0]*100, 1)}% выиграет команда {game['team1']},
С вероятностью {round(game['p_team2'][0]*100, 1)}% выиграет команда {game['team2']}
Поэтому считаю, что в результате {game['result']}
'''
            self.bot.send_message(call.message.chat.id, text)

        self.bot.polling()

    def prediction(self):
        for g in PredictorBot.round:
            # 
            g['p_team1'] = self.predictor.create_game_prediction(
                g['en_team1'], g['en_team2'])
            g['p_team2'] = self.predictor.create_game_prediction(
                g['en_team2'], g['en_team1'])
            if g['p_team1'][0] > 0.55:
                if g['p_team2'][0] < 0.45:
                    g['result'] = f"победит команда {g['team1']}"
                elif 0.45 <= g['p_team2'][0] <= 0.55:
                    g['result'] = f"победит команда {g['team1']} или будет ничья"
                elif g['p_team2'][0] > 0.55:
                    g['result'] = f"будет ничья"
            elif 0.45 <= g['p_team1'][0] <= 0.55:
                if g['p_team2'][0] < 0.45:
                    g['result'] = f"победит команда {g['team1']} или будет ничья"
                elif 0.45 <= g['p_team2'][0] <= 0.55:
                    g['result'] = f"будет ничья"
                elif g['p_team2'][0] > 0.55:
                    g['result'] = f"победит команда {g['team2']}"
            if g['p_team1'][0] < 0.45:
                if g['p_team2'][0] < 0.45:
                    g['result'] = f"будет ничья"
                elif 0.45 <= g['p_team2'][0] <= 0.55:
                    g['result'] = f"победит команда {g['team2']} или будет ничья"
                elif g['p_team2'][0] > 0.55:
                    g['result'] = f"победит команда {g['team2']}"

            # if not g['goal1'] and not g['goal2']:
            #     g['goal1'], g['goal2'] = random.randrange(
            #         0, 5), random.randrange(0, 5)
            # g['score'] = f"{g['goal1']}:{g['goal2']}"


class PredictionModel:

    def __init__(self, url: str = ''):
        self.url = url
        self.season_links = {}
        self.tables = {}
        self.teams_stat = {}
        self.t_annual_stat = {}
        self.t_games_result = {}
        self.t_stat_vector = []
        self.t_games_vector = []
        self.model = LinearRegression()

    def get_training_data(self):
        self._get_data(t='seasons')

        self._parse_seasons()
        self._get_season_data()
        self._parse_season()
        self._prepare_training_annual_stat()

    def get_games_results(self):
        self._get_data(t='results')
        for season, results in self.data.items():
            self.t_games_result[season] = {
                f"{team}_{game['guests']}": 1
                if game['home_goals'] > game['guests_goals'] else 0
                for team, games in results.items()
                for game in games}

    def train_prediction_model(self):
        self._prepare_training_data()
        self.model.fit(self.t_stat_vector, self.t_games_vector)

    def create_game_prediction(self, team1_name, team2_name):
        team1_vector = self.teams_stat['2023-2024'][team1_name]
        team2_vector = self.teams_stat['2023-2024'][team2_name]
        diff = [[a - b for a, b in zip(team1_vector, team2_vector)]]
        predictions = self.model.predict(diff)
        return predictions.tolist()

    def _get_data(self, t='seasons', l=''):
        if t == 'seasons':
            resp = requests.get(self.url)
            soup = BeautifulSoup(resp.text, 'lxml')
            self.data = soup.find('table', id='seasons')
        elif t == 'season':
            resp = requests.get(f"https://fbref.com/{l}")
            self.data = BeautifulSoup(resp.text, "lxml")
        elif t == 'results':
            with open("/opt/diploma/result.yaml", "r") as f:
                try:
                    self.data = yaml.safe_load(f)
                except yaml.YAMLError as exc:
                    logger.exception(exc)

    def _parse_seasons(self):
        if self.data:
            rows = self.data.find_all('tr')
            for row in rows:
                cells = row.find_all(['th', 'td'])
                # Catch only full seasons
                if cells[2].text == '16':
                    self.season_links[cells[0].text] = cells[1].find(
                        'a').get('href')

    def _get_season_data(self):
        for season, l in self.season_links.items():
            self._get_data(t='season', l=l)
            stats_tables = [
                'results{s}301_overall',
                'stats_squads_standard_for',
                'stats_squads_shooting_for',
            ]
            stats_tables[0] = stats_tables[0].format(s=season)

            self.tables[season] = {}
            for item in stats_tables:
                self.tables[season][item] = self.data.find('table', id=item)

    def _parse_season(self):
        for season, table in self.tables.items():
            self.teams_stat[season] = {}

            for table_name, data in table.items():
                if data:
                    rows = data.find_all('tr')
                    for row in rows[1:]:
                        if 'Squad' not in row.get_text():
                            cells = row.find_all(['th', 'td'])
                            row_data = [cell.text.strip() for cell in cells]
                            if 'overall' in table_name:
                                self.teams_stat[season][row_data[1].lower()] = [
                                    int(row_data[3]) if row_data[3] else 0,
                                    int(row_data[4]) if row_data[4] else 0,
                                    int(row_data[5]) if row_data[5] else 0,
                                    int(row_data[6]) if row_data[6] else 0,
                                    int(row_data[7]) if row_data[7] else 0,
                                    int(row_data[9]) if row_data[9] else 0,
                                ]
                            elif 'standard' in table_name:
                                self.teams_stat[season][row_data[0].lower()].extend([
                                    float(row_data[3]) if row_data[3] else 0.0,
                                    float(row_data[2]) if row_data[2] else 0.0,
                                    int(row_data[9]) if row_data[9] else 0,
                                ])
                            elif 'shooting' in table_name:
                                self.teams_stat[season][row_data[0].lower()].extend([
                                    int(row_data[4]) if row_data[4] else 0,
                                    int(row_data[5]) if row_data[5] else 0,
                                ])
                else:
                    logger.info(f'Nothing found in {season} for table {table_name}')
                    for team in self.teams_stat[season]:
                        if 'overall' in table_name:
                            self.teams_stat[season][team] = [0, 0, 0, 0, 0, 0,]
                        elif 'standard' in table_name:
                            self.teams_stat[season][team].extend([0, 0, 0])
                        elif 'shooting' in table_name:
                            self.teams_stat[season][team].extend([0, 0])

    def _prepare_training_annual_stat(self):
        for season, data in self.teams_stat.items():
            if season != '2023-2024':
                self.t_annual_stat[season] = {
                    f"{team1 if 'terek' not in team1 else 'akhmat grozny'}_{team2 if 'terek' not in team2 else 'akhmat grozny'}": [a - b for a, b in zip(data[team1], data[team2])]
                    for team1 in data
                    for team2 in data
                    if team1 != team2
                }

    def _prepare_training_data(self):
        for season, data in self.t_annual_stat.items():
            for k, v in data.items():
                self.t_stat_vector.append(v)
                try:
                    self.t_games_vector.append(self.t_games_result[season][k])
                except:
                    logger.exception(f'error in {season} with game {k}')


if __name__ == '__main__':
    url = 'https://premierliga.ru/ajax/match/'
    url_for_training = "https://fbref.com/en/comps/30/history/Russian-Premier-League-Seasons"
    # Get token from file
    token = get_token()
    # Create list of upcoming games
    games = Events(source=url, source_type='url')
    PredictorBot.round = games.get_events()
    PredictorBot.round_prepare()
    logger.info('we\'ve recieved games for the closest round')

    # Prediction model training
    predict_model = PredictionModel(url=url_for_training)
    predict_model.get_training_data()
    predict_model.get_games_results()
    predict_model.train_prediction_model()
    logger.info('we\'ve trained prediction model')

    # Launch bot instanse
    prediction_bot = PredictorBot(token=token, predict_model=predict_model, games=games)
    prediction_bot.run()
