import unittest
from unittest.mock import patch

import monitor


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.cfg = {
            "target": {"internship_years": ["2027"], "exclude_remote": True},
            "categories": {"product": ["product manager"], "hedge_fund": ["quantitative trader"]},
        }

    def test_navigation_and_full_time_roles_do_not_match(self):
        self.assertEqual(monitor.matches({"title": "Careers", "department": "Product Manager Intern"}, self.cfg), [])
        self.assertEqual(monitor.matches({"title": "Product Manager, International"}, self.cfg), [])

    def test_title_year_and_remote_location(self):
        job = {"title": "Product Manager Intern 2027", "location": "New York"}
        self.assertEqual(monitor.matches(job, self.cfg), ["product"])
        self.assertEqual(monitor.matches({**job, "title": "Product Manager Intern 2026"}, self.cfg), [])
        self.assertEqual(monitor.matches({**job, "location": "Remote"}, self.cfg), [])

    def test_board_parser_requires_jobs_list_and_stable_id(self):
        data = {"jobs": [{"id": "fixed-id", "title": "Product Manager Intern", "jobUrl": "https://jobs.ashbyhq.com/example/fixed-id", "isListed": True},
                         {"id": "hidden", "title": "Product Manager Intern", "isListed": False}]}
        row = {"source_type": "ashby", "source_key": "example"}
        with patch.object(monitor, "fetch_json", return_value=data):
            jobs = monitor.api_jobs(row, 1)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["id"], "fixed-id")
        with patch.object(monitor, "fetch_json", return_value={"error": "board missing"}):
            with self.assertRaisesRegex(ValueError, "shape changed"):
                monitor.api_jobs(row, 1)


if __name__ == "__main__":
    unittest.main()
