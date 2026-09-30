import unittest

from counter import increment


class CounterTests(unittest.TestCase):
    def test_increment(self):
        self.assertEqual(increment(4), 5)


if __name__ == "__main__":
    unittest.main()
