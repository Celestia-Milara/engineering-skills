import unittest
from prices import total


class PriceTests(unittest.TestCase):
    def test_total(self):
        self.assertEqual(total([10, 20]), 30)


if __name__ == "__main__":
    unittest.main()
