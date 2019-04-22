import contextlib
import copy
import mock
import shlex
import unittest
import io

from gaiagps import apiclient
from gaiagps import shell
from gaiagps import util


client = apiclient.GaiaClient


class FakeOutput(io.StringIO):
    def fileno(self):
        return -1


class FakeClient(object):
    FOLDERS = [
        {'id': '101', 'folder': None, 'title': 'folder1'},
        {'id': '102', 'folder': None, 'title': 'folder2'},
        {'id': '103', 'folder': '101', 'title': 'subfolder'},
        {'id': '104', 'folder': None, 'title': 'emptyfolder'},
        ]
    WAYPOINTS = [
        {'id': '001', 'folder': None, 'title': 'wpt1'},
        {'id': '002', 'folder': '101', 'title': 'wpt2'},
        {'id': '003', 'folder': '103', 'title': 'wpt3',
         'properties': {'time_created': '2015-10-21T23:29:00Z'}},
    ]
    TRACKS = [
        {'id': '201', 'folder': None, 'title': 'trk1'},
        {'id': '202', 'folder': '102', 'title': 'trk2'},
    ]

    def __init__(self, *a, **k):
        pass

    def list_objects(self, objtype):
        def add_props(l):
            return [dict(d, properties=d.get('properties', {})) for d in l]

        if objtype == 'waypoint':
            return add_props(self.WAYPOINTS)
        elif objtype == 'track':
            return add_props(self.TRACKS)
        elif objtype == 'folder':
            r = []
            for f in self.FOLDERS:
                r.append(dict(f,
                              maps=[],
                              waypoints=[w['id'] for w in self.WAYPOINTS
                                         if w['folder'] == f['id']],
                              tracks=[t['id'] for t in self.TRACKS
                                      if t['folder'] == f['id']],
                              children=[f['id'] for f in self.FOLDERS
                                        if f['folder'] == f['id']]))
            return r
        else:
            raise Exception('Invalid type %s' % objtype)

    def get_object(self, objtype, name=None, id_=None, fmt=None):
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
        obj['properties'] = {key: obj.pop('title')}
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


@contextlib.contextmanager
def fake_cookiejar():
    yield None


