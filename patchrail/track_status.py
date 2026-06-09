import sqlite3

class TrackStatus:
    def __init__(self, db_file):
        self.conn = sqlite3.connect(db_file)
        self.cursor = self.conn.cursor()

    def get_tracked_issues(self):
        self.cursor.execute('SELECT * FROM funded_issues')
        return self.cursor.fetchall()

    def get_noise_flagged_issues(self):
        self.cursor.execute('SELECT * FROM funded_issues WHERE noise_flags IS NOT NULL')
        return self.cursor.fetchall()

    def get_under_review_issues(self):
        self.cursor.execute('SELECT * FROM funded_issues WHERE score IS NULL')
        return self.cursor.fetchall()

    def print_status(self):
        tracked_issues = self.get_tracked_issues()
        noise_flagged_issues = self.get_noise_flagged_issues()
        under_review_issues = self.get_under_review_issues()

        print(f'Tracked issues: {len(tracked_issues)}')
        print(f'Noise flagged issues: {len(noise_flagged_issues)}')
        print(f'Under review issues: {len(under_review_issues)}')