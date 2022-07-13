import datetime
import functools
import logging
import os
import pytz
import string
import tzlocal
from xml.etree import ElementTree as ET

LOG = logging.getLogger(__name__)


ICON_ALIASES = {
    'blue': 'blue-pin-down.png',
    'black': 'black-pin.png',
    'brown': 'brown-pin.png',
    'gray': 'gray-pin.png',
    'green': 'green-pin.png',
    'orange': 'orange-pin.png',
    'purple': 'purple-pin.png',
    'red': 'red-pin-down.png',
    'white': 'white-pin.png',
    'yellow': 'yellow-pin.png',
    'airport': 'airport-24.png',
    'bicycle': 'bicycle-24.png',
    'building': 'building-24.png',
    'cafe': 'cafe-24.png',
    'camera': 'camera-24.png',
    'campsite': 'campsite-24.png',
    'car': 'car-24.png',
    'cemetary': 'cemetary-24.png',
    'chemist': 'chemist-24.png',
    'circle': 'circle-24.png',
    'city': 'city-24.png',
    'dam': 'dam-24.png',
    'disability': 'disability-24.png',
    'dog-park': 'dog-park-24.png',
    'emergency-telephone': 'emergency-telephone-24.png',
    'fast-food': 'fast-food-24.png',
    'fire-station': 'fire-station-24.png',
    'fuel': 'fuel-24.png',
    'garden': 'garden-24.png',
    'golf': 'golf-24.png',
    'harbor': 'harbor-24.png',
    'heart': 'heart-24.png',
    'heliport': 'heliport-24.png',
    'hospital': 'hospital-24.png',
    'lighthouse': 'lighthouse-24.png',
    'lodging': 'lodging-24.png',
    'logging': 'logging-24.png',
    'minefield': 'minefield-24.png',
    'mobilephone': 'mobilephone-24.png',
    'oil-well': 'oil-well-24.png',
    'park': 'park-24.png',
    'parking': 'parking-24.png',
    'pitch': 'pitch-24.png',
    'playground': 'playground-24.png',
    'polling-place': 'polling-place-24.png',
    'prison': 'prison-24.png',
    'rail': 'rail-24.png',
    'restaurant': 'restaurant-24.png',
    'skiing': 'skiing-24.png',
    'square': 'square-24.png',
    'star': 'star-24.png',
    'suitcase': 'suitcase-24.png',
    'swimming': 'swimming-24.png',
    'toilets': 'toilets-24.png',
    'triangle': 'triangle-24.png',
    'water': 'water-24.png',
    'wetland': 'wetland-24.png',
}


COLOR_ALIASES = {
    'red': '#F42410',
    'lightred': '#F90553',
    'purple': '#B60DC3',
    'navy': '#5E23CA',
    'blue': '#2D3FC7',
    'lightblue': '#0498FF',
    'teal': '#00ACF8',
    'aqua': '#00C3DD',
    'forestgreen': '#009B89',
    'green': '#36C03B',
    'lightgreen': '#8AD42F',
    'goldenrod': '#DCEE0E',
    'yellow': '#FFF011',
    'amber': '#FFC900',
    'orange': '#FF9D00',
    'firetruck': '#FF4D04',
    'brown': '#784D3E',
    'grey': '#A4A4A4',
    'slate': '#577B8E',
    'black': '#000000',
}


# From https://www8.garmin.com/xmlschemas/GpxExtensionsv3.xsd
GPXX_COLORS_TO_GAIA = {
    'Black': 'black',
    'DarkRed': 'red',
    'DarkGreen': 'forestgreen',
    'DarkYellow': 'goldenrod',
    'DarkBlue': 'navy',
    'DarkMagenta': 'purple',
    'DarkCyan': 'teal',
    'LightGray': 'grey',
    'DarkGray': 'slate',
    'Red': 'lightred',
    'Green': 'green',
    'Yellow': 'yellow',
    'Blue': 'blue',
    'Magenta': 'purple',
    'Cyan': 'aqua',
    'White': '#000000',
    'Transparent': 'brown',
}


