import datetime
import logging
import string

LOG = logging.getLogger(__name__)


def datefmt(thing):
    """Nicely format a thing with a datestamp.

    This attempts to find a datestamp in an object, parse, and format
    it for display. Something like this is required::

      {'id': '1234', 'title': 'Foo', 'time_created': '2019-01-01T10:11:12Z'}

    :param thing: A ``dict`` raw object from the API.
    :returns: A nicely-formatted date string, or ``'?'`` if none is found
              or is parseable
    """
    ds = thing.get('time_created') or thing['properties'].get('time_created')
    if not ds:
        return '?'

    if 'Z' in ds:
        dt = datetime.datetime.strptime(ds, '%Y-%m-%dT%H:%M:%SZ')
    elif '.' in ds:
        dt = datetime.datetime.strptime(ds, '%Y-%m-%dT%H:%M:%S.%f')
    else:
        dt = datetime.datetime.strptime(ds, '%Y-%m-%dT%H:%M:%S')

    return dt.strftime('%d %b %Y %H:%M:%S')


def make_waypoint(name, lat, lon, alt=0):
    """Make a raw waypoint object.

    This returns an object suitable for sending to the API.

    :param lat: A ``float`` representing latitude
    :param lon: A ``float`` representing longitude
    :param alt: A ``float`` representing altitude in meters
    :returns: A ``dict`` object
    """
    return {
        'type': 'Feature',
        'properties': {
            'title': name,
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
    :returns: A ``dict`` object
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
    :returns: A hierarchical ``dict`` of folders
    """
    folders_by_id = {folder['id']: folder
                     for folder in folders}
    root = {
        'properties': {
            'name': '/',
            'waypoints': [],
            'tracks': [],
        },
    }

    for folder in folders:
        if folder['parent']:
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
    :param folder: A root folder of a hierarchical tree from
                   :func:`make_tree`
    :returns: A hierarchical tree of full folder definitions.
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


def pprint_folder(folder, indent=0):
    """Print a tree of folder contents.

    This prints a pseudo-filesystem view of a folder tree to the
    console.

    :param folder: A folder tree root from :func:`resolve_tree`
    :param indent: Number of spaces to indent the first level
    """
    pfx = ' ' * indent
    for subf in name_sort(folder.get('subfolders', {}).values()):
        print()
        print('%sDIR %s %s/' % (
            pfx, datefmt(subf),
            subf['properties']['name']))
        pprint_folder(subf, indent + 4)

    if folder.get('subfolders'):
        print()

    for waypoint in title_sort(folder['properties']['waypoints']):
        print('%sWPT %s %s' % (
            pfx, datefmt(waypoint),
            waypoint['title']))
    for track in title_sort(folder['properties']['tracks']):
        print('%sTRK %s %s' % (
            pfx, datefmt(track),
            track['title']))


def validate_lat(lat):
    """Validate and normalize a latitude

    Only decimal degrees is supported

    :param lat: A ``str`` latitude
    :returns: A ``float`` representing the latitude
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

    :param lon: A ``str`` longitude
    :returns: A ``float`` representing the longitude
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

    :param alt: A ``str`` altitude
    :returns: A ``float`` representing the altitude
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

    :param idstr: A ``str`` to be examined
    :returns: ``True`` if the string is an identifier, ``False`` otherwise
    """
    return (len(idstr) in (36, 32) and
            all(c in string.hexdigits + '-' for c in idstr))
