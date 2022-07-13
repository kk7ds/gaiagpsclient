import contextlib
import copy
import datetime
import io
import mock
import os
import pprint
import shlex
import tempfile
import time
import unittest

from gaiagps import apiclient
from gaiagps import shell
from gaiagps.tests import test_apiclient
from gaiagps.tests import test_util
from gaiagps import util


client = apiclient.GaiaClient
_test_name = test_apiclient._test_name


class FakeOutput(io.StringIO):
    def fileno(self):
        return -1


class FakeClient(object):
    FOLDERS = [
        {'id': '101', 'folder': '', 'title': 'folder1'},
        {'id': '102', 'folder': '', 'title': 'folder2'},
        {'id': '103', 'folder': '101', 'title': 'subfolder'},
        {'id': '104', 'folder': '', 'title': 'emptyfolder'},
        ]
    WAYPOINTS = [
        {'id': '001', 'folder': '', 'title': 'wpt1'},
        {'id': '002', 'folder': '101', 'title': 'wpt2', 'deleted': True},
        {'id': '003', 'folder': '103', 'title': 'wpt3',
         'properties': {'time_created': '2015-10-21T23:29:00Z',
                        'icon': 'foo',
                        'notes': '',
                        'public': False,
                        'title': 'wpt3',
                        'revision': 6}},
    ]
    TRACKS = [
        {'id': '201', 'folder': '', 'title': 'trk1',
         'features': [{
             'properties': {'title': 'trk1',
                            'color': '#FF0000',
                            'public': False,
                            'revision': 6,
                            'activities': ['hiking'],
                            'notes': ''},
            }]},
        {'id': '202', 'folder': '102', 'title': 'trk2'},
    ]
    PHOTOS = [
        {'id': '301', 'title': 'pho1',
         'time_created': '2019-05-26T21:02:34Z',
         'properties': {
             'fullsize_url': 'https://foo.com/photo1/full',
             'scaled_url': 'https://foo.com/photo1/scaled',
             'thumbnail': 'https://foo.com/photo1/thumbnail',
         }},
        {'id': '302', 'title': 'pho2',
         'properties': {
             'fullsize_url': 'https://foo.com/photo2/full',
             'scaled_url': 'https://foo.com/photo2/scaled',
             'thumbnail': 'https://foo.com/photo2/thumbnail',
         }},
    ]

    s = None

    def __init__(self, *a, **k):
        pass

    def list_objects(self, objtype, archived=True):
        def add_props(items):
            return [dict(d,
                         properties=d.get('properties',
                                          {'time_created':
                                           '2019-01-01T02:03:04Z'}),
                         deleted=d.get('deleted', False))
                    for d in items
                    if archived or d.get('deleted', False) is False]

        if objtype == 'waypoint':
            return add_props(self.WAYPOINTS)
        elif objtype == 'track':
            return add_props(self.TRACKS)
        elif objtype == 'photo':
            return self.PHOTOS
        elif objtype == 'folder':
            r = []
            for f in self.FOLDERS:
                r.append(dict(f,
                              parent=f['folder'] or None,
                              properties={'time_created':
                                          '2019-01-01T02:03:04Z'},
                              maps=[],
                              waypoints=[w['id'] for w in self.WAYPOINTS
                                         if w['folder'] == f['id']],
                              tracks=[t['id'] for t in self.TRACKS
                                      if t['folder'] == f['id']],
                              children=[s['id'] for s in self.FOLDERS
                                        if s['folder'] == f['id']]))
            return r
        else:
            raise Exception('Invalid type %s' % objtype)

    def get_object(self, objtype, name=None, id_=None, fmt=None):
        def add_props(o):
            o = copy.deepcopy(o)
            if o['title'].startswith('trk'):
                p = o.get('features', list([dict()]))[0]
            else:
                p = o
            p.setdefault('properties',
                         {'time_created':
                          '2019-01-01T02:03:04Z'})
            p.setdefault('deleted', False)
            return o

        if name:
            key = 'title'
            value = name
        else:
            key = 'id'
            value = id_

        lst = getattr(self, objtype.upper() + 'S')
        obj = dict(apiclient.find(lst, key, value))

        if fmt is not None:
            return 'object %s format %s' % (obj['id'], fmt)

        key = 'name' if objtype == 'folder' else 'title'
        obj = copy.deepcopy(obj)
        obj.setdefault('properties', {})
        obj['properties'][key] = obj.pop('title')
        obj['properties']['time_created'] = obj['properties'].get(
            'time_created', '2019-01-01T02:03:04Z')
        if objtype == 'waypoint':
            obj['geometry'] = {'coordinates': [-122.0, 45.5, 123]}
        elif objtype == 'folder':
            obj['properties']['trackstats'] = {}
            obj['properties']['waypoints'] = [
                add_props(w) for w in self.WAYPOINTS
                if w['folder'] == obj['id']]
            obj['properties']['tracks'] = [
                add_props(t) for t in self.TRACKS
                if t['folder'] == obj['id']]
        return obj

    def add_object_to_folder(self, folderid, objtype, objid):
        raise NotImplementedError('Mock me')

    def remove_object_from_folder(self, folderid, objtype, objid):
        raise NotImplementedError('Mock me')

    def delete_object(self, objtype, id_):
        raise NotImplementedError('Mock me')

    def put_object(self, objtype, objdata):
        raise NotImplementedError('Mock me')

    def create_object(self, objtype, objdata):
        raise NotImplementedError('Mock me')

    def upload_file(self, filename):
        raise NotImplementedError('Mock me')

    def set_objects_archive(self, objtype, ids, archive):
        raise NotImplementedError('Mock me')

    def test_auth(self):
        raise NotImplementedError('Mock me')

    def get_photo(self, photoid, size='fullsize'):
        photo = [x for x in self.PHOTOS if x['id'] == photoid][0]
        return ('image/jpeg', b'photodatafor%s' % photo['title'].encode())

    def get_access(self, folderid):
        return [{'admin': False,
                 'archived': False,
                 'create_date': '2019-06-03T16:42:24.107000',
                 'folder': 'folder1',
                 'items_last_updated': '2019-06-02T22:36:11.008000',
                 'last_updated': '2019-06-03T16:42:24.107000',
                 'permanently_deleted': False,
                 'unique_id': '37c3bf74-ee54-4420-8dbc-552b17254efb',
                 'user_displayname': 'myuser',
                 'user_username': 'bar@foo.com',
                 'write': True},
                {'admin': True,
                 'archived': False,
                 'create_date': '2019-06-03T16:42:24.107000',
                 'folder': 'folder1',
                 'items_last_updated': '2019-06-02T22:36:11.008000',
                 'last_updated': '2019-06-03T16:42:24.107000',
                 'permanently_deleted': False,
                 'unique_id': '37c3bf74-ee54-4420-8dbc-552b17254efb',
                 'user_displayname': 'myadmin',
                 'user_username': 'bardmin@foo.com',
                 'write': False}]

    def get_invites(self, folderid):
        return [{'accepted': None,
                 'admin_access': False,
                 'expires': '2019-07-03T18:29:50.748834',
                 'folder': 'folder1',
                 'folder_id': '101',
                 'folder_name': 'folder1',
                 'id': 4567,
                 'invited_by': 1234,
                 'message': None,
                 'responded_at': None,
                 'sender_name': 'sender',
                 'sender_username': 'sender@foo.com',
                 'sent_at': '2019-06-03T18:29:50.748834',
                 'to_email': 'foo@bar.com',
                 'to_user': 9800,
                 'write_access': False}]


@contextlib.contextmanager
def fake_cookiejar():
    yield None


# This is a fake implementation of util.is_id which relies on our
# convention here of using three-digit integer strings as IDs
def fake_is_id(name_or_id):
    return len(name_or_id) == 3 and name_or_id.isdigit()


