from pathlib import Path
import tempfile
import unittest
from store import load, save


class StoreTests(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "records.data"
            values = {"name": "bread", "quantity": 2}
            save(path, values)
            self.assertEqual(load(path), values)


if __name__ == "__main__":
    unittest.main()
