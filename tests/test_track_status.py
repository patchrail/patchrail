import unittest
from patchrail.track_status import TrackStatus

class TestTrackStatus(unittest.TestCase):
    def test_get_tracked_issues(self):
        track_status = TrackStatus('test.db')
        tracked_issues = track_status.get_tracked_issues()
        self.assertIsNotNone(tracked_issues)

    def test_get_noise_flagged_issues(self):
        track_status = TrackStatus('test.db')
        noise_flagged_issues = track_status.get_noise_flagged_issues()
        self.assertIsNotNone(noise_flagged_issues)

    def test_get_under_review_issues(self):
        track_status = TrackStatus('test.db')
        under_review_issues = track_status.get_under_review_issues()
        self.assertIsNotNone(under_review_issues)

if __name__ == '__main__':
    unittest.main()