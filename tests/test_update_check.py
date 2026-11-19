"""The daily update check: version compare, throttle, answer parsing. No real network: urlopen is replaced."""
import io
import json
import socket
import unittest
import urllib.error
from unittest import mock

from convert_win import update_check as uc

PAGE = uc.PAGE_PREFIX + "tag/v9.9.9"


class Resp(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def answer(**over):
    body = {"tag_name": "v9.9.9", "html_url": PAGE, "draft": False, "prerelease": False}
    body.update(over)
    return Resp(json.dumps(body).encode())


class Versions(unittest.TestCase):
    def test_numbers_not_text(self):
        self.assertTrue(uc.newer("v0.1.10", "0.1.9"))  # "0.1.10" < "0.1.9" as text, not as numbers
        self.assertTrue(uc.newer("v0.2.0", "0.1.99"))
        self.assertFalse(uc.newer("v0.1.12", "0.1.12"))
        self.assertFalse(uc.newer("v0.1.11", "0.1.12"))

    def test_odd_tags_are_never_newer(self):
        for tag in ("latest", "v1.2", "v1.2.3-rc1", "", None, 5, "v1.2.3.4"):
            self.assertFalse(uc.newer(tag, "0.1.12"), tag)


class Throttle(unittest.TestCase):
    def test_once_a_day(self):
        now = 1_000_000_000
        self.assertTrue(uc.due(0, now))  # never checked
        self.assertFalse(uc.due(now - 3600, now))  # an hour ago
        self.assertFalse(uc.due(now - uc.DAY + 1, now))
        self.assertTrue(uc.due(now - uc.DAY, now))
        self.assertTrue(uc.due(now + 5000, now))  # clock moved back: do not wait forever


class Fetch(unittest.TestCase):
    def fetch(self, result=None, error=None):
        with mock.patch("urllib.request.urlopen", side_effect=error, return_value=result) as m:
            out = uc.fetch_latest()
        return out, m

    def test_good_answer(self):
        out, m = self.fetch(answer())
        self.assertEqual(out, ("v9.9.9", PAGE))
        req = m.call_args.args[0]
        self.assertEqual(req.full_url, uc.API)
        self.assertEqual(req.get_header("User-agent"), "Convert-update-check")  # generic: no version, no user
        self.assertEqual(m.call_args.kwargs["timeout"], uc.TIMEOUT)
        self.assertIsNone(req.data)  # a GET with nothing sent

    def test_every_problem_is_silence(self):
        bad = [answer(draft=True), answer(prerelease=True), answer(tag_name="nightly"), answer(tag_name=7),
               answer(html_url="https://evil.example/releases/tag/v9.9.9"),
               answer(html_url=uc.PAGE_PREFIX.replace("github.com", "github.com.evil.example")),
               answer(html_url=None), Resp(b"not json"), Resp(b"\xff\xfe"), Resp(b"[1, 2]"), Resp(b"null")]
        for r in bad:
            self.assertIsNone(self.fetch(r)[0])
        for err in (urllib.error.HTTPError(uc.API, 403, "rate limit", {}, None), urllib.error.URLError("offline"),
                    socket.timeout("slow"), ConnectionResetError(), OSError("x")):
            self.assertIsNone(self.fetch(error=err)[0], repr(err))

    def test_non_200_is_ignored(self):
        r = answer()
        r.status = 304
        self.assertIsNone(self.fetch(r)[0])

    def test_url_returned_only_when_newer(self):
        with mock.patch.object(uc, "fetch_latest", return_value=("v0.1.13", PAGE)):
            self.assertEqual(uc.newer_release_url("0.1.12"), PAGE)
            self.assertIsNone(uc.newer_release_url("0.1.13"))
        with mock.patch.object(uc, "fetch_latest", return_value=None):
            self.assertIsNone(uc.newer_release_url("0.1.12"))

    def test_safe_page(self):
        self.assertTrue(uc.safe_page(PAGE))
        for u in ("", None, "http://github.com/TheCreator0169/convert/releases/", "file:///C:/Windows/System32/calc.exe",
                  "https://github.com/TheCreator0169/other/releases/tag/v1"):
            self.assertFalse(uc.safe_page(u), u)


if __name__ == "__main__":
    unittest.main()
