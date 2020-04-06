import datetime
from dotenv import load_dotenv
import pandas as pd
from pytz import timezone
import tweepy
import time
import os


load_dotenv()


def authenticate_twitter():
    auth = tweepy.OAuthHandler(
        os.environ['API_KEY'], os.environ['API_SECRET_KEY'])
    auth.set_access_token(
        os.environ['ACCESS_TOKEN'], os.environ['ACCESS_TOKEN_SECRET'])
    api = tweepy.API(auth)
    return api


def retrieve_thread_ids(api, latest_status_id):
    '''Starting with a reply, follow tweet thread back to OP and return IDs
    Arguments:
    api -- authenticated tweepy API object
    starting_status_id -- ID number for tweet to start at. Int
    '''
    status_ids = []

    def retrieve_parent_status_id(api, status_id):
        ''' recursively follow tweet thread from status_id
        to OP and return IDs'''
        status_ids.append(status_id)
        parent_id = api.statuses_lookup([status_id])[0].in_reply_to_status_id
        if parent_id is None:
            return status_ids
        else:
            return retrieve_parent_status_id(api, parent_id)
    return retrieve_parent_status_id(api, latest_status_id)


def create_tweet_thread_df(api, latest_status_id):
    '''Retrieve id, text, and timestamp on tweet and all preceding tweets
    in the thread, return as pandas DataFrame
    Arguments:
    api -- authenticated tweepy API object
    '''
    thread_status_ids = retrieve_thread_ids(api, latest_status_id)
    thread_tweets = api.statuses_lookup(thread_status_ids)
    ordered_ids = [tweet.id for tweet in thread_tweets]
    UTCs = [tweet.created_at.replace(tzinfo=timezone('UTC'))
            for tweet in thread_tweets]
    PDTs = [tweet_time.astimezone(timezone('US/Pacific'))
            for tweet_time in UTCs]
    texts = [tweet.text for tweet in thread_tweets]
    df = pd.DataFrame({
        'id': ordered_ids,
        'UTC': UTCs,
        'PDT': PDTs,
        'text': texts
    }).sort_values('PDT').reset_index(drop=True)
    return df


def make_ordinal(n):
    '''
    From user Florian Bruker, retrieved April 5th 2020
    https://stackoverflow.com/questions/9647202/ordinal-numbers-replacement

    Convert an integer into its ordinal representation::

        make_ordinal(0)   => '0th'
        make_ordinal(3)   => '3rd'
        make_ordinal(122) => '122nd'
        make_ordinal(213) => '213th'
    '''
    n = int(n)
    suffix = ['th', 'st', 'nd', 'rd', 'th'][min(n % 10, 4)]
    if 11 <= (n % 100) <= 13:
        suffix = 'th'
    return str(n) + suffix


def get_latest_covid_data(
    url='https://covidtracking.com/api/v1/us/current.csv'):
    '''download latest data from covidtracking.com'''
    covid_data = pd.read_csv(url)
    num_cases = covid_data.loc[0,'positive']
    num_deaths = covid_data.loc[0,'death']
    return num_cases, num_deaths


def compose_new_covid_tweet():
    '''get latest covid data and use to write text for new tweet'''
    num_cases, num_deaths = get_latest_covid_data()
    today = datetime.datetime.now().astimezone(timezone('US/Pacific'))
    month = today.strftime('%B')
    day = make_ordinal(int(today.strftime('%d')))
    cases_increase = num_cases / 523
    deaths_increase = num_deaths / 19
    tweet_text = f"""{month.capitalize()} {day}

Confirmed COVID-19 cases in the US: {num_cases:,.0f}. ~{cases_increase:,.0f}x increase since March 9th
Deaths from COVID-19 in the US: {num_deaths:,.0f}. ~{deaths_increase:,.0f}x increase since March 9th"""
    return tweet_text


def update_covid_thread_df(df_savepath='covid_thread_history.csv'):
    '''Load saved data to find most recent tweet > reply to it with a new tweet
    with latest stats > update saved data to include new reply
    '''
    api = authenticate_twitter()
    df = pd.read_csv(df_savepath, index_col=0)
    latest_status_id = df['id'].iloc[-1]
    new_tweet = api.update_status(
        status = compose_new_covid_tweet(),
        in_reply_to_status_id = latest_status_id,
        auto_populate_reply_metadata=True
    )
    time.sleep(5)  # give new tweet time to get up there before updating data
    create_tweet_thread_df(api, new_tweet.id).to_csv(df_savepath)


if __name__ == "__main__":
    update_covid_thread_df()
