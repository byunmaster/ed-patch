import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_name_echo as c


class Echo(unittest.TestCase):
    def test_catches(self):
        self.assertEqual(c.echo("<1e>남자<04><01>남자는 말했다."), "남자")

    def test_clean(self):
        self.assertIsNone(c.echo("<1e>남자<04><01>아, 왕자님."))
        self.assertIsNone(c.echo("그냥 본문"))


if __name__ == "__main__":
    unittest.main()