@mock.patch('gaiagps.shell.cookiejar', new=fake_cookiejar)
@mock.patch.object(apiclient, 'GaiaClient', new=FakeClient)
class TestShellUnit(unittest.TestCase):
    def _run(self, cmdline):
        out = FakeOutput()
        with mock.patch.multiple('sys', stdout=out, stderr=out, stdin=out):
            rc = shell.main(shlex.split(cmdline))
        print(out.getvalue())
        return rc, out.getvalue()

    def test_first_run(self):
        rc, out = self._run('')
        self.assertEqual(1, rc)
        self.assertIn('usage:', out)

    def test_waypoint_list_by_id(self):
        rc, out = self._run('waypoint list --by-id')
        self.assertEqual(0, rc)
        self.assertIn('001', out)
        self.assertIn('wpt2', out)

    def test_list_wpt(self):
        rc, out = self._run('waypoint list')
        self.assertEqual(0, rc)
        self.assertIn('wpt1', out)
        self.assertIn('wpt2', out)
        self.assertIn('wpt3', out)
        self.assertIn('folder1', out)
        self.assertIn('subfolder', out)
        self.assertNotIn('folder2', out)

    def test_list_trk(self):
        rc, out = self._run('track list')
        self.assertEqual(0, rc)
        self.assertIn('trk1', out)
        self.assertIn('trk2', out)
        self.assertIn('folder2', out)
        self.assertNotIn('folder1', out)
        self.assertNotIn('subfolder', out)

    def test_list_match(self):
        rc, out = self._run('waypoint list --match w.*2')
        self.assertEqual(0, rc)
        self.assertIn('wpt2', out)
        self.assertNotIn('wpt1', out)

    def test_list_match_date(self):
        rc, out = self._run('waypoint list --match-date 2019-01-01')
        self.assertEqual(0, rc)
        self.assertNotIn('wpt1', out)
        self.assertNotIn('wpt2', out)
        self.assertNotIn('wpt3', out)

        rc, out = self._run('waypoint list --match-date 2015-10-21')
        self.assertEqual(0, rc)
        self.assertNotIn('wpt1', out)
        self.assertNotIn('wpt2', out)
        self.assertIn('wpt3', out)

        rc, out = self._run('waypoint list --match-date 2015-10-21:2015-10-22')
        self.assertEqual(0, rc)
        self.assertNotIn('wpt1', out)
        self.assertNotIn('wpt2', out)
        self.assertIn('wpt3', out)

        rc, out = self._run('waypoint list --match-date foo')
        self.assertEqual(2, rc)

        rc, out = self._run('waypoint list --match-date 2015-10-21:foo')
        self.assertEqual(2, rc)

    @mock.patch.object(FakeClient, 'add_object_to_folder')
    def test_move(self, mock_add, verbose=False, dry=False):
        rc, out = self._run('%s waypoint move wpt1 wpt2 folder2 %s' % (
            verbose and '--verbose' or '',
            dry and '--dry-run' or ''))
        self.assertEqual(0, rc)
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
        rc, out = self._run('waypoint move --match w.*2 folder2')
        self.assertEqual(0, rc)
        mock_add.assert_has_calls([mock.call('102', 'waypoint', '002')])

    @mock.patch.object(FakeClient, 'add_object_to_folder')
    def test_move_match_date(self, mock_add):
        rc, out = self._run('waypoint move --match-date 2015-10-21 folder2')
        self.assertEqual(0, rc)
        mock_add.assert_called_once_with('102', 'waypoint', '003')

    @mock.patch.object(FakeClient, 'add_object_to_folder')
    def test_move_match_none(self, mock_add):
        rc, out = self._run('waypoint move --match-date 2019-01-01 folder2')
        self.assertEqual(0, rc)
        self.assertIn('', out)
        mock_add.assert_not_called()

    @mock.patch.object(FakeClient, 'add_object_to_folder')
    def test_move_match_ambiguous(self, mock_add):
        rc, out = self._run('waypoint move folder2')
        self.assertEqual(1, rc)
        self.assertIn('Specify', out)
        mock_add.assert_not_called()

    @mock.patch.object(FakeClient, 'add_object_to_folder')
    def test_move_to_nonexistent_folder(self, mock_add):
        rc, out = self._run('waypoint move wpt1 wpt2 foobar')
        self.assertEqual(1, rc)
        self.assertIn('foobar not found', out)
        mock_add.assert_not_called()

    @mock.patch.object(FakeClient, 'remove_object_from_folder')
    def test_move_to_root(self, mock_remove):
        rc, out = self._run('waypoint move wpt1 wpt2 /')
        self.assertEqual(0, rc)
        mock_remove.assert_has_calls([mock.call('101', 'waypoint', '002')])
        self.assertIn('\'wpt1\' is already at root', out)

    @mock.patch.object(FakeClient, 'delete_object')
    def test_remove(self, mock_delete, dry=False):
        rc, out = self._run('waypoint remove wpt1 wpt2 %s' % (
            dry and '--dry-run' or ''))
        self.assertEqual(0, rc)
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
        rc, out = self._run('--verbose waypoint remove --match w.*2')
        self.assertEqual(0, rc)
        self.assertIn('Removing waypoint \'wpt2\'', out)
        mock_delete.assert_has_calls([mock.call('waypoint', '002')])

    @mock.patch.object(FakeClient, 'delete_object')
    def test_remove_missing(self, mock_delete):
        rc, out = self._run('--verbose waypoint remove wpt7')
        self.assertEqual(1, rc)
        self.assertIn('not found', out)
        mock_delete.assert_not_called()

    @mock.patch.object(FakeClient, 'delete_object')
    def test_remove_folder_empty(self, mock_delete):
        rc, out = self._run('--verbose folder remove emptyfolder')
        self.assertEqual(0, rc)
        self.assertIn('Removing', out)
        mock_delete.assert_called_once_with('folder', '104')

    @mock.patch.object(FakeClient, 'delete_object')
    def test_remove_folder_nonempty(self, mock_delete):
        rc, out = self._run('--verbose folder remove folder1')
        self.assertEqual(0, rc)
        self.assertIn('skipping', out)
        mock_delete.assert_not_called()

    @mock.patch.object(FakeClient, 'delete_object')
    def test_remove_folder_nonempty_force(self, mock_delete):
        rc, out = self._run('--verbose folder remove --force folder1')
        self.assertEqual(0, rc)
        self.assertIn('Warning', out)
        mock_delete.assert_called_once_with('folder', '101')

    @mock.patch('builtins.input')
    @mock.patch('os.isatty', return_value=True)
    @mock.patch.object(FakeClient, 'delete_object')
    def test_remove_folder_nonempty_prompt(self, mock_delete, mock_tty,
                                           mock_input):
        mock_input.return_value = ''
        rc, out = self._run('--verbose folder remove folder1')
        self.assertEqual(0, rc)
        mock_delete.assert_not_called()

        mock_input.return_value = 'y'
        rc, out = self._run('--verbose folder remove folder1')
        self.assertEqual(0, rc)
        mock_delete.assert_called_once_with('folder', '101')

    @mock.patch.object(FakeClient, 'put_object')
    def test_rename_waypoint(self, mock_put, dry=False):
        rc, out = self._run(
            '--verbose waypoint rename wpt2 wpt7 %s' % (
                dry and '--dry-run' or ''))
        self.assertEqual(0, rc)
        self.assertIn('Renaming', out)
        new_wpt = {'id': '002', 'folder': '101',
                   'properties': {'title': 'wpt7'}}
        if dry:
            mock_put.assert_not_called()
        else:
            mock_put.assert_called_once_with('waypoint', new_wpt)

    def test_rename_dry_run(self):
        self.test_rename_waypoint(dry=True)

    @mock.patch.object(FakeClient, 'put_object')
    def test_rename_track(self, mock_put):
        rc, out = self._run('--verbose track rename trk2 trk7')
        self.assertEqual(0, rc)
        self.assertIn('Renaming', out)
        new_trk = {'id': '202', 'title': 'trk7'}
        mock_put.assert_called_once_with('track', new_trk)

    @mock.patch.object(FakeClient, 'put_object')
    def test_rename_fail(self, mock_put):
        mock_put.return_value = None
        rc, out = self._run('track rename trk2 trk7')
        self.assertEqual(1, rc)
        self.assertIn('Failed to rename', out)

    @mock.patch.object(FakeClient, 'create_object')
    def test_add_waypoint(self, mock_create):
        rc, out = self._run('waypoint add foo 1.5 2.6')
        self.assertEqual(0, rc)
        self.assertEqual('', out)
        mock_create.assert_called_once_with(
            'waypoint',
            util.make_waypoint('foo', 1.5, 2.6, 0))

    @mock.patch.object(FakeClient, 'create_object')
    @mock.patch.object(FakeClient, 'add_object_to_folder')
    def test_add_waypoint_dry_run(self, mock_add, mock_create):
        rc, out = self._run('waypoint add --dry-run test 1 2')
        self.assertEqual(0, rc)
        self.assertIn('Dry run', out)
        mock_create.assert_not_called()
        mock_add.assert_not_called()

        rc, out = self._run('waypoint add --dry-run --new-folder foo test 1 2')
        self.assertEqual(0, rc)
        self.assertIn('Dry run', out)
        mock_create.assert_not_called()
        mock_add.assert_not_called()

        rc, out = self._run('waypoint add --dry-run --existing-folder folder1 '
                            'test 1 2')
        self.assertEqual(0, rc)
        self.assertIn('Dry run', out)
        mock_create.assert_not_called()
        mock_add.assert_not_called()

    @mock.patch.object(FakeClient, 'create_object')
    def test_add_waypoint_with_altitude(self, mock_create):
        rc, out = self._run('waypoint add foo 1.5 2.6 3')
        self.assertEqual(0, rc)
        self.assertEqual('', out)
        mock_create.assert_called_once_with(
            'waypoint',
            util.make_waypoint('foo', 1.5, 2.6, 3))

    @mock.patch.object(FakeClient, 'create_object')
    def test_add_waypoint_bad_data(self, mock_create):
        rc, out = self._run('waypoint add foo a 2.6')
        self.assertEqual(1, rc)
        self.assertIn('Latitude', out)

        rc, out = self._run('waypoint add foo 1.5 a')
        self.assertEqual(1, rc)
        self.assertIn('Longitude', out)

        rc, out = self._run('waypoint add foo 1.5 2.6 a')
        self.assertEqual(1, rc)
        self.assertIn('Altitude', out)

    @mock.patch.object(FakeClient, 'create_object')
    @mock.patch.object(FakeClient, 'add_object_to_folder')
    def test_add_waypoint_new_folder(self, mock_add, mock_create):
        mock_create.side_effect = [
            {'id': '1'},
            {'id': '2', 'properties': {'name': 'folder'}}]
        rc, out = self._run('waypoint add --new-folder bar foo 1.5 2.6')
        self.assertEqual(0, rc)
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
        rc, out = self._run(
            'waypoint add --existing-folder folder1 foo 1.5 2.6')
        self.assertEqual(0, rc)
        self.assertEqual('', out)
        mock_create.assert_has_calls([
            mock.call('waypoint',
                      util.make_waypoint('foo', 1.5, 2.6, 0))])
        mock_add.assert_called_once_with('101', 'waypoint', '1')

    def test_add_waypoint_existing_folder_not_found(self):
        rc, out = self._run('waypoint add --existing-folder bar foo 1.5 2.6')
        self.assertEqual(1, rc)
        self.assertIn('not found', out)

    @mock.patch.object(FakeClient, 'upload_file')
    def test_upload(self, mock_upload):
        rc, out = self._run('upload foo.gpx')
        self.assertEqual(0, rc)
        mock_upload.assert_called_once_with('foo.gpx')

    @mock.patch.object(FakeClient, 'create_object')
    def test_add_folder(self, fake_create):
        rc, out = self._run('folder add foo')
        self.assertEqual(0, rc)
        self.assertEqual('', out)
        fake_create.assert_called_once_with('folder', util.make_folder('foo'))

    @mock.patch.object(FakeClient, 'create_object')
    @mock.patch.object(FakeClient, 'add_object_to_folder')
    def test_add_folder_dry_run(self, fake_add, fake_create):
        rc, out = self._run('folder add --dry-run foo')
        self.assertEqual(0, rc)
        self.assertIn('Dry run', out)
        fake_create.assert_not_called()
        fake_add.assert_not_called()

        rc, out = self._run('folder add --dry-run --existing-folder folder1 '
                            'foo')
        self.assertEqual(0, rc)
        self.assertIn('Dry run', out)
        fake_create.assert_not_called()
        fake_add.assert_not_called()

    @mock.patch.object(FakeClient, 'create_object')
    @mock.patch.object(FakeClient, 'add_object_to_folder')
    def test_add_folder_to_existing(self, fake_add, fake_create):
        fake_create.return_value = {'id': '105'}
        rc, out = self._run('folder add --existing-folder folder1 foo')
        self.assertEqual(0, rc)
        self.assertEqual('', out)
        fake_create.assert_called_once_with('folder', util.make_folder('foo'))
        fake_add.assert_called_once_with('101', 'folder', '105')

    @mock.patch.object(FakeClient, 'create_object')
    @mock.patch.object(FakeClient, 'add_object_to_folder')
    def test_add_folder_to_existing_fail(self, fake_add, fake_create):
        fake_create.return_value = {'id': '105'}
        fake_add.return_value = None
        rc, out = self._run('folder add --existing-folder folder1 foo')
        self.assertEqual(1, rc)
        self.assertIn('failed to add', out)
        fake_create.assert_called_once_with('folder', util.make_folder('foo'))

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
            rc, out = self._run('upload --existing-folder folder1 foo.gpx')

        self.assertEqual(0, rc)

        expected = copy.deepcopy(FakeClient.FOLDERS[0])
        expected['children'] = []
        expected['maps'] = []
        expected['waypoints'] = ['002', '010', '011']
        expected['tracks'] = ['210', '211']
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
            rc, out = self._run('upload --new-folder newfolder foo.gpx')

        self.assertEqual(0, rc)

        expected = copy.deepcopy(folders_copy[-1])
        expected['children'] = []
        expected['maps'] = []
        expected['waypoints'] = ['010', '011']
        expected['tracks'] = ['210', '211']
        mock_put.assert_called_once_with('folder', expected)
        mock_delete.assert_called_once_with('folder', '105')

    @mock.patch.object(FakeClient, 'upload_file')
    @mock.patch.object(FakeClient, 'create_object')
    @mock.patch.object(FakeClient, 'delete_object')
    def test_upload_new_folder_create_fail(self, mock_delete, mock_create,
                                           mock_upload):
        mock_create.return_value = None
        rc, out = self._run('upload --new-folder foo foo.gpx')
        self.assertEqual(1, rc)
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
        rc, out = self._run('upload --existing-folder folder1 foo.gpx')
        self.assertEqual(1, rc)
        self.assertIn('Failed to move', out)
        mock_delete.assert_not_called()

    @mock.patch('builtins.open')
    def test_export(self, mock_open):
        rc, out = self._run('waypoint export wpt1 foo.gpx')
        self.assertEqual(0, rc)
        self.assertIn('Wrote \'foo.gpx\'', out)
        mock_open.assert_called_once_with('foo.gpx', 'wb')
        fake_file = mock_open.return_value.__enter__.return_value
        fake_file.write.assert_called_once_with('object 001 format gpx')

        rc, out = self._run('folder export folder1 foo.gpx')
        self.assertEqual(0, rc)
        self.assertIn('Wrote \'foo.gpx\'', out)

        rc, out = self._run('track export trk1 foo.gpx')
        self.assertEqual(0, rc)
        self.assertIn('Wrote \'foo.gpx\'', out)

        rc, out = self._run('folder export folder1 --format kml foo.kml')
        self.assertEqual(0, rc)
        self.assertIn('Wrote \'foo.kml\'', out)

        rc, out = self._run('folder export folder1 --format jpg foo')
        self.assertEqual(2, rc)
