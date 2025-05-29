import io
import contextlib
import unittest
from src.main import main

class TestHelloWorldAction(unittest.TestCase):

    def test_hello_world_output(self):
        with io.StringIO() as stdout, contextlib.redirect_stdout(stdout):
            main()
            output = stdout.getvalue().strip()
        self.assertEqual(output, "Hello, World!")

if __name__ == '__main__':
    unittest.main()