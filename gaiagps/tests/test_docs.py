import mock
import os
import shlex
import unittest

from gaiagps import shell


class TestDocSnippetsUnit(unittest.TestCase):
    def _get_invocations(self, filename):
        key = '  $ gaiagps '
        with open(filename) as f:
            return [(i + 1, l[len(key):].strip())
                    for i, l in enumerate(f.readlines())
                    if l.startswith(key)]

    def _doc_file(self, name):
        return os.path.join(
            os.path.dirname(os.path.abspath(__file__)),  # /gaiagps/tests
            '..',                                        # /gaiagps
            '..',                                        # /
            'doc',                                       # /doc
            'source',                                    # /doc/source
            name)                                        # /doc/source/$name

    @mock.patch('gaiagps.apiclient.GaiaClient')
    @mock.patch('gaiagps.shell.command.Command.dispatch')
    @mock.patch('sys.stdin.fileno')
    def _test_invocation(self, location, command, mock_fileno, mock_dispatch,
                         mock_client):
        # For --user, we will check for is-terminal on stdin
        mock_fileno.return_value = -1

        # Return an impossible sentinel from any command
        mock_dispatch.return_value = 123456

        # Assert we ran the actual command and didn't fail in the parser
        self.assertEqual(123456, shell.main(shlex.split(command)),
                         '%s: Failed to test command invocation: %r' % (
                             location, command))

    def _test_doc_file(self, filename):
        lines = self._get_invocations(self._doc_file(filename))
        self.assertNotEqual(0, len(lines),
                            'No commands matched in %r' % filename)
        for number, line in lines:
            self._test_invocation('%s:%i' % (filename, number), line)

    def test_cli(self):
        self._test_doc_file('cli.rst')

    def test_install(self):
        self._test_doc_file('install.rst')
