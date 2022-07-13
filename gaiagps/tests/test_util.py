import copy
import datetime
import io
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
               '0c94be3d-6fd9-45a0-9ca5-e8fd6969b7d3',
               '6505ccef3cfffd6229e71f1528650b9edf8bfb47']
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

    @mock.patch('builtins.open')
    def test_strip_gpx_extensions(self, mock_open):
        input = io.BytesIO(GPX_WITH_EXTENSIONS.encode())
        output = io.StringIO()
        mock_open.side_effect = [input, output]

        # Avoid letting the StringIO be closed and freeing the buffer
        with mock.patch.object(output, 'close'):
            util.strip_gpx_extensions('input-file', 'output-file')

        self.assertIn('<wpt', output.getvalue())
        self.assertNotIn('<extensions>', output.getvalue())

    @mock.patch('builtins.open')
    def test_strip_gpx_extensions_errors(self, mock_open):
        input = io.BytesIO(b'foo')
        mock_open.return_value = input
        self.assertRaises(Exception,
                          util.strip_gpx_extensions,
                          'input-file', 'output-file')

        input = io.BytesIO(b'<kml></kml>')
        mock_open.return_value = input
        self.assertRaises(Exception,
                          util.strip_gpx_extensions,
                          'input-file', 'output-file')

    @mock.patch('builtins.open')
    def test_get_track_colors_from_gpx(self, mock_open):
        input = io.BytesIO(GPX_WITH_EXTENSIONS.encode())
        mock_open.return_value = input
        self.assertEqual({'gaiagpsclient test data test track': 'Red'},
                         util.get_track_colors_from_gpx('foo'))

    @mock.patch('builtins.open')
    def test_get_track_colors_from_gpx_errors(self, mock_open):
        input = io.BytesIO(b'foo')
        mock_open.return_value = input
        self.assertRaises(Exception,
                          util.get_track_colors_from_gpx, 'input-file')

        input = io.BytesIO(b'<kml></kml>')
        mock_open.return_value = input
        self.assertRaises(Exception,
                          util.get_track_colors_from_gpx, 'input-file')

        noname = copy.copy(GPX_WITH_EXTENSIONS)
        noname = noname.replace(
            '<name>gaiagpsclient test data test track</name>', '')
        input = io.BytesIO(noname.encode())
        mock_open.return_value = input
        self.assertEqual({}, util.get_track_colors_from_gpx('input-file'))

        noexts = copy.copy(GPX_WITH_EXTENSIONS)
        noexts = noexts.replace('<gpxx:DisplayColor>Red</gpxx:DisplayColor>',
                                '')
        input = io.BytesIO(noexts.encode())
        mock_open.return_value = input
        self.assertEqual({}, util.get_track_colors_from_gpx('input-file'))

    def test_thingformatter_keys(self):
        self.assertEqual(
            sorted(['title', 'created', 'updated', 'id',
                    'altitude', 'public', 'notes']),
            sorted(util.ThingFormatter({'properties': {'notes': ''}}).keys))

    def test_thingformatter_wpt(self):
        f = util.ThingFormatter(TEST_WPT)
        self.assertEqual('TestPoint 8873927a-820b-4a75-b15a-c3e40d383006',
                         '%(title)s %(id)s' % f)

        # Complex type formatting
        self.assertEqual('45.5 / -122.7',
                         '%(latitude).1f / %(longitude).1f' % f)

        # Implicit "anything in properties" should also work
        self.assertEqual('TestPoint True',
                         '%(title)s %(is_active)s' % f)

    def test_thingformatter_trk(self):
        f = util.ThingFormatter(TEST_TRK)
        self.assertEqual('ph-closed2 b0298a9a30b073b3493ca54e3a1417bb',
                         '%(title)s %(id)s' % f)
        self.assertEqual('0000',
                         '%(moving_speed)04i' % f)

    def test_thingformatter_edges(self):
        # Altitude will fail with KeyError and trigger the error path
        f = util.ThingFormatter({'properties': {}})
        self.assertEqual('ERROR', f['altitude'])

        # General property fallback, missing key
        f = util.ThingFormatter({})
        self.assertEqual('UNSUPPORTED', f['snarf'])


