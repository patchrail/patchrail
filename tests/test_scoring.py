import unittest
from patchrail.scoring import calculate_source_noise, get_owner_info

class TestScoring(unittest.TestCase):
    def test_calculate_source_noise(self):
        owner_info = {
            'created_at': '2022-01-01T00:00:00Z',
            'public_repos': 10,
            'followers': 100,
            'website': 'https://example.com',
            'payout_verifiability': True,
            'issue_count': 5
        }
        noise_flags = calculate_source_noise(owner_info)
        self.assertFalse(noise_flags['account_age'])
        self.assertFalse(noise_flags['public_repo_count'])
        self.assertFalse(noise_flags['followers'])
        self.assertFalse(noise_flags['website_presence'])
        self.assertFalse(noise_flags['payout_verifiability'])
        self.assertFalse(noise_flags['anomalous_volume'])

    def test_get_owner_info(self):
        owner_name = 'example'
        owner_info = get_owner_info(owner_name)
        self.assertIsNotNone(owner_info)

if __name__ == '__main__':
    unittest.main()