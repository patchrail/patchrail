import datetime
import requests

def calculate_source_noise(owner):
    """
    Calculate the source noise heuristic for an owner.
    """
    noise_flags = {
        'account_age': False,
        'public_repo_count': False,
        'followers': False,
        'website_presence': False,
        'payout_verifiability': False,
        'anomalous_volume': False
    }

    # Account age
    if owner['created_at'] > datetime.datetime.now() - datetime.timedelta(days=30):
        noise_flags['account_age'] = True

    # Public repo count
    if owner['public_repos'] < 2:
        noise_flags['public_repo_count'] = True

    # Followers
    if owner['followers'] < 5:
        noise_flags['followers'] = True

    # Website presence
    if not owner['website']:
        noise_flags['website_presence'] = True

    # Payout verifiability
    if not owner['payout_verifiability']:
        noise_flags['payout_verifiability'] = True

    # Anomalous volume
    if owner['issue_count'] > 10:
        noise_flags['anomalous_volume'] = True

    return noise_flags

def get_owner_info(owner_name):
    """
    Get owner info from GitHub API.
    """
    url = f'https://api.github.com/users/{owner_name}'
    response = requests.get(url)
    return response.json()

def score_funded_issue(issue):
    """
    Score a funded issue based on the owner's source noise.
    """
    owner_name = issue['owner']
    owner_info = get_owner_info(owner_name)
    noise_flags = calculate_source_noise(owner_info)

    # Calculate the overall score
    score = 0
    for flag, value in noise_flags.items():
        if value:
            score += 1

    return score