GPX_WITH_EXTENSIONS = """<?xml version="1.0"?>
<gpx xmlns="http://www.topografix.com/GPX/1/1" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:wptx1="http://www.garmin.com/xmlschemas/WaypointExtension/v1" xmlns:gpxtrx="http://www.garmin.com/xmlschemas/GpxExtensions/v3" xmlns:gpxtpx="http://www.garmin.com/xmlschemas/TrackPointExtension/v1" xmlns:gpxx="http://www.garmin.com/xmlschemas/GpxExtensions/v3" xmlns:trp="http://www.garmin.com/xmlschemas/TripExtensions/v1" xmlns:adv="http://www.garmin.com/xmlschemas/AdventuresExtensions/v1" xmlns:prs="http://www.garmin.com/xmlschemas/PressureExtension/v1" xmlns:tmd="http://www.garmin.com/xmlschemas/TripMetaDataExtensions/v1" xmlns:vptm="http://www.garmin.com/xmlschemas/ViaPointTransportationModeExtensions/v1" xmlns:ctx="http://www.garmin.com/xmlschemas/CreationTimeExtension/v1" xmlns:gpxacc="http://www.garmin.com/xmlschemas/AccelerationExtension/v1" xmlns:gpxpx="http://www.garmin.com/xmlschemas/PowerExtension/v1" xmlns:vidx1="http://www.garmin.com/xmlschemas/VideoExtension/v1" creator="Garmin Desktop App" version="1.1" xsi:schemaLocation="http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd http://www.garmin.com/xmlschemas/WaypointExtension/v1 http://www8.garmin.com/xmlschemas/WaypointExtensionv1.xsd http://www.garmin.com/xmlschemas/TrackPointExtension/v1 http://www.garmin.com/xmlschemas/TrackPointExtensionv1.xsd http://www.garmin.com/xmlschemas/GpxExtensions/v3 http://www8.garmin.com/xmlschemas/GpxExtensionsv3.xsd http://www.garmin.com/xmlschemas/ActivityExtension/v1 http://www8.garmin.com/xmlschemas/ActivityExtensionv1.xsd http://www.garmin.com/xmlschemas/AdventuresExtensions/v1 http://www8.garmin.com/xmlschemas/AdventuresExtensionv1.xsd http://www.garmin.com/xmlschemas/PressureExtension/v1 http://www.garmin.com/xmlschemas/PressureExtensionv1.xsd http://www.garmin.com/xmlschemas/TripExtensions/v1 http://www.garmin.com/xmlschemas/TripExtensionsv1.xsd http://www.garmin.com/xmlschemas/TripMetaDataExtensions/v1 http://www.garmin.com/xmlschemas/TripMetaDataExtensionsv1.xsd http://www.garmin.com/xmlschemas/ViaPointTransportationModeExtensions/v1 http://www.garmin.com/xmlschemas/ViaPointTransportationModeExtensionsv1.xsd http://www.garmin.com/xmlschemas/CreationTimeExtension/v1 http://www.garmin.com/xmlschemas/CreationTimeExtensionsv1.xsd http://www.garmin.com/xmlschemas/AccelerationExtension/v1 http://www.garmin.com/xmlschemas/AccelerationExtensionv1.xsd http://www.garmin.com/xmlschemas/PowerExtension/v1 http://www.garmin.com/xmlschemas/PowerExtensionv1.xsd http://www.garmin.com/xmlschemas/VideoExtension/v1 http://www.garmin.com/xmlschemas/VideoExtensionv1.xsd">
  <metadata>
    <link href="http://www.garmin.com">
      <text>Garmin International</text>
    </link>
    <time>2019-05-14T21:19:51Z</time>
    <bounds maxlat="43.528282642364502" maxlon="-120.645139217376709" minlat="42.847406901419163" minlon="-121.981050968170166"/>
  </metadata>
  <wpt lat="43.1944465264678" lon="-121.594601729884744">
    <ele>1621.01171875</ele>
    <time>2015-01-03T19:46:03Z</time>
    <name>gaiagpsclient test data 10</name>
    <sym>Flag, Blue</sym>
    <type>user</type>
    <extensions>
      <gpxx:WaypointExtension>
        <gpxx:DisplayMode>SymbolAndName</gpxx:DisplayMode>
      </gpxx:WaypointExtension>
      <wptx1:WaypointExtension>
        <wptx1:DisplayMode>SymbolAndName</wptx1:DisplayMode>
      </wptx1:WaypointExtension>
      <ctx:CreationTimeExtension>
        <ctx:CreationTime>2015-01-03T19:46:03Z</ctx:CreationTime>
      </ctx:CreationTimeExtension>
    </extensions>
  </wpt>
  <trk>
    <name>gaiagpsclient test data test track</name>
    <extensions>
      <gpxx:TrackExtension>
        <gpxx:DisplayColor>Red</gpxx:DisplayColor>
      </gpxx:TrackExtension>
    </extensions>
    <trkseg>
      <trkpt lat="45.45985241420567" lon="-122.516925316303968">
        <ele>230.43359375</ele>
        <time>2018-07-11T15:25:05Z</time>
      </trkpt>
      <trkpt lat="45.35285241620567" lon="-122.914925316303968">
        <ele>230.43359375</ele>
        <time>2018-07-11T15:35:15Z</time>
      </trkpt>
    </trkseg>
  </trk>
</gpx>
"""  # noqa


