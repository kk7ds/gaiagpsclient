import copy
import datetime
import mock
import os
import pytz
import unittest

from gaiagps import util


class TestUtilUnit(unittest.TestCase):
    @mock.patch('tzlocal.get_localzone')
    def test_date_parse(self, mock_get_localzone):
        hill_valley = pytz.timezone('America/Los_Angeles')
        mock_get_localzone.return_value = hill_valley

        expected = hill_valley.localize(
            datetime.datetime(2015, 10, 21, 16, 29))
        formats = ['2015-10-21T23:29:00Z',
                   '2015-10-21T23:29:00.00',
                   '2015-10-21T23:29:00']
        for i in formats:
            self.assertEqual(expected,
                             util.date_parse({'time_created': i}))
            self.assertEqual(expected,
                             util.date_parse({'properties': {
                                 'time_created': i}}))

    @mock.patch('tzlocal.get_localzone')
    def test_datefmt(self, mock_get_localzone):
        hill_valley = pytz.timezone('America/Los_Angeles')
        mock_get_localzone.return_value = hill_valley

        expected = '21 Oct 2015 16:29:00'
        formats = ['2015-10-21T23:29:00Z',
                   '2015-10-21T23:29:00.00',
                   '2015-10-21T23:29:00']
        for i in formats:
            self.assertEqual(expected,
                             util.datefmt({'time_created': i}))
            self.assertEqual(expected,
                             util.datefmt({'properties': {'time_created': i}}))

    def test_title_sort(self):
        self.assertEqual([{'title': 'abc'}, {'title': 'def'}],
                         util.title_sort([
                             {'title': 'def'}, {'title': 'abc'}]))

    def test_name_sort(self):
        self.assertEqual([{'name': 'abc'}, {'name': 'def'}],
                         util.name_sort([
                             {'name': 'def'}, {'name': 'abc'}]))

    def test_is_id(self):
        ids = ['0b00901f6549abf8a8b7de8b49d24894',
               '0c94be3d-6fd9-45a0-9ca5-e8fd6969b7d3']
        not_ids = ['0b00901f6549abf8a8b7de8b49d2489z',
                   '0c94be3d-6fd9-45a0-9ca5-e8fd6969b7dz',
                   '0b00901f6549abf8a8b7de8b49d2489',
                   '0b00901f6549abf8a8b7de8b49d248933',
                   '0c94be3d-6fd9-45a0-9ca5:e8fd6969b7dz',
                   '0c94be3d-6fd9-45a0-9ca5 e8fd6969b7dz',
                   'This is a name',
                   'name']

        for i in ids:
            self.assertTrue(util.is_id(i))

        for i in not_ids:
            self.assertFalse(util.is_id(i))

    def test_validate_lat(self):
        valid = ['45.123', '1.2', '0.1', '-45.123', '0.0', '-0.1']
        invalid = ['45.a', 'foo', '-foo', '90.1', '97', '-122', '']

        for i in valid:
            self.assertIsInstance(util.validate_lat(i), float)

        for i in invalid:
            self.assertRaises(ValueError, util.validate_lat, i)

    def test_validate_lon(self):
        valid = ['45.123', '1.2', '0.1', '120', '-120.123', '0.0', '-0.1']
        invalid = ['45.a', 'foo', '-foo', '190.1', '197', '-181', '']

        for i in valid:
            self.assertIsInstance(util.validate_lon(i), float)

        for i in invalid:
            self.assertRaises(ValueError, util.validate_lon, i)

    def test_validate_alt(self):
        valid = ['0', '1', '900']
        invalid = ['a', 'foo', '', '-1', '-0.1', '1.2']

        for i in valid:
            self.assertIsInstance(util.validate_alt(i), int)

        for i in invalid:
            self.assertRaises(ValueError, util.validate_alt, i)

    def _test_folders(self):
        folders = [
            {'id': '1', 'parent': None, 'name': 'root1', 'properties': {
                'waypoints': ['100', '101'], 'tracks': ['200', '201']}},
            {'id': '2', 'parent': '3', 'name': 'subfolder', 'properties': {
                'waypoints': ['102'], 'tracks': []}},
            {'id': '3', 'parent': None, 'name': 'root2', 'properties': {
                'waypoints': [], 'tracks': []}},
            {'id': '4', 'parent': '2', 'name': 'subsub', 'properties': {
                'waypoints': [], 'tracks': ['202']}},
        ]
        return folders

    def test_make_tree(self):
        tree = util.make_tree(self._test_folders())

        self.assertEqual('/', tree['properties']['name'])
        self.assertEqual({}, tree['properties']['waypoints'])
        self.assertEqual({}, tree['properties']['tracks'])
        self.assertEqual(['1', '3'],
                         list(sorted(tree['subfolders'].keys())))

        self.assertEqual(['100', '101'],
                         tree['subfolders']['1']['properties']['waypoints'])
        self.assertEqual(['200', '201'],
                         tree['subfolders']['1']['properties']['tracks'])

        sf = tree['subfolders']['3']['subfolders']['2']
        self.assertEqual([],
                         sf['subfolders']['4']['properties']['waypoints'])
        self.assertEqual(['202'],
                         sf['subfolders']['4']['properties']['tracks'])

        return tree

    def _test_resolve_tree(self):
        folders = self._test_folders()
        full_folders = {i['id']: copy.deepcopy(i) for i in folders}
        for folder in full_folders.values():
            folder['properties']['name'] = folder.pop('name')
            folder['properties']['waypoints'] = [
                {'id': i,
                 'title': 'waypoint_%s' % i,
                 'properties': {}}
                for i in folder['properties']['waypoints']]
            folder['properties']['tracks'] = [
                {'id': i,
                 'title': 'track_%s' % i,
                 'properties': {}}
                for i in folder['properties']['tracks']]

        fake_client = mock.MagicMock()
        fake_client.get_object.side_effect = lambda t, id_: full_folders[id_]
        fake_client.list_objects.return_value = [{'title': 'testdata',
                                                  'properties': {},
                                                  'folder': ''}]

        tree = util.make_tree(folders)
        resolved = util.resolve_tree(fake_client, tree)
        return resolved

    def test_resolve_tree(self):
        resolved = self._test_resolve_tree()
        sub = resolved['subfolders']['3']['subfolders']['2']
        self.assertEqual(
            [{'id': '102', 'title': 'waypoint_102', 'properties': {}}],
            sub['properties']['waypoints'])
        subsub = sub['subfolders']['4']
        self.assertEqual(
            [{'id': '202', 'title': 'track_202', 'properties': {}}],
            subsub['properties']['tracks'])

    def test_pprint_folder(self):
        resolved = self._test_resolve_tree()
        with mock.patch('builtins.print') as mock_print:
            util.pprint_folder(resolved)

        lines = []
        for call in mock_print.call_args_list:
            lines.append(call[0][0] if call[0] else '')

        output = ''.join(lines)

        # Check some things at the root and at the leaves for proper
        # nesting
        self.assertIn('root1/', output)
        self.assertIn('[W] testdata', output)
        self.assertIn('subsub/', output)
        self.assertIn('[T] track_202', output)

    @mock.patch('os.environ')
    @mock.patch('os.access')
    def test_get_editor(self, mock_access, mock_environ):
        mock_access.return_value = True
        mock_environ.get.return_value = '/foo/bar'

        # Editor exists, should return it
        editor = util.get_editor()
        self.assertEqual('/foo/bar', editor)
        mock_environ.get.assert_called_once_with('EDITOR',
                                                 '/usr/bin/editor')
        mock_access.assert_called_once_with('/foo/bar', os.X_OK)

        # Does not exist or not executable
        mock_access.return_value = False
        editor = util.get_editor()
        self.assertIsNone(editor)
