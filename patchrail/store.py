import sqlite3

class Store:
    def __init__(self, db_file):
        self.conn = sqlite3.connect(db_file)
        self.cursor = self.conn.cursor()

    def create_table(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS funded_issues (
                id INTEGER PRIMARY KEY,
                owner TEXT,
                issue_id INTEGER,
                score INTEGER,
                noise_flags TEXT
            )
        ''')
        self.conn.commit()

    def insert_funded_issue(self, issue):
        self.cursor.execute('''
            INSERT INTO funded_issues (owner, issue_id, score, noise_flags)
            VALUES (?, ?, ?, ?)
        ''', (issue['owner'], issue['issue_id'], issue['score'], str(issue['noise_flags'])))
        self.conn.commit()

    def get_funded_issues(self):
        self.cursor.execute('SELECT * FROM funded_issues')
        return self.cursor.fetchall()

    def update_funded_issue(self, issue):
        self.cursor.execute('''
            UPDATE funded_issues
            SET score = ?, noise_flags = ?
            WHERE owner = ? AND issue_id = ?
        ''', (issue['score'], str(issue['noise_flags']), issue['owner'], issue['issue_id']))
        self.conn.commit()