TEST_WPT = {'geometry': {'coordinates': [-122.68157958984, 45.499278510068024],
                         'type': 'Point'},
            'id': '8873927a-820b-4a75-b15a-c3e40d383006',
            'properties': {'attr': 'null',
                           'deleted': True,
                           'elevation': 0,
                           'icon': 'chemist-24.png',
                           'id': '8873927a-820b-4a75-b15a-c3e40d383006',
                           'is_active': True,
                           'latitude': 45.499278510068024,
                           'longitude': -122.68157958984,
                           'notes': 'Multi1a',
                           'photos': [],
                           'public': False,
                           'revision': 5210,
                           'time_created': '2019-05-15T14:20:50Z',
                           'title': 'TestPoint',
                           'track_id': '',
                           'updated_date': '2019-05-15T14:20:50Z',
                           'writable': True},
            'type': 'Feature'}


TEST_TRK = {'features': [{'geometry': {'coordinates': [[[-120.221565,
                                                         44.600239,
                                                         731.0,
                                                         1554770257.0],
                                                        [-120.271149,
                                                         44.739372,
                                                         463.0,
                                                         978307200.0]]],
                                       'type': 'MultiLineString'},
                          'properties': {'average_speed': -3.585747935330069e-05,  # noqa
                                         'color': '#0497ff',
                                         'comment_count': 0,
                                         'cover_photo_id': None,
                                         'db_insert_date': '2019-04-09T00:43:50Z',  # noqa
                                         'deleted': False,
                                         'distance': 20670.5121643181,
                                         'favorite_count': 0,
                                         'flag': None,
                                         'hexcolor': '#0497ff',
                                         'id': 'b0298a9a30b073b3493ca54e3a1417bb',  # noqa
                                         'is_active': True,
                                         'is_favorite': False,
                                         'last_updated_on_server': '2019-05-20T20:36:35.124',  # noqa
                                         'latitude': 44.66554264292247,
                                         'longitude': -120.24934389109352,
                                         'moving_speed': 0,
                                         'moving_time': -576463057.0,
                                         'notes': 'These are newnotes',
                                         'preferred_link': '/datasummary/track/b0298a9a30b073b3493ca54e3a1417bb/',  # noqa
                                         'public': False,
                                         'revision': 5213,
                                         'routing_mode': None,
                                         'source': '',
                                         'stopped_time': 0.0,
                                         'time_created': '2019-04-09T00:43:47Z',  # noqa
                                         'title': 'ph-closed2',
                                         'total_ascent': 98.0,
                                         'total_descent': 366.0,
                                         'total_time': -576463057.0,
                                         'track_type': '',
                                         'updated_date': '2019-05-20T20:36:35Z',  # noqa
                                         'uploaded_gpx_to_osm': None,
                                         'user_displayname': 'dsmith',
                                         'user_email': 'dsmith@danplanet.com',
                                         'user_id': 454408,
                                         'user_photo_count': 0,
                                         'username': 'dsmith@danplanet.com',
                                         'writable': True},
                          'style': {'stroke': '#0497ff'},
                          'type': 'Feature'}],
            'id': 'b0298a9a30b073b3493ca54e3a1417bb',
            'type': 'FeatureCollection'}
