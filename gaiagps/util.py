import datetime
import logging
import string

LOG = logging.getLogger(__name__)


def datefmt(thing):
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
    return {'title': name}


def make_tree(folders):
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
        if folder['parent']:
            parent = folders_by_id[folder['parent']]
        else:
            parent = root

        parent.setdefault('subfolders', {})
        parent['subfolders'][folder['id']] = folder

    return root


def resolve_tree(client, folder):
    """Walk the tree and flesh out folders with waypoint/track data"""

    if 'id' in folder:
        LOG.debug('Resolving %s' % folder['id'])
        updated = client.get_object('folder', id_=folder['id'])
        subf = folder.get('subfolders', {})
        folder.clear()
        folder.update(updated)
        folder['subfolders'] = subf

    for subfolder in folder.get('subfolders', {}).values():
        LOG.debug('Descending into %s' % subfolder['id'])
        resolve_tree(client, subfolder)

    return folder


def title_sort(iterable):
    return sorted(iterable, key=lambda e: e['title'])


def name_sort(iterable):
    return sorted(iterable, key=lambda e: e.get('name', ''))


def pprint_folder(folder, indent=0):
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
    try:
        lat = float(lat)
    except ValueError:
        raise ValueError('Latitude must be in decimal degree format')

    if lat < -90 or lat > 90:
        raise ValueError('Latitude must be between -90 and 90')

    return lat


def validate_lon(lon):
    try:
        lon = float(lon)
    except ValueError:
        raise ValueError('Longitude must be in decimal degree format')

    if lon < -180 or lon > 180:
        raise ValueError('Longitude must be between -180 and 180')

    return lon


def validate_alt(alt):
    try:
        alt = int(alt)
    except ValueError:
        raise ValueError('Altitude must be a positive integer number of '
                         'meters')

    if alt < 0:
        raise ValueError('Altitude must be positive')

    return alt


def is_id(idstr):
    return (len(idstr) in (36, 32) and
            all(c in string.hexdigits + '-' for c in idstr))