def date_parse(thing, property_name='time_created'):
    """Parse a local datetime from a thing with a datestamp.

    This attempts to find a datestamp in an object and parse it for
    use in the local timezone.

    Something like this is required::

      {'id': '1234', 'title': 'Foo', 'time_created': '2019-01-01T10:11:12Z'}

    :param thing: A raw object from the API
    :type thing: dict
    :returns: A localized tz-aware `datetime` or None if no datestamp is found.
    :rtype: :class:`datetime.datetime`
    """
    if property_name in thing:
        ds = thing[property_name]
    elif 'properties' in thing:
        ds = thing['properties'].get(property_name)
    elif 'features' in thing:
        ds = thing['features'][0]['properties'].get(property_name)
    else:
        ds = None
    if not ds:
        return None

    if 'Z' in ds:
        dt = datetime.datetime.strptime(ds, '%Y-%m-%dT%H:%M:%SZ')
    elif '.' in ds:
        dt = datetime.datetime.strptime(ds, '%Y-%m-%dT%H:%M:%S.%f')
    else:
        dt = datetime.datetime.strptime(ds, '%Y-%m-%dT%H:%M:%S')

    dt = pytz.utc.localize(dt)
    return dt.astimezone(tzlocal.get_localzone())


def datefmt(thing, property_name='time_created'):
    """Nicely format a thing with a datestamp.

    See :func:`~date_parse` for more information.

    :param thing: A ``dict`` raw object from the API.
    :type thing: dict
    :returns: A nicely-formatted date string, or ``'?'`` if none is found
              or is parseable
    :rtype: `str`
    """
    localdt = date_parse(thing, property_name=property_name)
    if localdt:
        return localdt.strftime('%d %b %Y %H:%M:%S')
    else:
        return '?'


def make_waypoint(name, lat, lon, alt=0, notes='', icon=''):
    """Make a raw waypoint object.

    This returns an object suitable for sending to the API.

    :param lat: A ``float`` representing latitude
    :type lat: float
    :param lon: A ``float`` representing longitude
    :type lon: float
    :param alt: A ``float`` representing altitude in meters
    :type alt: float
    :param notes: A ``str`` representing the notes field
    :type notes: str
    :param icon: A ``str`` representing the icon (one of the values
                 supported by gaiagps, for example ``blue-pin-down.png``)
    :type icon: str
    :returns: A ``dict`` object
    :rtype: `dict`
    """
    return {
        'type': 'Feature',
        'properties': {
            'title': name,
            'notes': notes,
            'icon': icon,
        },
        'geometry': {
            'type': 'Point',
            'coordinates': [lon, lat, alt],
        },
    }


def make_folder(name):
    """Make a folder object.

    This returns an object suitable for sending to the API.

    :param name: A ``str`` representing the folder name
    :type name: str
    :returns: A ``dict`` object
    :rtype: `dict`
    """
    return {'title': name}


def make_tree(folders):
    """Creates a hierarchical structure of folders.

    This takes a flat list of folder objects and returns
    a nested ``dict`` with subfolders inside their parent's
    ``subfolders`` key. A new root folder structure is at the
    top, with a name of ``/``.

    :param folders: A flat ``list`` of folders like you get from
                    :func:`~gaiagps.apiclient.GaiaClient.list_objects`
    :type folders: list
    :returns: A hierarchical ``dict`` of folders
    :rtype: `dict`
    """
    folders_by_id = {folder['id']: folder
                     for folder in folders}
    root = {
        'properties': {
            'name': '/',
            'waypoints': {},
            'tracks': {},
        },
    }

    for folder in folders:
        if folder.get('parent'):
            parent = folders_by_id[folder['parent']]
        else:
            parent = root

        parent.setdefault('subfolders', {})
        parent['subfolders'][folder['id']] = folder

    return root


def resolve_tree(client, folder):
    """Walk the tree and flesh out folders with waypoint/track data.

    This takes a hierarchical folder tree from :func:`make_tree` and
    replaces the folder descriptions with full definitions, as you
    would get from :func:`~gaiagps.apiclient.GaiaClient.get_object`.

    :param client: An instance of :class:`~gaiagps.apiclient.GaiaClient`
    :type client: GaiaClient
    :param folder: A root folder of a hierarchical tree from
                   :func:`make_tree`
    :type folder: dict
    :returns: A hierarchical tree of full folder definitions.
    :rtype: `dict`
    """

    if 'id' in folder:
        LOG.debug('Resolving %s' % folder['id'])
        updated = client.get_object('folder', id_=folder['id'])
        subf = folder.get('subfolders', {})
        folder.clear()
        folder.update(updated)
        folder['subfolders'] = subf
    else:
        # This is the fake root folder
        LOG.debug('Resolving root folder (by force)')
        folder['properties']['waypoints'] = [
            w for w in client.list_objects('waypoint')
            if w['folder'] == '']
        folder['properties']['tracks'] = [
            t for t in client.list_objects('track')
            if t['folder'] == '']

    for subfolder in folder.get('subfolders', {}).values():
        LOG.debug('Descending into %s' % subfolder['id'])
        resolve_tree(client, subfolder)

    return folder


