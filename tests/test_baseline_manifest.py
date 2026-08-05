import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "create_baseline_manifest.py"
SPEC = importlib.util.spec_from_file_location("create_baseline_manifest", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class BaselineManifestTests(unittest.TestCase):
    def test_csv_row_count_and_sha_are_stable(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.csv"
            path.write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
            self.assertEqual(MODULE.csv_row_count(path), 2)
            first = MODULE.sha256_file(path)
            second = MODULE.sha256_file(path)
            self.assertEqual(first, second)
            self.assertEqual(len(first), 64)

    def test_compare_detects_identical_minimal_manifests(self):
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            canonical = {
                name: {"row_count": 1, "sha256": f"hash-{index}"}
                for index, name in enumerate(MODULE.CANONICAL_OUTPUTS)
            }
            manifest = {
                "repository": {"commit_sha": "abc"},
                "inputs": [{"sha256": "input"}],
                "active_configuration": [{"sha256": "config"}],
                "canonical_outputs": canonical,
                "key_metrics": {"funnel": {"rows": 1}},
            }
            first = tmp / "first.json"
            second = tmp / "second.json"
            report = tmp / "report.json"
            first.write_text(json.dumps(manifest), encoding="utf-8")
            second.write_text(json.dumps(manifest), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable, str(SCRIPT), "compare",
                    "--first", str(first), "--second", str(second),
                    "--output", str(report), "--require-canonical-hashes",
                ],
                check=False,
            )
            self.assertEqual(result.returncode, 0)
            self.assertEqual(json.loads(report.read_text())["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
