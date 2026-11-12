from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SHARED = Path(__file__).resolve().parents[1] / "scr_Radar_V1/compartido_Radar_V1"
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

from facebook_data_contract_Radar_V1 import project_facebook_row
from facebook_historical_contract_Radar_V1 import load_historical_facebook_rows, row_from_exclusion


class FacebookHistoricalContractTests(unittest.TestCase):
    WEEK = "2026-04-06_semana_06abril_12abril_26_Radar_V1"

    def record(self, date="Desconocida", reason="date_unknown"):
        original = {"tipo": "POST", "cuenta": "tampicogob", "url": "https://facebook.com/TampicoGob/posts/1",
                    "post_url_padre": "", "fecha": date, "texto": "Original", "num_comentarios": "0"}
        projected, _ = project_facebook_row(original, schema="canonical")
        record = {"source_week": self.WEEK, "source_sha256": "a" * 64, "source_record": 1,
                  "reason": reason, "original": original, "projected": projected}
        record["accepted_row"] = row_from_exclusion(record)
        return record

    def test_keeps_original_unknown_blank_and_relative_dates(self):
        for date, reason in (("Desconocida", "date_unknown"), ("", "date_unknown"), ("767h", "date_invalid")):
            with self.subTest(date=date):
                self.assertEqual(row_from_exclusion(self.record(date, reason))["fecha"], date)

    def test_rejects_other_reasons_and_absolute_dates(self):
        record = self.record()
        for reason in ("date_outside_week", "duplicates", "orphan_comments"):
            with self.assertRaises(ValueError):
                row_from_exclusion({**record, "reason": reason})
        with self.assertRaises(ValueError):
            row_from_exclusion({**record, "original": {**record["original"], "fecha": "2026-04-10"}})

    def test_registry_checks_week_projection_and_provenance_multiplicity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / self.WEEK / "facebook_reincorporado_Radar_V1.jsonl"
            path.parent.mkdir()
            record = self.record()
            path.write_text(json.dumps(record) + "\n")
            self.assertEqual(load_historical_facebook_rows(self.WEEK, root), [record["accepted_row"]])
            self.assertEqual(load_historical_facebook_rows("2026-04-13_semana_13abril_19abril_26_Radar_V1", root), [])
            for invalid in (
                {**record, "source_week": "otra_semana"},
                {**record, "accepted_row": {**record["accepted_row"], "fecha": "2026-04-10"}},
                {**record, "source_sha256": ""},
            ):
                path.write_text(json.dumps(invalid) + "\n")
                with self.assertRaises(ValueError):
                    load_historical_facebook_rows(self.WEEK, root)
            path.write_text((json.dumps(record) + "\n") * 2)
            with self.assertRaises(ValueError):
                load_historical_facebook_rows(self.WEEK, root)


if __name__ == "__main__":
    unittest.main()
