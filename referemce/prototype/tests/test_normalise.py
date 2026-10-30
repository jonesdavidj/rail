"""Parser tests. Fixtures follow the documented Darwin LDBWS JSON shape
(trainServices / std / etd / subsequentCallingPoints / callingPoint ...).
They are not captured from the live service."""
import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server as S  # noqa: E402

NOW = datetime(2026, 10, 29, 18, 0, tzinfo=S.LONDON)


def cp(name, crs, st, et="On time", **kw):
    return {"locationName": name, "crs": crs, "st": st, "et": et, "isCancelled": False, **kw}


def svc(std, etd="On time", stops=None, **kw):
    base = {"std": std, "etd": etd, "platform": "3", "operator": "South Western Railway", "operatorCode": "SW",
            "isCancelled": False, "serviceType": "train", "serviceID": "id" + std,
            "origin": [{"locationName": "Surbiton", "crs": "SUR"}],
            "destination": [{"locationName": "London Waterloo", "crs": "WAT"}],
            "subsequentCallingPoints": [{"callingPoint": stops or [
                cp("Clapham Junction", "CLJ", "18:14"), cp("London Waterloo", "WAT", "18:22")]}]}
    base.update(kw)
    return base


class Normalise(unittest.TestCase):
    def one(self, raw):
        services, _ = S.normalise_board({"trainServices": [raw]}, "WAT", NOW)
        return services[0]

    def test_on_time(self):
        s = self.one(svc("18:05"))
        self.assertEqual((s["status"], s["planned"], s["expected"], s["in_min"]), ("on_time", "18:05", None, 5))
        self.assertEqual(s["arrival"]["planned"], "18:22")
        self.assertEqual(s["stop_count"], 1)
        self.assertEqual(s["platform"], "3")

    def test_late_with_estimates(self):
        s = self.one(svc("18:05", "18:12", [cp("Clapham Junction", "CLJ", "18:14", "18:21"),
                                           cp("London Waterloo", "WAT", "18:22", "18:29")]))
        self.assertEqual((s["status"], s["delay_min"], s["expected"]), ("late", 7, "18:12"))
        self.assertEqual((s["arrival"]["planned"], s["arrival"]["expected"]), ("18:22", "18:29"))

    def test_delayed_unknown(self):
        s = self.one(svc("18:05", "Delayed", delayReason="Trespassers on the railway"))
        self.assertEqual(s["status"], "delayed")
        self.assertEqual(s["reason"], "Trespassers on the railway")

    def test_cancelled(self):
        s = self.one(svc("18:05", "Cancelled", isCancelled=True, cancelReason="Crew shortage <b>today</b>"))
        self.assertEqual(s["status"], "cancelled")
        self.assertEqual(s["reason"], "Crew shortage today")

    def test_part_cancelled(self):
        s = self.one(svc("18:05", filterLocationCancelled=True))
        self.assertEqual(s["status"], "part_cancelled")
        self.assertTrue(s["arrival"]["cancelled"])

    def test_no_platform(self):
        self.assertIsNone(self.one(svc("18:05", platform=None))["platform"])

    def test_length_from_service_or_calling_point(self):
        self.assertEqual(self.one(svc("18:05", length=10))["length"], 10)
        stops = [cp("Clapham Junction", "CLJ", "18:14"), cp("London Waterloo", "WAT", "18:22", length=8)]
        self.assertEqual(self.one(svc("18:05", stops=stops))["length"], 8)
        self.assertIsNone(self.one(svc("18:05"))["length"])

    def test_midnight_rollover(self):
        late = datetime(2026, 10, 29, 23, 50, tzinfo=S.LONDON)
        services, _ = S.normalise_board({"trainServices": [svc("00:05", "00:12")]}, "WAT", late)
        self.assertEqual(services[0]["in_min"], 15)
        self.assertEqual(services[0]["delay_min"], 7)

    def test_stops_truncated_at_destination(self):
        stops = [cp("Clapham Junction", "CLJ", "18:14"), cp("London Waterloo", "WAT", "18:22"),
                 cp("Beyond", "BYD", "18:40")]
        s = self.one(svc("18:05", stops=stops))
        self.assertEqual([x["crs"] for x in s["stops"]], ["CLJ", "WAT"])

    def test_skips_service_change_groups(self):
        raw = svc("18:05")
        raw["subsequentCallingPoints"] = [
            {"serviceChangeRequired": True, "callingPoint": [cp("Wrong", "WRG", "18:10")]},
            {"callingPoint": [cp("London Waterloo", "WAT", "18:22")]}]
        self.assertEqual(self.one(raw)["arrival"]["planned"], "18:22")

    def test_bus_and_non_train_ignored(self):
        services, _ = S.normalise_board({"trainServices": [svc("18:05", serviceType="bus"), svc("18:10")]}, "WAT", NOW)
        self.assertEqual(len(services), 1)

    def test_empty_and_error_boards(self):
        self.assertEqual(S.normalise_board({}, "WAT", NOW)[0], [])
        with self.assertRaises(ValueError):
            S.normalise_board({"fault": {"faultstring": "bad"}}, "WAT", NOW)
        with self.assertRaises(ValueError):
            S.normalise_board({"trainServices": "nope"}, "WAT", NOW)

    def test_messages_stripped(self):
        _, msgs = S.normalise_board({"trainServices": [], "nrccMessages": [{"value": "<p>Delays &amp; cancellations</p>"}]}, "WAT", NOW)
        self.assertEqual(msgs, ["Delays & cancellations"])


