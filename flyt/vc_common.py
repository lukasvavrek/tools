import os
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

AUTH_URL = 'https://connect.visma.com/connect/token'

# Get credentials from environment variables
CLIENT_ID = os.getenv('VISMA_CLIENT_ID')
CLIENT_SECRET = os.getenv('VISMA_CLIENT_SECRET')

# Validate that required environment variables are set
if not CLIENT_ID or not CLIENT_SECRET:
    raise ValueError("VISMA_CLIENT_ID and VISMA_CLIENT_SECRET must be set in environment variables")


def get_access_token(scope=None):
    grant_type = 'client_credentials'
    if not scope:
        scope = 'publicapi:user:read'

    data = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': grant_type,
        'scope': scope,
    }

    response = requests.post(AUTH_URL, data=data)

    return response.json()['access_token']


def fetch_users(access_token, domain=None, page=1):
    users_url = 'https://public-api.connect.visma.com/v1.0/users'
    users_url += f'?page={page}'

    if domain:
        users_url += f'&email=%@{domain}'

    headers = {
        'Authorization': f'Bearer {access_token}'
    }

    response = requests.get(users_url, headers=headers)

    if response.status_code != 200:
        raise Exception(f'Failed to fetch users for {domain}')

    users = response.json()

    return users
