import unittest
from patchrail.store import Store

class TestStore(unittest.TestCase):
    def test_create_table(self):
        store = Store('test.db')
        store.create_table()
        self.assertTrue(store.conn)

    def test_insert_funded_issue(self):
        store = Store('test.db')
        store.create_table()
        issue = {
            'owner': 'example',
            'issue_id': 1,
            'score': 0,
            'noise_flags': {}
        }
        store.insert_funded_issue(issue)
        self.assertTrue(store.get_funded_issues())

if __name__ == '__main__':
    unittest.main()