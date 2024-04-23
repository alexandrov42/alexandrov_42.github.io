#!/usr/bin/env python

from bs4 import BeautifulSoup
import requests
import yaml
from sklearn.linear_model import LinearRegression

resp = requests.get(
    "https://fbref.com/en/comps/30/history/Russian-Premier-League-Seasons")

soup = BeautifulSoup(resp.text, 'lxml')

seasons = soup.find('table', id='seasons')
season_links = {}
tables = {}
teams_stat = {}
train_annual_stat = {}
train_game_result = {}
train_stat_vector = []
train_games_vector = []


# grep season and links for them from html
if seasons:
    rows = seasons.find_all('tr')
    for row in rows:
        cells = row.find_all(['th', 'td'])
        # catch only full seasons
        if cells[2].text == '16':
            season_links[cells[0].text] = cells[1].find('a').get('href')

# grep three table for each season from html
for season, l in season_links.items():
    stats_tables = [
        'results{s}301_overall',
        'stats_squads_standard_for',
        'stats_squads_shooting_for',
    ]
    resp = requests.get(f"https://fbref.com/{l}")

    season_soup = BeautifulSoup(resp.text, "lxml")

    stats_tables[0] = stats_tables[0].format(s=season)

    tables[season] = {}
    for item in stats_tables:
        tables[season][item] = season_soup.find('table', id=item)

for season, table in tables.items():
    teams_stat[season] = {}
    for table_name, data in table.items():
        if data:
            rows = data.find_all('tr')
            for row in rows[1:]:
                if 'Squad' not in row.get_text():
                    cells = row.find_all(['th', 'td'])
                    row_data = [cell.text.strip() for cell in cells]
                    if 'overall' in table_name:
                        teams_stat[season][row_data[1].lower()] = [
                            int(row_data[3]) if row_data[3] else 0,
                            int(row_data[4]) if row_data[4] else 0,
                            int(row_data[5]) if row_data[5] else 0,
                            int(row_data[6]) if row_data[6] else 0,
                            int(row_data[7]) if row_data[7] else 0,
                            int(row_data[9]) if row_data[9] else 0,
                        ]
                    elif 'standard' in table_name:
                        teams_stat[season][row_data[0].lower()].extend([
                            float(row_data[3]) if row_data[3] else 0.0,
                            float(row_data[2]) if row_data[2] else 0.0,
                            int(row_data[9]) if row_data[9] else 0,
                        ])
                    elif 'shooting' in table_name:
                        teams_stat[season][row_data[0].lower()].extend([
                            int(row_data[4]) if row_data[4] else 0,
                            int(row_data[5]) if row_data[5] else 0,
                        ])
        else:
            print(f'Nothing found in {season} for table {table_name}')
            for team in teams_stat[season]:
                if 'overall' in table_name:
                    teams_stat[season][team] = [0, 0, 0, 0, 0, 0,]
                elif 'standard' in table_name:
                    teams_stat[season][team].extend([0, 0, 0])
                elif 'shooting' in table_name:
                    teams_stat[season][team].extend([0, 0])

# pprint.pprint(teams_stat, width=120)

for season, data in teams_stat.items():
    if season != '2023-2024':
        train_annual_stat[season] = {
            f"{team1 if 'terek' not in team1 else 'akhmat grozny'}_{team2 if 'terek' not in team2 else 'akhmat grozny'}": [a - b for a, b in zip(data[team1], data[team2])]
            for team1 in data
            for team2 in data
            if team1 != team2
        }

# pprint.pprint(train_annual_stat, width=180)

# comand_params = ['win', 'draw', 'lose', 'goals', 'goals_miss',
#                  'points', 'possesion', 'Age', 'Ast', 'shots', 'SoT', ]

with open("result.yaml", "r") as data:
    try:
        game_results = yaml.safe_load(data)
    except yaml.YAMLError as exc:
        print(exc)

# print(game_results)
for season, results in game_results.items():
    train_game_result[season] = {
        f"{team}_{game['guests']}": 1
        if game['home_goals'] > game['guests_goals'] else 0
        for team, games in results.items()
        for game in games}

for season, data in train_annual_stat.items():
    for k, v in data.items():
        train_stat_vector.append(v)
        try:
            train_games_vector.append(train_game_result[season][k])
        except:
            print(f'error in {season} with game {k}')


# print(train_stat_vector)
# print(train_games_vector)

model = LinearRegression()
model.fit(train_stat_vector, train_games_vector)


def createGamePrediction(team1_vector, team2_vector):
    diff = [[a - b for a, b in zip(team1_vector, team2_vector)]]
    predictions = model.predict(diff)
    return predictions

# print(f"Вероятность, что выиграет Локомотив: {createGamePrediction(teams_stat['2023-2024']['loko moscow'], teams_stat['2023-2024']['krasnodar'])}")
# print(f"Вероятность, что выиграет Краснодар: {createGamePrediction(teams_stat['2023-2024']['krasnodar'], teams_stat['2023-2024']['loko moscow'])}")

# print(f"Вероятность, что выиграет Rubin: {createGamePrediction(teams_stat['2023-2024']['rubin kazan'], teams_stat['2023-2024']['akhmat grozny'])}")
# print(f"Вероятность, что выиграет Akhmat: {createGamePrediction(teams_stat['2023-2024']['akhmat grozny'], teams_stat['2023-2024']['rubin kazan'])}")




print(f"Вероятность, что выиграет fakel voronezh: {createGamePrediction(teams_stat['2023-2024']['fakel voronezh'], teams_stat['2023-2024']['rostov'])}")
print(f"Вероятность, что выиграет rostov: {createGamePrediction(teams_stat['2023-2024']['rostov'], teams_stat['2023-2024']['fakel voronezh'])}")
