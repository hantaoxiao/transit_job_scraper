import unittest
from unittest.mock import MagicMock, Mock, patch
from urllib.parse import parse_qs, unquote, urlparse

from agencies import AGENCIES
from scrapers import infor


AGENCY = next(agency for agency in AGENCIES if agency["agency"] == "NITA")


def view(number=148, posting=2, title="Senior Board Advisor"):
    values = {
        "Description": title, "JobRequisition": number, "JobId": number,
        "CategoryDescriptionForSort": "Executive Office", "WorkType": "FT",
        "LocationOfJob_prd_Location_ohb_2_chb_": "IL", "LocationOfJob_prd_Location_ohb_3_chb_": "Chicago",
        "PostingDateRange_prd_Begin": "20261020",
    }
    return {"resourceId": f"JobPosting[JobPostingSet](1,{number},{posting})",
            "fields": {key: {"value": value} for key, value in values.items()}}


def listing(records, next_url=None):
    return {"status": "COMPLETED", "dataViewSet": {
        "data": records, "pagingInfo": {"hasNext": next_url is not None},
        "pagingUrls": {"nextPageUrl": next_url} if next_url else {},
    }}


def detail(record):
    return {"status": "COMPLETED", "resourceId": record["resourceId"], "fields": {
        "_op_Description_spc_translation_cp_": {"value": record["fields"]["Description"]["value"]},
        "_op_PositionDescription_spc_translation_cp_": {"value": '''<b>26-SBA</b>
        <p>Advise the Northern Illinois Transit Authority board on regional transit.</p>
        <p>Pension plan or 401(k) salary match.</p>
        <p>This role typically offers salaries ranging from $141,450 to $176,813 for highly qualified candidates.</p>'''},
        "PostingDateRange_prd_End": {"value": "20261218"},
        "SalaryAmountEntered": {"value": False},
        "_op_FormattedSalaryRangeAmountWithCurrencyCodeAndPayRate_spc_translation_cp_": {"value": "0 - 0 per year"},
    }}


def response(payload):
    result = Mock()
    result.json.return_value = payload
    return result


class InforTests(unittest.TestCase):
    def test_nita_collects_both_postings_with_complete_metadata(self):
        first = view()
        second = view(147, 1, "Chief Transit Safety Officer")
        session = MagicMock()
        session.__enter__.return_value = session
        session.get.side_effect = [response(listing([first, second])), response(detail(first)), response(detail(second))]
        with patch.object(infor.requests, "Session", return_value=session):
            jobs = infor.scrape_infor(AGENCY)
        self.assertEqual(len(jobs), 2)
        job = jobs[0]
        self.assertEqual(job["agency"], "NITA")
        self.assertEqual(job["title"], "Senior Board Advisor")
        self.assertEqual((job["city"], job["state"]), ("Chicago", "IL"))
        self.assertEqual(job["salary_range_display"], "$141,450 - $176,813")
        self.assertEqual(job["posted_date"], "2026-10-20")
        self.assertEqual(job["closing_date"], "2026-12-18")
        self.assertEqual(job["employment_type"], "Full Time")
        self.assertEqual(job["requisition_id"], "148")
        self.assertIn("regional transit", job["description"])
        parsed = urlparse(job["source_url"])
        self.assertIn("JobPosting[JobPostingSet](1,148,2).JobPostingDisplay", unquote(parsed.path))
        self.assertEqual(parse_qs(parsed.query)["csk.JobBoard"], ["EXTERNAL"])
        self.assertNotIn("pageop", parse_qs(parsed.query))
        self.assertEqual(parse_qs(urlparse(session.get.call_args_list[0].args[0]).query)["pagesize"], ["100"])

    def test_pagination_follows_server_url_and_deduplicates_postings(self):
        first = view()
        second = view(147, 1, "Chief Transit Safety Officer")
        next_url = AGENCY["jobs_url"] + "&pageop=next&lk=cursor"
        session = Mock()
        session.get.side_effect = [response(listing([first], next_url)), response(listing([first, second]))]
        records = infor._listings(session, AGENCY)
        self.assertEqual(len(records), 2)
        self.assertEqual(session.get.call_args.args[0], next_url)

    def test_recognized_empty_board_returns_empty_list(self):
        session = Mock()
        session.get.return_value = response(listing([]))
        self.assertEqual(infor._listings(session, AGENCY), [])

    def test_missing_data_or_unauthorized_response_is_not_zero_jobs(self):
        for payload in ({"status": "UNAUTHORIZED"}, {"status": "COMPLETED"}):
            with self.subTest(payload=payload):
                session = Mock()
                session.get.return_value = response(payload)
                with self.assertRaises(RuntimeError):
                    infor._listings(session, AGENCY)

    def test_repeated_pagination_fails_before_returning_partial_jobs(self):
        url = infor._load_url(AGENCY["jobs_url"], listing=True)
        session = Mock()
        session.get.return_value = response(listing([view()], url))
        with self.assertRaisesRegex(RuntimeError, "repeated"):
            infor._listings(session, AGENCY)
        self.assertEqual(session.get.call_count, 1)

    def test_pagination_cannot_leave_configured_job_board(self):
        session = Mock()
        session.get.return_value = response(listing([view()], "https://example.com/list"))
        with self.assertRaisesRegex(RuntimeError, "outside"):
            infor._listings(session, AGENCY)
        self.assertEqual(session.get.call_count, 1)

    def test_missing_or_mismatched_detail_fails_instead_of_publishing_wrong_job(self):
        record = view()
        for payload in (detail(view(147, 1)), {"status": "COMPLETED", "resourceId": record["resourceId"], "fields": {}}):
            with self.subTest(payload=payload):
                session = MagicMock()
                session.__enter__.return_value = session
                session.get.side_effect = [response(listing([record])), response(payload)]
                with patch.object(infor.requests, "Session", return_value=session):
                    with self.assertRaises(RuntimeError):
                        infor.scrape_infor(AGENCY)


if __name__ == "__main__":
    unittest.main()
