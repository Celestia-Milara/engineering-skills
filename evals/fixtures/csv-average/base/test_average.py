from pathlib import Path
import tempfile
import unittest
from average import average


class AverageTests(unittest.TestCase):
    def test_nonempty(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "values.csv"
            path.write_text("2\n4\n", encoding="utf-8")
            self.assertEqual(average(path), 3)


if __name__ == "__main__":
    unittest.main()
