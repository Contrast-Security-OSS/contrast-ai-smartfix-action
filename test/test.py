import io
import contextlib
import unittest
from main import main

class TestSmartFixAction(unittest.TestCase):

    def test_main_output(self):
        with io.StringIO() as stdout, contextlib.redirect_stdout(stdout):
            main()
            output = stdout.getvalue().strip()
        self.assertIn("--- Starting Contrast AI SmartFix Script ---", output)

if __name__ == '__main__':
    unittest.main()