@mock.patch('gaiagps.shell.cookiejar', new=fake_cookiejar)
@mock.patch.object(apiclient, 'GaiaClient', new=FakeClient)
class TestShellUnit(unittest.TestCase):
    def _run(self, cmdline, expect_fail=False):
        out = FakeOutput()
        with mock.patch.multiple('sys', stdout=out, stderr=out, stdin=out):
            rc = shell.main(shlex.split(cmdline))
        print(out.getvalue())
        if not expect_fail:
            self.assertEqual(0, rc)
        else:
            self.assertNotEqual(0, rc)
        return out.getvalue()

    def test_first_run(self):
        out = self._run('', expect_fail=True)
        self.assertIn('usage:', out)

    def test_waypoint_list_icons(self):
        out = self._run('waypoint list-icons')
        self.assertIn('chemist (chemist-24.png)', out)

    def test_waypoint_list_by_id(self):
        out = self._run('waypoint list --by-id')
        self.assertIn('001', out)
        self.assertIn('wpt2', out)

    def test_list_wpt(self):
        out = self._run('waypoint list')
        self.assertIn('wpt1', out)
        self.assertIn('wpt2', out)
        self.assertIn('wpt3', out)
        self.assertIn('folder1', out)
        self.assertIn('subfolder', out)
        self.assertNotIn('folder2', out)

    @mock.patch('gaiagps.util.is_id', new=lambda i: True)
    def test_list_formatted(self):
        out = self._run('waypoint list --match wpt1 '
                        '--format "%(title)s"')
        self.assertEqual('wpt1', out.strip())

    def test_list_format_help(self):
        out = self._run('waypoint list --format=help')
        self.assertIn('format takes', out)

    def test_list_trk(self):
        out = self._run('track list')
        self.assertIn('trk1', out)
        self.assertIn('trk2', out)
        self.assertIn('folder2', out)
        self.assertNotIn('folder1', out)
        self.assertNotIn('subfolder', out)

    def test_list_match(self):
        out = self._run('waypoint list --match w.*2')
        self.assertIn('wpt2', out)
        self.assertNotIn('wpt1', out)

    def test_list_match_date(self):
        out = self._run('waypoint list --match-date 2019-03-14')
        self.assertNotIn('wpt1', out)
        self.assertNotIn('wpt2', out)
        self.assertNotIn('wpt3', out)

        out = self._run('waypoint list --match-date 2015-10-21')
        self.assertNotIn('wpt1', out)
        self.assertNotIn('wpt2', out)
        self.assertIn('wpt3', out)

        out = self._run('waypoint list --match-date 2015-10-21:2015-10-22')
        self.assertNotIn('wpt1', out)
        self.assertNotIn('wpt2', out)
        self.assertIn('wpt3', out)

        out = self._run('waypoint list --match-date 2016-01-01:')
        self.assertIn('wpt1', out)
        self.assertIn('wpt2', out)
        self.assertNotIn('wpt3', out)

        out = self._run('waypoint list --match-date :2016-01-01')
        self.assertNotIn('wpt1', out)
        self.assertNotIn('wpt2', out)
        self.assertIn('wpt3', out)

        out = self._run('waypoint list --match-date foo',
                        expect_fail=True)
        self.assertIn('foo\' does not match format', out)
        out = self._run('waypoint list --match-date 2015-10-21:foo',
                        expect_fail=True)
        self.assertIn('foo\' does not match format', out)
        out = self._run('waypoint list --match-date foo:2015-10-21',
                        expect_fail=True)
        self.assertIn('foo\' does not match format', out)

    @mock.patch.object(FakeClient, 'list_objects')
    def test_list_archived_include_logic(self, mock_list):
        self._run('waypoint list')
        mock_list.assert_called_once_with('waypoint', archived=True)

        mock_list.reset_mock()
        self._run('waypoint list --archived=no')
        mock_list.assert_called_once_with('waypoint', archived=False)

        mock_list.reset_mock()
        self._run('waypoint list --archived=yes')
        mock_list.assert_called_once_with('waypoint', archived=True)

        mock_list.reset_mock()
        self._run('waypoint list --archived=foo',
                  expect_fail=True)
        mock_list.assert_not_called()

    def test_list_archived(self):
        out = self._run('waypoint list')
        self.assertIn('wpt1', out)
        self.assertIn('wpt2', out)

        out = self._run('waypoint list --archived=y')
        self.assertNotIn('wpt1', out)
        self.assertIn('wpt2', out)

        out = self._run('waypoint list --archived=n')
        self.assertIn('wpt1', out)
        self.assertNotIn('wpt2', out)

    def test_list_in_folder(self):
        # List a folder with contents
        out = self._run('waypoint list --in-folder folder1')
        self.assertNotIn('wpt1', out)
        self.assertIn('wpt2', out)

        # List the root
        out = self._run('waypoint list --in-folder ""')
        self.assertIn('wpt1', out)
        self.assertNotIn('wpt2', out)

        # List empty folder, no results
        out = self._run('waypoint list --in-folder folder2')
        self.assertNotIn('wpt1', out)
        self.assertNotIn('wpt2', out)

    @mock.patch.object(FakeClient, 'add_object_to_folder')
    def test_move(self, mock_add, verbose=False, dry=False):
        out = self._run('%s waypoint move wpt1 wpt2 folder2 %s' % (
            verbose and '--verbose' or '',
            dry and '--dry-run' or ''))
        if dry:
            mock_add.assert_not_called()
        else:
            mock_add.assert_has_calls([mock.call('102', 'waypoint', '001'),
                                       mock.call('102', 'waypoint', '002')])
        if verbose:
            self.assertIn('wpt1', out)
            self.assertIn('wpt2', out)
            self.assertIn('folder2', out)
            self.assertNotIn('wpt3', out)
            self.assertNotIn('folder1', out)
            self.assertNotIn('subfolder', out)
        elif dry:
            self.assertIn('Dry run', out)
        else:
            self.assertEqual('', out)

    def test_move_verbose(self):
        self.test_move(verbose=True)

    def test_move_dry_run(self):
        self.test_move(verbose=True, dry=True)

    @mock.patch.object(FakeClient, 'add_object_to_folder')
    def test_move_match(self, mock_add):
        self._run('waypoint move --match w.*2 folder2')
        mock_add.assert_has_calls([mock.call('102', 'waypoint', '002')])

    @mock.patch.object(FakeClient, 'add_object_to_folder')
    def test_move_match_date(self, mock_add):
        self._run('waypoint move --match-date 2015-10-21 folder2')
        mock_add.assert_called_once_with('102', 'waypoint', '003')

    @mock.patch.object(FakeClient, 'add_object_to_folder')
    def test_move_match_none(self, mock_add):
        out = self._run('waypoint move --match-date 2019-03-14 folder2',
                        expect_fail=True)
        self.assertIn('', out)
        mock_add.assert_not_called()

    @mock.patch.object(FakeClient, 'add_object_to_folder')
    def test_move_match_ambiguous(self, mock_add):
        out = self._run('--verbose waypoint move folder2',
                        expect_fail=True)
        self.assertIn('No items', out)
        mock_add.assert_not_called()

    @mock.patch.object(FakeClient, 'add_object_to_folder')
    def test_move_to_nonexistent_folder(self, mock_add):
        out = self._run('waypoint move wpt1 wpt2 foobar',
                        expect_fail=True)
        self.assertIn('foobar not found', out)
        mock_add.assert_not_called()

    @mock.patch.object(FakeClient, 'remove_object_from_folder')
    def test_move_to_root(self, mock_remove):
        out = self._run('waypoint move wpt1 wpt2 /')
        mock_remove.assert_has_calls([mock.call('101', 'waypoint', '002')])
        self.assertIn('\'wpt1\' is already at root', out)

    @mock.patch.object(FakeClient, 'add_object_to_folder')
    def test_move_in_folder_all(self, mock_add):
        self._run('--verbose waypoint move --in-folder folder1 folder2')
        mock_add.assert_called_once_with('102', 'waypoint', '002')

    @mock.patch.object(FakeClient, 'delete_object')
    def test_remove(self, mock_delete, dry=False):
        out = self._run('waypoint remove wpt1 wpt2 %s' % (
            dry and '--dry-run' or ''))
        if dry:
            self.assertIn('Dry run', out)
            mock_delete.assert_not_called()
        else:
            self.assertEqual('', out)
            mock_delete.assert_has_calls([mock.call('waypoint', '001'),
                                          mock.call('waypoint', '002')])

    def test_remove_dry_run(self):
        self.test_remove(dry=True)

    @mock.patch.object(FakeClient, 'delete_object')
    def test_remove_match_verbose(self, mock_delete):
        out = self._run('--verbose waypoint remove --match w.*2')
        self.assertIn('Removing waypoint \'wpt2\'', out)
        mock_delete.assert_has_calls([mock.call('waypoint', '002')])

    @mock.patch.object(FakeClient, 'delete_object')
    def test_remove_missing(self, mock_delete):
        out = self._run('--verbose waypoint remove wpt7',
                        expect_fail=True)
        self.assertIn('not found', out)
        mock_delete.assert_not_called()

    @mock.patch.object(FakeClient, 'delete_object')
    def test_remove_in_folder_all(self, mock_delete):
        out = self._run('--verbose waypoint remove --in-folder folder1')
        self.assertIn('wpt2', out)
        mock_delete.assert_called_once_with('waypoint', '002')

    @mock.patch.object(FakeClient, 'delete_object')
    def test_remove_in_folder_filter(self, mock_delete):
        out = self._run('--verbose waypoint remove --in-folder folder1 wpt2')
        self.assertIn('wpt2', out)
        mock_delete.assert_called_once_with('waypoint', '002')

        # If we limit to a folder and by name, make sure we take the
        # intersection and not the union
        mock_delete.reset_mock()
        out = self._run('--verbose waypoint remove --in-folder folder1 wpt1')
        self.assertEqual('', out)
        mock_delete.assert_not_called()

    @mock.patch.object(FakeClient, 'delete_object')
    def test_remove_nothing(self, mock_delete):
        self._run('waypoint remove')
        mock_delete.assert_not_called()

    @mock.patch.object(FakeClient, 'delete_object')
    def test_remove_folder_empty(self, mock_delete):
        out = self._run('--verbose folder remove emptyfolder')
        self.assertIn('Removing', out)
        mock_delete.assert_called_once_with('folder', '104')

    @mock.patch.object(FakeClient, 'delete_object')
    def test_remove_folder_nonempty(self, mock_delete):
        out = self._run('--verbose folder remove folder1')
        self.assertIn('skipping', out)
        mock_delete.assert_not_called()

    @mock.patch.object(FakeClient, 'delete_object')
    def test_remove_folder_nonempty_force(self, mock_delete):
        out = self._run('--verbose folder remove --force folder1')
        self.assertIn('Warning', out)
        mock_delete.assert_called_once_with('folder', '101')

    @mock.patch('builtins.input')
    @mock.patch('os.isatty', return_value=True)
    @mock.patch.object(FakeClient, 'delete_object')
    def test_remove_folder_nonempty_prompt(self, mock_delete, mock_tty,
                                           mock_input):
        mock_input.return_value = ''
        self._run('--verbose folder remove folder1')
        mock_delete.assert_not_called()

        mock_input.return_value = 'y'
        self._run('--verbose folder remove folder1')
        mock_delete.assert_called_once_with('folder', '101')

    @mock.patch.object(FakeClient, 'put_object')
    def test_rename_waypoint(self, mock_put, dry=False):
        out = self._run(
            '--verbose waypoint rename wpt2 wpt7 %s' % (
                dry and '--dry-run' or ''))
        self.assertIn('Renaming', out)
        new_wpt = {'id': '002', 'folder': '101',
                   'properties': {'title': 'wpt7',
                                  'time_created': '2019-01-01T02:03:04Z'},
                   'geometry': {'coordinates': [-122.0, 45.5, 123]},
                   'deleted': True}
        if dry:
            mock_put.assert_not_called()
        else:
            mock_put.assert_called_once_with('waypoint', new_wpt)

    def test_rename_dry_run(self):
        self.test_rename_waypoint(dry=True)

    @mock.patch.object(FakeClient, 'put_object')
    def test_rename_track(self, mock_put):
        out = self._run('--verbose track rename trk2 trk7')
        self.assertIn('Renaming', out)
        new_trk = {'id': '202', 'title': 'trk7'}
        mock_put.assert_called_once_with('track', new_trk)

    @mock.patch.object(FakeClient, 'put_object')
    @mock.patch('builtins.open')
    @mock.patch('yaml.dump')
    def test_edit_track_dump(self, mock_dump, mock_open, mock_put):
        out = self._run('track edit trk1')
        self.assertIn('Edit and then apply', out)
        mock_open.assert_called_once_with('tracks.yml', 'w')
        fake_file = mock_open.return_value.__enter__.return_value
        preamble = fake_file.write.call_args_list[0][0][0]
        self.assertIn('YAML document', preamble)
        self.assertIn('yellow', preamble)
        fake_file.write.assert_has_calls([mock.call(mock_dump.return_value)])
        mock_put.assert_not_called()

    @mock.patch.object(FakeClient, 'put_object')
    @mock.patch('builtins.open')
    @mock.patch('yaml.load')
    def test_edit_track_load(self, mock_load, mock_open, mock_put):
        mock_load.return_value = [{'id': '201',
                                   'features': [{
                                       'properties': {
                                           'color': 'red',
                                           'notes': '',
                                           'public': False,
                                           'title': 'newname',
                                           'activities': ['hiking', 'camping'],
                                           'revision': 6}}]}]
        out = self._run('track edit trk1 -f tracks.yml')
        self.assertEqual('', out)
        mock_open.assert_called_once_with('tracks.yml', 'r')
        fake_file = mock_open.return_value.__enter__.return_value
        fake_file.read.assert_called_once_with()
        mock_load.assert_called_once_with(fake_file.read.return_value)
        obj = FakeClient().get_object('track', 'trk1')
        expected = copy.deepcopy(obj['features'][0]['properties'])
        expected['title'] = 'newname'
        expected['color'] = '#F42410'
        expected['id'] = obj['id']
        expected['activities'] = ['hiking', 'camping']
        mock_put.assert_called_once_with('track', expected)

    @mock.patch.object(FakeClient, 'put_object')
    @mock.patch('builtins.open')
    @mock.patch('yaml.load')
    def test_edit_track_load_errors(self, mock_load, mock_open, mock_put):
        # User deleted revision
        mock_load.return_value = [{'id': '201',
                                   'features': [{
                                       'properties': {'title': 'val'}}]}]
        out = self._run('track edit trk1 -f track.yml')
        self.assertIn('changed on the server', out)

        # ID mismatch
        mock_load.return_value = [{'id': '202',
                                   'features': [{
                                       'properties': {'revision': 6,
                                                      'color': 'foo',
                                                      'notes': '',
                                                      'public': False,
                                                      'title': 'val'}}]}]
        out = self._run('--debug --verbose track edit trk1 -f track.yml')
        self.assertIn('id does not match', out)

        # User removed a value
        mock_load.return_value = [{'id': '201',
                                   'features': [{
                                       'properties': {'revision': 6,
                                                      'color': 'foo',
                                                      'public': False,
                                                      'title': 'val'}}]}]
        out = self._run('track edit trk1 -f track.yml',
                        expect_fail=True)
        self.assertIn('Deleting values', out)

        # Length mismatch between file and server query
        mock_load.return_value = [{'id': '201',
                                   'features': [{
                                       'properties': {'revision': 6,
                                                      'title': 'val'}}]},
                                  'another thing']
        out = self._run('track edit trk1 -f trake.yml',
                        expect_fail=True)
        self.assertIn('items but matched', out)

    @mock.patch.object(FakeClient, 'put_object')
    def test_rename_fail(self, mock_put):
        mock_put.return_value = None
        out = self._run('track rename trk2 trk7',
                        expect_fail=True)
        self.assertIn('Failed to rename', out)

    @mock.patch.object(FakeClient, 'create_object')
    def test_add_waypoint(self, mock_create):
        out = self._run('waypoint add foo 1.5 2.6')
        self.assertEqual('', out)
        mock_create.assert_called_once_with(
            'waypoint',
            util.make_waypoint('foo', 1.5, 2.6, 0))

    @mock.patch.object(FakeClient, 'create_object')
    @mock.patch.object(FakeClient, 'add_object_to_folder')
    def test_add_waypoint_dry_run(self, mock_add, mock_create):
        out = self._run('waypoint add --dry-run test 1 2')
        self.assertIn('Dry run', out)
        mock_create.assert_not_called()
        mock_add.assert_not_called()

        out = self._run('waypoint add --dry-run --new-folder foo test 1 2')
        self.assertIn('Dry run', out)
        mock_create.assert_not_called()
        mock_add.assert_not_called()

        out = self._run('waypoint add --dry-run --existing-folder folder1 '
                        'test 1 2')
        self.assertIn('Dry run', out)
        mock_create.assert_not_called()
        mock_add.assert_not_called()

    @mock.patch.object(FakeClient, 'create_object')
    def test_add_waypoint_with_altitude(self, mock_create):
        out = self._run('waypoint add foo 1.5 2.6 3')
        self.assertEqual('', out)
        mock_create.assert_called_once_with(
            'waypoint',
            util.make_waypoint('foo', 1.5, 2.6, 3))

    @mock.patch.object(FakeClient, 'create_object')
    def test_add_waypoint_with_extras(self, mock_create):
        out = self._run('waypoint add foo 1.5 2.6 3 '
                        '--icon "foo.png" --notes "these are notes"')
        self.assertEqual('', out)
        mock_create.assert_called_once_with(
            'waypoint',
            util.make_waypoint('foo', 1.5, 2.6,
                               alt=3,
                               notes='these are notes',
                               icon='foo.png'))

    @mock.patch.object(FakeClient, 'create_object')
    def test_add_waypoint_with_icon_by_alias(self, mock_create):
        out = self._run('waypoint add foo 1.5 2.6 3 '
                        '--icon fuel')
        self.assertEqual('', out)
        mock_create.assert_called_once_with(
            'waypoint',
            util.make_waypoint('foo', 1.5, 2.6,
                               alt=3,
                               icon='fuel-24.png'))

    @mock.patch.object(FakeClient, 'create_object')
    def test_add_waypoint_bad_data(self, mock_create):
        out = self._run('waypoint add foo a 2.6',
                        expect_fail=True)
        self.assertIn('Latitude', out)

        out = self._run('waypoint add foo 1.5 a',
                        expect_fail=True)
        self.assertIn('Longitude', out)

        out = self._run('waypoint add foo 1.5 2.6 a',
                        expect_fail=True)
        self.assertIn('Altitude', out)

    @mock.patch.object(FakeClient, 'create_object')
    def test_add_waypoint_failed(self, mock_create):
        mock_create.return_value = None
        out = self._run('waypoint add foo 1.2 2.6',
                        expect_fail=True)
        self.assertIn('Failed to create waypoint', out)

    @mock.patch.object(FakeClient, 'create_object')
    @mock.patch.object(FakeClient, 'add_object_to_folder')
    def test_add_waypoint_new_folder(self, mock_add, mock_create):
        mock_create.side_effect = [
            {'id': '1'},
            {'id': '2', 'properties': {'name': 'folder'}}]
        out = self._run('waypoint add --new-folder bar foo 1.5 2.6')
        self.assertEqual('', out)
        mock_create.assert_has_calls([
            mock.call('waypoint',
                      util.make_waypoint('foo', 1.5, 2.6, 0)),
            mock.call('folder',
                      util.make_folder('bar'))])
        mock_add.assert_called_once_with('2', 'waypoint', '1')

    @mock.patch.object(FakeClient, 'create_object')
    @mock.patch.object(FakeClient, 'add_object_to_folder')
    def test_add_waypoint_existing_folder(self, mock_add, mock_create):
        mock_create.side_effect = [
            {'id': '1'},
            {'id': '2', 'properties': {'name': 'folder'}}]
        out = self._run(
            'waypoint add --existing-folder folder1 foo 1.5 2.6')
        self.assertEqual('', out)
        mock_create.assert_has_calls([
            mock.call('waypoint',
                      util.make_waypoint('foo', 1.5, 2.6, 0))])
        mock_add.assert_called_once_with('101', 'waypoint', '1')

    def test_add_waypoint_existing_folder_not_found(self):
        out = self._run('waypoint add --existing-folder bar foo 1.5 2.6',
                        expect_fail=True)
        self.assertIn('not found', out)

    @mock.patch.object(FakeClient, 'put_object')
    @mock.patch('builtins.open')
    @mock.patch('yaml.dump')
    def test_edit_waypoint_dump(self, mock_dump, mock_open, mock_put):
        out = self._run('waypoint edit wpt3')
        self.assertIn('Edit and then apply', out)
        mock_open.assert_called_once_with('waypoints.yml', 'w')
        fake_file = mock_open.return_value.__enter__.return_value
        fake_file.write.assert_has_calls([mock.call(mock_dump.return_value)])
        preamble = fake_file.write.call_args_list[0][0][0]
        self.assertIn('YAML document', preamble)
        self.assertIn('chemist', preamble)
        mock_put.assert_not_called()

    @mock.patch('gaiagps.util.get_editor')
    @mock.patch.object(FakeClient, 'put_object')
    @mock.patch('builtins.open')
    @mock.patch('yaml.load')
    def test_edit_waypoint_load(self, mock_load, mock_open, mock_put,
                                mock_editor):
        mock_editor.return_value = None
        mock_load.return_value = [{'id': '003',
                                   'properties': {
                                       'icon': 'foo',
                                       'notes': '',
                                       'public': False,
                                       'title': 'newname',
                                       'revision': 6}}]
        out = self._run('waypoint edit wpt3 -f waypoint.yml')
        self.assertEqual('', out)
        mock_open.assert_called_once_with('waypoint.yml', 'r')
        fake_file = mock_open.return_value.__enter__.return_value
        fake_file.read.assert_called_once_with()
        mock_load.assert_called_once_with(fake_file.read.return_value)
        updated = copy.deepcopy(FakeClient().get_object('waypoint', 'wpt3'))
        updated['properties']['title'] = 'newname'
        mock_put.assert_called_once_with('waypoint', updated)

    @mock.patch.object(FakeClient, 'put_object')
    @mock.patch('builtins.open')
    @mock.patch('yaml.load')
    def test_edit_waypoint_load_errors(self, mock_load, mock_open, mock_put):
        # Server rejected for whatever reason
        mock_load.return_value = [{'id': '003',
                                   'properties': {'revision': 6,
                                                  'icon': 'foo',
                                                  'notes': '',
                                                  'public': False,
                                                  'title': 'val'}}]
        mock_put.return_value = False
        out = self._run('waypoint edit wpt3 -f waypoint.yml',
                        expect_fail=True)
        self.assertIn('server rejected', out)

        # YAML top-level is not a list
        mock_load.return_value = {'id': '003'}
        mock_put.return_value = False
        out = self._run('waypoint edit wpt3 -f waypoint.yml',
                        expect_fail=True)
        self.assertIn('format is incorrect', out)

        # Revision mismatch between local and server
        mock_load.return_value = [{'id': '003',
                                   'properties': {'revision': 5,
                                                  'icon': 'foo',
                                                  'notes': '',
                                                  'public': False,
                                                  'title': 'val'}}]
        out = self._run('waypoint edit wpt3 -f waypoint.yml')
        self.assertIn('changed on the server', out)

        # User deleted revision
        mock_load.return_value = [{'id': '003',
                                   'properties': {'title': 'val'}}]
        out = self._run('waypoint edit wpt3 -f waypoint.yml')
        self.assertIn('changed on the server', out)

        # ID mismatch
        mock_load.return_value = [{'id': '002',
                                   'properties': {'revision': 6,
                                                  'icon': 'foo',
                                                  'notes': '',
                                                  'public': False,
                                                  'title': 'val'}}]
        out = self._run('waypoint edit wpt3 -f waypoint.yml')
        self.assertIn('id does not match', out)

        # User removed a value
        mock_load.return_value = [{'id': '003',
                                   'properties': {'revision': 6,
                                                  'icon': 'foo',
                                                  'public': False,
                                                  'title': 'val'}}]
        out = self._run('waypoint edit wpt3 -f waypoint.yml',
                        expect_fail=True)
        self.assertIn('Deleting values', out)

        # Length mismatch between file and server query
        mock_load.return_value = [{'id': '002',
                                   'properties': {'revision': 6,
                                                  'title': 'val'}},
                                  'another thing']
        out = self._run('waypoint edit wpt3 -f waypoint.yml',
                        expect_fail=True)
        self.assertIn('items but matched', out)

    @mock.patch('gaiagps.shell.waypoint.Waypoint._dump_for_edit')
    @mock.patch('gaiagps.shell.waypoint.Waypoint._load_for_edit')
    @mock.patch('subprocess.call')
    @mock.patch('os.path.getmtime')
    @mock.patch('gaiagps.util.get_editor')
    def test_edit_waypoint_interactive(self, mock_editor,
                                       mock_mtime, mock_call,
                                       mock_load, mock_dump):
        mock_mtime.return_value = 123
        mock_editor.return_value = '/usr/bin/editor'
        out = self._run('waypoint edit wpt3 -i')
        mock_call.assert_called_once_with(['/usr/bin/editor', 'waypoints.yml'])
        self.assertIn('No changes made', out)
        mock_load.assert_not_called()

        mock_mtime.side_effect = [123, 456]
        out = self._run('waypoint edit wpt3 -i')
        self.assertTrue(mock_load.called)

        mock_mtime.side_effect = [123, 456]
        mock_load.side_effect = Exception('test failed')
        out = self._run('waypoint edit wpt3 -i',
                        expect_fail=True)
        self.assertIn('test failed', out)

    @mock.patch('gaiagps.util.get_editor')
    def test_edit_waypoint_no_editor(self, mock_editor):
        mock_editor.return_value = None
        out = self._run('waypoint edit -h')
        self.assertNotIn('interactive', out)

    def test_edit_waypoint_no_match(self):
        out = self._run('waypoint edit --match notathing',
                        expect_fail=True)
        self.assertIn('No objects matched criteria',  out)

        out = self._run('waypoint edit',
                        expect_fail=True)
        self.assertIn('No objects matched criteria',  out)

    @mock.patch('gaiagps.shell.waypoint.Waypoint._dump_for_edit')
    def test_edit_waypoint_in_folder(self, mock_dump):
        the_wpts = []

        def _dump(wpts, editable, fn):
            the_wpts.clear()
            the_wpts.extend(wpts)
            return 1

        mock_dump.side_effect = _dump

        # All items in a folder
        self._run('--verbose waypoint edit --in-folder subfolder')
        self.assertEqual(1, len(the_wpts))
        self.assertEqual('003', the_wpts[0]['id'])

        # One item in a folder by match
        self._run('waypoint edit --in-folder subfolder wpt3')
        self.assertEqual(1, len(the_wpts))
        self.assertEqual('003', the_wpts[0]['id'])

        # Folder but specify an item not in that folder
        mock_dump.reset_mock()
        out = self._run('waypoint edit --in-folder subfolder wpt2',
                        expect_fail=True)
        self.assertNotIn('Wrote', out)
        self.assertIn('No objects matched', out)
        mock_dump.assert_not_called()

    @mock.patch.object(FakeClient, 'upload_file')
    def test_upload(self, mock_upload):
        self._run('upload foo.gpx')
        mock_upload.assert_called_once_with('foo.gpx')

    @mock.patch.object(FakeClient, 'upload_file')
    @mock.patch('gaiagps.util.strip_gpx_extensions')
    def test_upload_strip_gpx_extensions(self, mock_strip, mock_upload):
        self._run('upload --strip-gpx-extensions /path/to/foo.gpx')
        mock_strip.assert_called_once_with('/path/to/foo.gpx',
                                           '/path/to/clean-foo.gpx')
        mock_upload.assert_called_once_with('/path/to/clean-foo.gpx')

    @mock.patch.object(FakeClient, 'get_object')
    @mock.patch.object(FakeClient, 'upload_file')
    def test_upload_queued(self, mock_upload, mock_get):
        mock_upload.return_value = None
        out = self._run('upload --existing-folder foo foo.gpx')
        self.assertIn('upload has been queued', out)
        self.assertIn('Unable to move', out)

    @mock.patch('time.sleep')
    @mock.patch.object(FakeClient, 'get_object')
    @mock.patch.object(FakeClient, 'upload_file')
    def test_upload_queued_poll(self, mock_upload, mock_get, mock_sleep):
        mock_upload.return_value = None
        mock_get.side_effect = [apiclient.NotFound,
                                apiclient.NotFound,
                                {'id': 'foo',
                                 'properties': {
                                     'name': 'folder'}}]
        out = self._run('--verbose upload --poll foo.gpx')
        self.assertIn('..done', out)
        mock_get.assert_has_calls([mock.call('folder', 'foo.gpx'),
                                   mock.call('folder', 'foo.gpx'),
                                   mock.call('folder', 'foo.gpx')])

        mock_get.side_effect = apiclient.NotFound
        out = self._run('--verbose upload --poll foo.gpx')
        self.assertIn('queued at the server', out)

    @mock.patch.object(FakeClient, 'upload_file')
    @mock.patch('gaiagps.util.get_track_colors_from_gpx')
    @mock.patch.object(FakeClient, 'put_object')
    def test_upload_colorize_tracks(self, mock_put, mock_colors, mock_upload):
        mock_upload.return_value = {'id': '102',
                                    'properties': {'name': 'folder2'}}
        mock_colors.return_value = {'trk1': 'Red',
                                    'trk2': 'Green'}
        self._run('--verbose upload --colorize-tracks foo.gpx')
        # Since we're reusing fake folder2 from the fixture, which has
        # only trk2 in it, we expect to only see trk2 updated since
        # upload calls colorize with the GPX upload folder
        mock_put.assert_called_once_with('track',
                                         {'id': '202',
                                          'color': '#36C03B'})

        # Try again without a gpx file and make sure we report it,
        # but do not fail
        mock_colors.side_effect = Exception('Not a gpx file')
        out = self._run('--verbose upload --colorize-tracks foo.kml')
        self.assertIn('Failed to colorize', out)

    @mock.patch.object(FakeClient, 'set_objects_archive')
    def _test_archive_waypoint(self, cmd, mock_archive):
        args = [
            'wpt3',
            '--match w.*3',
            '--match-date 2015-10-21',
        ]
        for arg in args:
            mock_archive.reset_mock()
            self._run('waypoint %s %s' % (cmd, arg))
            mock_archive.assert_called_once_with('waypoint', ['003'],
                                                 cmd == 'archive')

    def test_archive_waypoint(self):
        self._test_archive_waypoint('archive')

    def test_unarchive_waypoint(self):
        self._test_archive_waypoint('unarchive')

    @mock.patch.object(FakeClient, 'set_objects_archive')
    def test_archive_dry_run(self, mock_archive):
        self._run('waypoint archive --dry-run wpt3')
        mock_archive.assert_not_called()

    @mock.patch.object(FakeClient, 'set_objects_archive')
    def test_archive_fails(self, mock_archive):
        self._run('waypoint archive',
                  expect_fail=True)
        mock_archive.assert_not_called()

        self._run('waypoint archive --match nothing',
                  expect_fail=True)
        mock_archive.assert_not_called()

    @mock.patch.object(FakeClient, 'set_objects_archive')
    def test_archive_in_folder(self, mock_archive):
        self._run('waypoint archive --in-folder folder1')
        mock_archive.assert_called_once_with('waypoint', ['002'],
                                             True)

    @mock.patch('gaiagps.util.is_id', new=fake_is_id)
    def test_waypoint_coords(self):
        out = self._run('waypoint coords wpt1')
        self.assertEqual('45.500000,-122.000000', out.strip())

        out = self._run('waypoint coords --show-name wpt1')
        self.assertEqual('45.500000,-122.000000 wpt1', out.strip())

        out = self._run('waypoint coords --show-name --match wpt')
        self.assertIn('wpt1', out)
        self.assertIn('wpt2', out)

        self._run('waypoint coords --show-name --match wpt --just-one',
                  expect_fail=True)

        self._run('waypoint coords',
                  expect_fail=True)

    @mock.patch.object(FakeClient, 'create_object')
    def test_add_folder(self, fake_create):
        out = self._run('folder add foo')
        self.assertEqual('', out)
        fake_create.assert_called_once_with('folder', util.make_folder('foo'))

    @mock.patch.object(FakeClient, 'create_object')
    @mock.patch.object(FakeClient, 'add_object_to_folder')
    def test_add_folder_dry_run(self, fake_add, fake_create):
        out = self._run('folder add --dry-run foo')
        self.assertIn('Dry run', out)
        fake_create.assert_not_called()
        fake_add.assert_not_called()

        out = self._run('folder add --dry-run --existing-folder folder1 '
                        'foo')
        self.assertIn('Dry run', out)
        fake_create.assert_not_called()
        fake_add.assert_not_called()

    @mock.patch.object(FakeClient, 'create_object')
    def test_add_folder_failed(self, mock_create):
        mock_create.return_value = None
        out = self._run('folder add foo',
                        expect_fail=True)
        self.assertIn('Failed to add folder', out)

    @mock.patch.object(FakeClient, 'create_object')
    @mock.patch.object(FakeClient, 'add_object_to_folder')
    def test_add_folder_to_existing(self, fake_add, fake_create):
        fake_create.return_value = {'id': '105'}
        out = self._run('folder add --existing-folder folder1 foo')
        self.assertEqual('', out)
        fake_create.assert_called_once_with('folder', util.make_folder('foo'))
        fake_add.assert_called_once_with('101', 'folder', '105')

    @mock.patch.object(FakeClient, 'create_object')
    @mock.patch.object(FakeClient, 'add_object_to_folder')
    def test_add_folder_to_existing_fail(self, fake_add, fake_create):
        fake_create.return_value = {'id': '105'}
        fake_add.return_value = None
        out = self._run('folder add --existing-folder folder1 foo',
                        expect_fail=True)
        self.assertIn('failed to add', out)
        fake_create.assert_called_once_with('folder', util.make_folder('foo'))

    @mock.patch.object(FakeClient, 'put_object')
    def test_rename_folder(self, mock_put):
        out = self._run('--verbose folder rename folder1 newfolder')
        self.assertIn('Renaming', out)
        new_fld = {'id': '101', 'title': 'newfolder'}
        mock_put.assert_called_once_with('folder', new_fld)

    @mock.patch.object(FakeClient, 'upload_file')
    @mock.patch.object(FakeClient, 'put_object')
    @mock.patch.object(FakeClient, 'delete_object')
    def test_upload_existing_folder(self, mock_delete, mock_put, mock_upload):
        mock_upload.return_value = {'id': '105', 'properties': {
            'name': 'foo.gpx'}}

        folders_copy = copy.deepcopy(FakeClient.FOLDERS)
        folders_copy.append({'id': '105',
                             'title': 'foo.gpx',
                             'folder': None,
                             'properties': {}})

        waypoints_copy = copy.deepcopy(FakeClient.WAYPOINTS)
        waypoints_copy.append({'id': '010', 'folder': '105', 'title': 'wpt8'})
        waypoints_copy.append({'id': '011', 'folder': '105', 'title': 'wpt9'})

        tracks_copy = copy.deepcopy(FakeClient.TRACKS)
        tracks_copy.append({'id': '210', 'folder': '105', 'title': 'trk8'})
        tracks_copy.append({'id': '211', 'folder': '105', 'title': 'trk9'})

        with mock.patch.multiple(FakeClient,
                                 FOLDERS=folders_copy,
                                 WAYPOINTS=waypoints_copy,
                                 TRACKS=tracks_copy):
            self._run('upload --existing-folder folder1 foo.gpx')

        expected = copy.deepcopy(FakeClient.FOLDERS[0])
        expected['parent'] = None
        expected['children'] = ['103']
        expected['maps'] = []
        expected['waypoints'] = ['002', '010', '011']
        expected['tracks'] = ['210', '211']
        expected['properties'] = {'time_created': '2019-01-01T02:03:04Z'}
        mock_put.assert_called_once_with('folder', expected)
        mock_delete.assert_called_once_with('folder', '105')

    @mock.patch.object(FakeClient, 'upload_file')
    @mock.patch.object(FakeClient, 'put_object')
    @mock.patch.object(FakeClient, 'delete_object')
    @mock.patch.object(FakeClient, 'create_object')
    def test_upload_new_folder(self, mock_create, mock_delete, mock_put,
                               mock_upload):
        mock_upload.return_value = {'id': '105', 'properties': {
            'name': 'foo.gpx'}}

        folders_copy = copy.deepcopy(FakeClient.FOLDERS)
        folders_copy.append({'id': '105',
                             'title': 'foo.gpx',
                             'folder': None,
                             'properties': {}})
        folders_copy.append({'id': '106',
                             'title': 'newfolder',
                             'folder': None,
                             'properties': {'name': 'newfolder'}})

        mock_create.return_value = folders_copy[-1]

        waypoints_copy = copy.deepcopy(FakeClient.WAYPOINTS)
        waypoints_copy.append({'id': '010', 'folder': '105', 'title': 'wpt8'})
        waypoints_copy.append({'id': '011', 'folder': '105', 'title': 'wpt9'})

        tracks_copy = copy.deepcopy(FakeClient.TRACKS)
        tracks_copy.append({'id': '210', 'folder': '105', 'title': 'trk8'})
        tracks_copy.append({'id': '211', 'folder': '105', 'title': 'trk9'})

        with mock.patch.multiple(FakeClient,
                                 FOLDERS=folders_copy,
                                 WAYPOINTS=waypoints_copy,
                                 TRACKS=tracks_copy):
            self._run('upload --new-folder newfolder foo.gpx')

        expected = copy.deepcopy(folders_copy[-1])
        expected['parent'] = None
        expected['children'] = []
        expected['maps'] = []
        expected['waypoints'] = ['010', '011']
        expected['tracks'] = ['210', '211']
        expected['properties'] = {'time_created': '2019-01-01T02:03:04Z'}
        mock_put.assert_called_once_with('folder', expected)
        mock_delete.assert_called_once_with('folder', '105')

    @mock.patch.object(FakeClient, 'upload_file')
    @mock.patch.object(FakeClient, 'create_object')
    @mock.patch.object(FakeClient, 'delete_object')
    def test_upload_new_folder_create_fail(self, mock_delete, mock_create,
                                           mock_upload):
        mock_create.return_value = None
        out = self._run('upload --new-folder foo foo.gpx',
                        expect_fail=True)
        self.assertIn('failed to create folder', out)
        mock_delete.assert_not_called()

    @mock.patch.object(FakeClient, 'upload_file')
    @mock.patch.object(FakeClient, 'put_object')
    @mock.patch.object(FakeClient, 'delete_object')
    def test_upload_with_folder_move_fail(self, mock_delete, mock_put,
                                          mock_upload):
        mock_upload.return_value = {'id': '102',  # re-use to avoid mocks
                                    'properties': {
                                        'name': 'foo.gpx',
                                    }}
        mock_put.return_value = None
        out = self._run('upload --existing-folder folder1 foo.gpx',
                        expect_fail=True)
        self.assertIn('Failed to move', out)
        mock_delete.assert_not_called()

    @mock.patch('builtins.open')
    def test_export(self, mock_open):
        out = self._run('waypoint export wpt1 foo.gpx')
        self.assertIn('Wrote \'foo.gpx\'', out)
        mock_open.assert_called_once_with('foo.gpx', 'wb')
        fake_file = mock_open.return_value.__enter__.return_value
        fake_file.write.assert_called_once_with('object 001 format gpx')

        out = self._run('folder export folder1 foo.gpx')
        self.assertIn('Wrote \'foo.gpx\'', out)

        out = self._run('folder export folder1 -')
        self.assertIn('object 101 format gpx', out)

        out = self._run('track export trk1 foo.gpx')
        self.assertIn('Wrote \'foo.gpx\'', out)

        out = self._run('folder export folder1 --format kml foo.kml')
        self.assertIn('Wrote \'foo.kml\'', out)

        out = self._run('folder export folder1 --format jpg foo',
                        expect_fail=True)

    def test_query_hidden(self):
        self._run('query foo',
                  expect_fail=True)

    @mock.patch.dict(os.environ, GAIAGPSCLIENTDEV='y')
    @mock.patch.object(FakeClient, 's')
    def test_query(self, mock_s):
        mock_r = mock.MagicMock()
        mock_r.headers = {'Content-Type': 'foo json foo'}
        mock_r.status_code = 200
        mock_r.reason = 'OK'
        mock_r.json.return_value = {'object': 'data'}
        mock_s.get.return_value = mock_r
        out = self._run('query api/objects/waypoint')
        self.assertIn('200 OK', out)
        self.assertIn('json', out)
        self.assertIn('object', out)
        mock_s.get.assert_called_once_with(
            apiclient.gurl('api', 'objects', 'waypoint'),
            params={})
        mock_r.json.assert_called_once_with()

    @mock.patch.dict(os.environ, GAIAGPSCLIENTDEV='y')
    @mock.patch.object(FakeClient, 's')
    def test_query_args_method_quiet(self, mock_s):
        mock_r = mock.MagicMock()
        mock_r.headers = {'Content-Type': 'html'}
        mock_r.status_code = 200
        mock_r.reason = 'OK'
        mock_r.content = 'foo'
        mock_s.put.return_value = mock_r

        out = self._run('query api/objects/waypoint -X PUT -a foo=bar -q')
        self.assertNotIn('200 OK', out)
        self.assertNotIn('Content-Type', out)
        self.assertIn('foo', out)
        mock_s.put.assert_called_once_with(
            apiclient.gurl('api', 'objects', 'waypoint'),
            params={'foo': 'bar'})

    def test_url(self):
        out = self._run('waypoint url wpt1')
        self.assertEqual('https://www.gaiagps.com/datasummary/waypoint/001',
                         out.strip())

    def test_dump(self):
        out = self._run('waypoint dump wpt1')
        self.assertEqual(
            pprint.pformat(
                FakeClient().get_object('waypoint', 'wpt1')),
            out.strip())

    @mock.patch.object(FakeClient, 'test_auth')
    def test_test(self, mock_test):
        mock_test.return_value = True
        out = self._run('test')
        self.assertEqual('Success!', out.strip())

        mock_test.return_value = False
        out = self._run('test',
                        expect_fail=True)
        self.assertEqual('Unable to access gaia', out.strip())

    @mock.patch.object(FakeClient, 'test_auth')
    def test_with_debug(self, mock_test):
        mock_test.return_value = True
        self._run('--debug test')

    @mock.patch.object(FakeClient, '__init__')
    def test_client_init_login_failure(self, mock_init):
        mock_init.side_effect = Exception()
        out = self._run('test',
                        expect_fail=True)
        self.assertIn('Unable to access Gaia', out)

    @mock.patch('getpass.getpass')
    @mock.patch('os.isatty')
    @mock.patch.object(FakeClient, '__init__')
    @mock.patch.object(FakeClient, 'test_auth')
    def test_get_pass(self, mock_test, mock_client, mock_tty, mock_getpass):
        mock_tty.return_value = True
        mock_getpass.return_value = mock.sentinel.password
        mock_client.return_value = None
        self._run('--user foo@bar.com test')
        mock_getpass.assert_called_once_with()
        mock_client.assert_called_once_with('foo@bar.com',
                                            mock.sentinel.password,
                                            cookies=None)

    def test_show_waypoint(self):
        out = self._run('waypoint show wpt3')
        self.assertIn('time_created', out)
        self.assertIn('title', out)

    def test_show_track(self):
        out = self._run('track show trk1')
        self.assertIn('time_created', out)
        self.assertIn('title', out)

    def test_show_folder(self):
        out = self._run('folder show folder1')
        self.assertRegex(out, r'name.*folder1')
        self.assertRegex(out, r'\| +waypoints.*\(1 items\) +\|')
        self.assertRegex(out, r'\| +tracks.*\(0 items\) +\|')
        self.assertNotIn('[ ', out)

        out = self._run('folder show --only-key name folder1')
        self.assertRegex(out, r'name.*folder1')
        self.assertNotIn('waypoints', out)
        self.assertNotIn('tracks', out)

        out = self._run('folder show --only-key name --only-key tracks '
                        'folder1')
        self.assertRegex(out, r'name.*folder1')
        self.assertRegex(out, r'\| +tracks.*\(0 items\) +\|')
        self.assertNotIn('waypoints', out)

        out = self._run('folder show -f = folder1')
        self.assertIn('name=folder1', out)
        self.assertIn('waypoints=[{', out)
        self.assertIn('tracks=[]', out)

        out = self._run('folder show --expand-key waypoints folder1')
        self.assertIn('name', out)
        self.assertRegex(out, r'\| +waypoints +\| \[{')
        self.assertNotRegex(out, r'\| +tracks +\| \[\]')

        out = self._run('folder show --expand-key waypoints '
                        '--expand-key tracks folder1')
        self.assertIn('name', out)
        self.assertRegex(out, r'\| +waypoints +\| \[{')
        self.assertRegex(out, r'\| +tracks +\| \[\]')

        out = self._run('folder show --expand-key all folder1')
        self.assertIn('name', out)
        self.assertRegex(out, r'\| +waypoints +\| \[{')
        self.assertRegex(out, r'\| +tracks +\| \[\]')

        out = self._run('folder show --only-vals folder1')
        self.assertNotIn('name', out)
        self.assertIn('folder1', out)

        out = self._run('folder show --only-key foo folder1',
                        expect_fail=True)

        out = self._run('folder show -f = --only-vals folder1',
                        expect_fail=True)

    def test_tree(self):
        out = self._run('tree')
        lines = out.split(os.linesep)

        def level(string):
            for line in lines:
                if string in line:
                    return line.index(string)
            return None

        self.assertEqual(0, level('/'))
        self.assertEqual(4, level('folder1/'))
        self.assertEqual(8, level('subfolder'))
        self.assertEqual(12, level('[W] wpt3'))
        self.assertEqual(4, level('[W] wpt1'))

        out = self._run('tree --long')
        self.assertIn('folder1', out)
        self.assertIn('21 Oct', out)

    @mock.patch.object(FakeClient, 'put_object')
    def test_colorize_track(self, mock_put):
        # Bad color
        out = self._run('track colorize --color red trk1',
                        expect_fail=True)
        self.assertIn('Invalid color code', out)
        mock_put.assert_not_called()

        # No match
        out = self._run('track colorize --color #ff0000 notrk',
                        expect_fail=True)
        self.assertIn('not found', out)
        mock_put.assert_not_called()

        # No pattern match
        out = self._run('track colorize --color #ff0000 --match notrk',
                        expect_fail=True)
        self.assertIn('No matching', out)
        mock_put.assert_not_called()

        # Change with proper code
        out = self._run('track colorize --color #ff0000 trk1')
        self.assertEqual('', out)
        mock_put.assert_called_once_with('track', {'id': '201',
                                                   'color': '#ff0000'})

        # Change honors dry-run
        mock_put.reset_mock()
        out = self._run('track colorize --dry-run --color #ff0000 trk1')
        self.assertEqual('', out)
        mock_put.assert_not_called()

        # Change with missing hash grace
        mock_put.reset_mock()
        out = self._run('track colorize --color ff0000 trk1')
        self.assertEqual('', out)
        mock_put.assert_called_once_with('track', {'id': '201',
                                                   'color': '#ff0000'})

        # Failed PUT reports failure
        mock_put.reset_mock()
        mock_put.return_value = False
        out = self._run('track colorize --color ff0000 trk1',
                        expect_fail=True)
        self.assertIn('Failed to set track', out)

    @mock.patch('random.choice')
    @mock.patch.object(FakeClient, 'put_object')
    def test_colorize_track_random(self, mock_put, mock_choice):
        out = self._run('track colorize --random notrk',
                        expect_fail=True)
        self.assertIn('not found', out)
        mock_put.assert_not_called()

        out = self._run('track colorize --random --match notrk',
                        expect_fail=True)
        self.assertIn('No matching', out)
        mock_put.assert_not_called()

        mock_choice.side_effect = ['color1', 'color2']
        out = self._run('track colorize --random trk1 trk2')
        self.assertEqual('', out)
        self.assertTrue(mock_choice.called)
        mock_put.assert_any_call('track', {'id': '201',
                                           'color': 'color1'})
        mock_put.assert_any_call('track', {'id': '202',
                                           'color': 'color2'})

    @mock.patch('gaiagps.util.get_track_colors_from_gpx')
    @mock.patch.object(FakeClient, 'put_object')
    def test_colorize_track_from_gpx(self, mock_put, mock_get_tracks):
        mock_get_tracks.return_value = {
            'trk1': 'Red',
            'trk3': 'Green',
        }

        # Match with no matches
        out = self._run('track colorize --from-gpx-file foo.gpx --match notrk',
                        expect_fail=True)
        self.assertIn('No matching', out)
        mock_put.assert_not_called()

        # Explicit, runs one
        out = self._run('track colorize --from-gpx-file foo.gpx trk1')
        self.assertEqual('', out)
        mock_put.assert_called_once_with('track', {'id': '201',
                                                   'color': '#F90553'})

        # Match that matches some not found in the gpx data
        mock_put.reset_mock()
        out = self._run('--verbose track colorize --from-gpx-file foo.gpx '
                        '--match trk')
        self.assertIn('\'trk2\' not found in GPX file', out)
        self.assertIn('Coloring track \'trk1\'', out)
        mock_put.assert_any_call('track', {'id': '201',
                                           'color': '#F90553'})

        # Run all found in the gpx data
        mock_put.reset_mock()
        out = self._run('--verbose track colorize --from-gpx-file foo.gpx')
        self.assertIn('Coloring track \'trk1\'', out)
        self.assertNotIn('trk3', out)
        mock_put.assert_any_call('track', {'id': '201',
                                           'color': '#F90553'})

        # In folder only selects the right tracks
        mock_get_tracks.return_value = {'trk1': 'Green',
                                        'trk2': 'Red'}
        mock_put.reset_mock()
        self._run('--verbose track colorize --from-gpx-file foo.gpx '
                  '--in-folder folder2')
        mock_put.assert_called_once_with('track', {'id': '202',
                                                   'color': '#F90553'})

        # No tracks in gpx data
        mock_get_tracks.return_value = {}
        mock_put.reset_mock()
        out = self._run('--verbose track colorize --from-gpx-file foo.gpx',
                        expect_fail=True)
        self.assertIn('No colored tracks found', out)
        mock_put.assert_not_called()

        # Tracks in gpx, but no matching
        mock_get_tracks.return_value = {'notrk': 'foo'}
        mock_put.reset_mock()
        out = self._run('--verbose track colorize --from-gpx-file foo.gpx',
                        expect_fail=True)
        self.assertIn('No matching objects', out)
        mock_put.assert_not_called()

    @mock.patch('gaiagps.util.date_parse')
    @mock.patch('os.utime')
    @mock.patch('builtins.open')
    def test_photo_export(self, mock_open, mock_utime, mock_dp):
        # This is mocked because the date libs open timezone definitions
        # and such, which is not compatible with our mocking of open()
        mock_dp.return_value = datetime.datetime(2015, 10, 21)
        expected_ts = time.mktime(mock_dp.return_value.timetuple())

        real_exists = os.path.exists

        def fake_exists(f):
            if f == 'pho2.jpg':
                return True
            else:
                return real_exists(f)

        with mock.patch('os.path.exists', new=fake_exists):

            out = self._run('--verbose photo export --dry-run pho1')
            self.assertIn('Would download', out)
            mock_open.assert_not_called()

            out = self._run('--verbose photo export pho1 pho2')
            self.assertIn('Wrote \'pho1.jpg\'', out)
            self.assertIn('File \'pho2.jpg\' already exists', out)
            mock_open.assert_called_once_with('pho1.jpg', 'wb')
            mock_file = mock_open.return_value.__enter__.return_value
            mock_file.write.assert_called_once_with(b'photodataforpho1')
            mock_utime.assert_called_once_with('pho1.jpg',
                                               (expected_ts, expected_ts))

        out = self._run('--verbose photo export --match pho3',
                        expect_fail=True)

        out = self._run('--verbose photo export --match',
                        expect_fail=True)

    def test_folder_access(self):
        self._run('folder access folder1',
                  expect_fail=True)

        out = self._run('folder access --list folder1')
        self.assertIn('myuser (bar@foo.com)', out)
        self.assertIn('Pending (foo@bar.com)', out)
        self.assertIn('admin', out)