class Paging(unittest.TestCase):
    def test_cursor(self):
        from datetime import timedelta
        raw = [svc((NOW + timedelta(minutes=5 + i * 8)).strftime("%H:%M")) for i in range(9)]
        services, _ = S.normalise_board({"trainServices": raw}, "WAT", NOW)
        page = S.build_page(services, [], 0, 7, NOW)
        self.assertEqual(len(page["services"]), 7)
        self.assertTrue(page["has_next"])
        self.assertEqual(page["next_offset"], page["services"][-1]["in_min"] + 1)

    def test_no_next_when_few(self):
        services, _ = S.normalise_board({"trainServices": [svc("18:05")]}, "WAT", NOW)
        self.assertFalse(S.build_page(services, [], 0, 7, NOW)["has_next"])

    def test_next_capped_at_max_offset(self):
        raw = [svc(f"19:{50 + i:02d}") for i in range(9)] if False else [svc(f"19:{i:02d}") for i in range(52, 60)] + [svc("20:00"), svc("20:01")]
        services, _ = S.normalise_board({"trainServices": raw}, "WAT", NOW)
        page = S.build_page(services, [], 110, 7, NOW)
        self.assertFalse(page["has_next"] and page["next_offset"] > S.MAX_OFFSET)


class MockMode(unittest.TestCase):
    def test_mock_goes_through_real_parser(self):
        for route in S.ROUTES:
            raw = S.mock_board(route, 0, NOW)
            services, _ = S.normalise_board(raw, S.ROUTES[route]["to"], NOW)
            self.assertGreaterEqual(len(services), 7)
            kinds = {s["status"] for s in services}
            self.assertTrue({"on_time", "late"} <= kinds)
            self.assertTrue(all(s["arrival"] for s in services))


class Safety(unittest.TestCase):
    def test_rejects_foreign_host(self):
        with self.assertRaises(S.UpstreamError):
            S.fetch_board("https://evil.example.com/x", "k", "SUR", "WAT", 0)
        with self.assertRaises(S.UpstreamError):
            S.fetch_board("http://api1.raildata.org.uk/x", "k", "SUR", "WAT", 0)


if __name__ == "__main__":
    unittest.main(verbosity=1)