def title_sort(iterable):
    """Return a sorted list of items by title.

    :param iterable: Items to sort
    :returns: Items in title sort order
    """
    return sorted(iterable, key=lambda e: e['title'])


def name_sort(iterable):
    """Return a sorted list of items by name.

    :param iterable: Items to sort
    :returns: Items in name sort order
    """
    return sorted(iterable, key=lambda e: e.get('name', ''))


def pprint_folder(folder, indent=0, long=False):
    """Print a tree of folder contents.

    This prints a pseudo-filesystem view of a folder tree to the
    console.

    :param folder: A folder tree root from :func:`resolve_tree`
    :type folder: dict
    :param indent: Number of spaces to indent the first level
    :type indent: int
    """
    midchild = b'\xe2\x94\x9c\xe2\x94\x80\xe2\x94\x80'.decode()
    lastchild = b'\xe2\x94\x94\xe2\x94\x80\xe2\x94\x80'.decode()

    def format_thing(thing):
        fields = []
        if long:
            fields.append(datefmt(thing))
        fields.append(thing.get('title') or
                      thing.get('properties')['name'])
        return ' '.join(fields)

    if indent == 0:
        print('/')

    pfx = (' ' * indent) + midchild
    for subf in name_sort(folder.get('subfolders', {}).values()):
        print('%s %s/' % (pfx, format_thing(subf)))
        pprint_folder(subf, indent=indent + 4, long=long)

    children = (
        [('W', w) for w in title_sort(
            folder['properties']['waypoints'])] +
        [('T', t) for t in title_sort(
            folder['properties']['tracks'])])

    while children:
        char, child = children.pop(0)
        if children:
            pfx = (' ' * indent) + midchild
        else:
            pfx = (' ' * indent) + lastchild
        print('%s [%s] %s' % (pfx, char, format_thing(child)))


def validate_lat(lat):
    """Validate and normalize a latitude

    Only decimal degrees is supported

    :param lat: A latitude string
    :type lat: str
    :returns: A latitude
    :rtype: `float`
    :raises ValueError: If the latitude is not parseable or within constraints
    """
    try:
        lat = float(lat)
    except ValueError:
        raise ValueError('Latitude must be in decimal degree format')

    if lat < -90 or lat > 90:
        raise ValueError('Latitude must be between -90 and 90')

    return lat


def validate_lon(lon):
    """Validate and normalize a longitude

    Only decimal degrees is supported

    :param lon: A longitude string
    :type lon: str
    :returns: A longitude
    :rtype: `float`
    :raises ValueError: If the longitude is not parseable or within constraints
    """
    try:
        lon = float(lon)
    except ValueError:
        raise ValueError('Longitude must be in decimal degree format')

    if lon < -180 or lon > 180:
        raise ValueError('Longitude must be between -180 and 180')

    return lon


def validate_alt(alt):
    """Validate and normalize an altitude

    Only meters are supported

    :param alt: An altitude string
    :type alt: str
    :returns: An altitude
    :rtype: `float`
    :raises ValueError: If the altitude is not parseable or within constraints
    """
    try:
        alt = int(alt)
    except ValueError:
        raise ValueError('Altitude must be a positive integer number of '
                         'meters')

    if alt < 0:
        raise ValueError('Altitude must be positive')

    return alt


def is_id(idstr):
    """Detect if a string is likely an API identifier

    :param idstr: An ID string to be examined
    :type idstr: str
    :returns: ``True`` if the string is an identifier, ``False`` otherwise
    :rtype: `bool`
    """
    return (len(idstr) in (36, 32, 40) and
            all(c in string.hexdigits + '-' for c in idstr))


def get_editor():
    """Return a path to an editor command, if possible.

    :returns: Path to an editor command or None if one is not found
    """

    editor = os.environ.get('EDITOR', '/usr/bin/editor')
    if editor and os.access(editor, os.X_OK):
        return editor