class TestShellFunctional(test_apiclient.BaseClientFunctional):
    @mock.patch.object(shell, 'cookiejar')
    def _run(self, cmdline, mock_cookies, expect_fail=False):
        mock_cookies.return_value.__enter__.return_value = self.cookies
        out = FakeOutput()
        with mock.patch.multiple('sys', stdout=out, stderr=out, stdin=out):
            rc = shell.main(shlex.split(cmdline))
        print(out.getvalue())
        if not expect_fail:
            self.assertEqual(0, rc)
        else:
            self.assertNotEqual(0, rc)
        return out.getvalue()

    def _import_sample_gpx(self):
        tmp = tempfile.mktemp('.gpx', 'tests-')
        with open(tmp, 'w') as f:
            f.write(test_util.GPX_WITH_EXTENSIONS)
        out = self._run('--verbose upload --strip-gpx-extensions %s' % tmp)
        self.assertNotIn('queued', out,
                         'Server started queuing our test data')
        self.addCleanup(lambda: os.remove(tmp))
        import_folder_name = _test_name('import')
        self._run('folder rename "%s" "%s"' % (
            'clean-%s' % os.path.basename(tmp), import_folder_name))
        return tmp, import_folder_name

    def test_track_ops(self):
        tmp, import_folder_name = self._import_sample_gpx()
        name = _test_name('test track')

        # Dump
        out = self._run('track dump "%s"' % name)
        self.assertIn(name, out)
        self.assertNotIn('#00ff00', out.lower())

        # Show
        out = self._run('track show "%s"' % name)
        self.assertIn(name, out)

        # List
        out = self._run('track list')
        self.assertIn(name, out)

        # Colorize
        self._run('track colorize --color #00ff00 "%s"' % name)
        out = self._run('track dump "%s"' % name)
        self.assertIn(name, out)
        self.assertIn('#00ff00', out.lower())

        # Rename
        newname = name + ' NEW'
        self._run('track rename "%s" "%s"' % (name, newname))
        out = self._run('track show "%s"' % newname)
        self.assertIn(newname, out)
        name = newname

        # Url
        out = self._run('track url "%s"' % name)
        self.assertIn('https://www.gaiagps', out)

        # Archive, Unarchive
        self._run('track archive "%s"' % name)
        out = self._run('track list --archived=no')
        self.assertNotIn(name, out)
        self._run('track unarchive "%s"' % name)
        out = self._run('track list --archived=no')
        self.assertIn(name, out)

        # Move
        folder = _test_name('foo')
        self._run('folder add "%s"' % folder)
        self._run('track move "%s" "%s"' % (name, folder))
        out = self._run('track list')
        self.assertRegex(out, r'(?m)^.*%s.*%s.*$' % (name, folder))

        # Remove
        self._run('track remove "%s"' % name)
        self._run('track show "%s"' % name,
                  expect_fail=True)
        self._run('folder remove --force "%s"' % folder)

    def test_waypoint_ops(self):
        name = _test_name('wpt')
        folder = _test_name('folder')

        # Add
        self._run('waypoint add --notes "these are notes" --icon chemist '
                  '--new-folder "%s" "%s" 45.123 -122.9876 42' % (
                      folder, name))
        out = self._run('waypoint list')
        self.assertIn(name, out)
        self.assertIn(folder, out)

        # Dump
        out = self._run('waypoint dump "%s"' % name)
        self.assertIn(name, out)

        # Show
        out = self._run('waypoint show "%s"' % name)
        self.assertIn(name, out)

        # Coords
        out = self._run('waypoint coords "%s"' % name)
        self.assertIn('45.123', out)
        self.assertIn('-122.9876', out)

        # Url
        out = self._run('waypoint url "%s"' % name)
        self.assertIn('https://www.gaiagps', out)

        # List match
        out = self._run('waypoint list --match "gaia.*wpt"')
        self.assertIn(name, out)

        # Archive, Unarchive
        self._run('waypoint archive "%s"' % name)
        out = self._run('waypoint list --archived=no')
        self.assertNotIn(name, out)
        self._run('waypoint unarchive "%s"' % name)
        out = self._run('waypoint list --archived=no')
        self.assertIn(name, out)

        # Move
        self._run('waypoint move "%s" /' % name)
        out = self._run('waypoint list')
        self.assertNotIn(folder, out)
        self._run('waypoint move "%s" "%s"' % (name, folder))
        out = self._run('waypoint list')
        self.assertIn(folder, out)

        # Rename
        newname = name + ' NEW'
        self._run('waypoint rename "%s" "%s"' % (name, newname))
        out = self._run('waypoint show "%s"' % newname)
        self.assertIn(newname, out)
        name = newname

        # Remove
        self._run('waypoint remove "%s"' % name)
        out = self._run('waypoint list')
        self.assertNotIn(name, out)
        self._run('folder remove --force "%s"' % folder)

    def test_bug_track_colors_ignored(self):
        # Test that honoring imported track colors is still unimplemented
        # in gaiagps.com. This servces as a sentinel for when the cookbook
        # doc item (and colorize --from-gpx-file) can be removed.
        tmp = tempfile.mktemp('.gpx', 'tests-')
        with open(tmp, 'w') as f:
            f.write(test_util.GPX_WITH_EXTENSIONS.replace('Red', 'Green'))
        out = self._run('--verbose upload %s' % tmp)
        self.assertNotIn('queued', out,
                         'Server started queuing our test data')
        self.addCleanup(os.remove, tmp)
        foldername = os.path.basename(tmp)
        trackname = _test_name('test track')
        self.addCleanup(self._run, 'folder remove --force "%s"' % foldername)
        out = self._run('track show -K color -V "%s"' % trackname)
        self.assertEqual('#ff0000', out.strip())