def strip_gpx_extensions(source_file, dest_file):
    """Strip any GPX extensions from a file.

    Remove any GPX extensions from source_file and write the
    result to dest_file.

    :param source_file: Source filename
    :type source_file: str
    :param dest_file: Destination filename
    :type dest_file: str
    :raises Exception: If the source file is not a GPX file
    """
    namespaces = {'': 'http://www.topografix.com/GPX/1/1'}
    for ns, url in namespaces.items():
        ET.register_namespace(ns, url)

    try:
        tree = ET.parse(source_file)
    except ET.ParseError:
        raise Exception('Input is not a GPX file')

    root = tree.getroot()
    if root.tag != '{http://www.topografix.com/GPX/1/1}gpx':
        raise Exception('Input is not a GPX file')

    # Remove the extension schemas
    xsi = '{http://www.w3.org/2001/XMLSchema-instance}schemaLocation'
    nslist = root.attrib[xsi]
    nslist = ' '.join(x for x in nslist.split() if 'GPX/1/1' in x)
    root.attrib[xsi] = nslist

    # For each, wpt, trk, etc, remove the <extensions> if present
    for elem in root.findall('*'):
        ext = elem.find('{http://www.topografix.com/GPX/1/1}extensions')
        if ext:
            elem.remove(ext)

    tree.write(dest_file)


def get_track_colors_from_gpx(source_file):
    """Return a dict of track names and colors from a GPX file.

    :param source_file: Source GPX filename
    :type source_file: str
    :returns: Dict of name:color
    """
    namespaces = {'gpx': 'http://www.topografix.com/GPX/1/1',
                  'gpxx': 'http://www.garmin.com/xmlschemas/GpxExtensions/v3'}
    for ns, url in namespaces.items():
        ET.register_namespace(ns, url)

    try:
        tree = ET.parse(source_file)
    except ET.ParseError:
        raise Exception('Input is not a GPX file')

    root = tree.getroot()
    if root.tag != '{http://www.topografix.com/GPX/1/1}gpx':
        raise Exception('Input is not a GPX file')

    tracks = {}
    for i, trk in enumerate(root.findall('gpx:trk', namespaces)):
        names = trk.findall('gpx:name', namespaces)
        if not names:
            LOG.info('Skipping unnamed track #%i' % (i + 1))
            continue
        name = names[0].text
        colors = trk.findall(
            'gpx:extensions/gpxx:TrackExtension/gpxx:DisplayColor',
            namespaces)
        if not colors:
            LOG.info('Skipping uncolored track #%i (%s)' % (i + 1, name))
            continue
        color = colors[0].text

        tracks[name] = color

    return tracks


class ThingFormatter(object):
    """Format helper for GaiaGPS objects.

    This is intended to digest an object from the API and provide
    a relatively safe dict-like formatting object for strings.

    Example usage:

       obj = client.get_object( ... )
       fmt = ThingFormatter(obj)
       print('%(title)s' % fmt)

    :param thing: An object from the GaiaGPS API as returned from
                  :class:`GaiaClient`
    :type thing: dict
    """

    def __init__(self, thing):
        self._thing = thing

    @property
    def keys(self):
        """A list of keys we definitely support for formatting"""
        static = set([k.replace('format_', '') for k in dir(self)
                      if k.startswith('format_') and
                      callable(getattr(self, k))])
        dynamic = set(self._find_props().keys())
        return static | dynamic

    def __getitem__(self, item):
        try:
            method = getattr(self, 'format_%s' % item)
        except AttributeError:
            if item in self._find_props():
                method = functools.partial(self._find_props().get, item)
            else:
                LOG.info('Unsupported format key %r' % item)
                method = lambda: 'UNSUPPORTED'  # noqa

        try:
            return method()
        except Exception as e:
            LOG.info('Error formatting %r: %s' % (item, e))
            LOG.debug(self._thing)
            return 'ERROR'

    def _find_props(self):
        try:
            return self._thing['properties']
        except KeyError:
            try:
                return self._thing['features'][0]['properties']
            except KeyError:
                return {}

    def format_title(self):
        """The title or name"""
        props = self._find_props()
        try:
            return props['title']
        except KeyError:
            return props['name']

    def format_created(self):
        """The "time_created" datestamp"""
        return datefmt(self._find_props(), 'time_created')

    def format_updated(self):
        """The "updated_date" datestamp"""
        return datefmt(self._find_props(), 'updated_date')

    def format_id(self):
        """The internal GaiaGPS identifier"""
        return self._thing['id']

    def format_altitude(self):
        """The altitude (elevation)"""
        return self._find_props()['elevation']

    def format_public(self):
        """The "public" or "private" status"""
        return self._find_props()['public'] and 'public' or 'private'
