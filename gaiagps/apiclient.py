import itertools
import logging
import os
import re
import requests
import sys
import pprint


logging.getLogger('requests').setLevel(logging.ERROR)

BASE = 'https://www.gaiagps.com'
LOG = logging.getLogger(__name__)


class AuthFailure(Exception):
    """Indicates that login to gaiagps.com was not possible."""
    pass


class NotFound(Exception):
    """Indicates that an identified item could not be found."""
    pass


def gurl(*sub):
    """Build a gaiagps.com url from components.

    Ensure that the resulting URL ends in a slash and that none
    of the sub elements that have a slash cause duplicates.
    """
    return '/'.join(itertools.chain([BASE],
                                    [x.strip('/') for x in sub],
                                    ['']))


def match(iterable, key, pattern):
    """Find items in iterable where ``key`` matches ``pattern``.

    :param iterable: Items to search
    :param key: The key to match
    :param pattern: A regular expression to use for matching
    :returns: A list of objects that match
    """
    return [i for i in iterable
            if re.search(pattern, i[key])]


def find(iterable, key, value):
    """Find exactly one item in iterable for which ``key`` equals ``value``.

    :param iterable: Items to search
    :param key: The key to match
    :param value: The value to match
    :raises NotFound: If a match is not found
    :raises RuntimeError: If multiple matches are found
    """
    matches = [i for i in iterable
               if i[key] == value]
    if not matches:
        raise NotFound('Item with %s=%s not found' % (key, value))
    elif len(matches) > 1:
        raise RuntimeError('Multiple items with %s=%s found' % (key, value))
    return matches[0]


def _logresp(r):
    LOG.debug('Response: %s %s: %r' % (r.status_code, r.reason,
                                       r.content))


USER_AGENT_ELEMENTS = [
    'Python/%s.%s.%s' % (sys.version_info.major,
                         sys.version_info.minor,
                         sys.version_info.micro),
    sys.platform,
]
try:
    USER_AGENT_ELEMENTS.append('requests/%s' % requests.__version__)
except Exception:
    pass
USER_AGENT = 'https://github.com/kk7ds/gaiagpsclient (%s)' % (
    '; '.join(USER_AGENT_ELEMENTS))


class GaiaClient(object):
    """A low-level client for gaiagps.com.

    Initialize and login (if necessary) to gaiagps.com. If
    a cookiejar is provided and the session stored within is
    still active, login credentials are not used.

    :param username: Username for gaiagps.com
    :type username: str
    :param password: Password for gaiagps.com
    :type password: str
    :param cookies: A cookie jar or ``None``
    :type cookies: http.cookiejar.CookieJar
    :raises AuthFailure: if login fails
    :raises RuntimeError: if session is stale and credentials are
            not provided
    """

    def __init__(self, username, password, cookies=None):
        self.username = username
        self.password = password
        self.s = requests.Session()
        self.s.headers = {
            'User-Agent': USER_AGENT,
            'Accept': 'application/json, text/plain, */*',
        }
        if cookies is not None:
            self.s.cookies = cookies

        if not self.test_auth():
            if not all([self.username, self.password]):
                raise RuntimeError('Session expired; '
                                   'username and password are required')
            LOG.debug('Not authenticated, logging in...')
            self.login()
        else:
            LOG.debug('Already logged in')

    def test_auth(self):
        """Test the session to see if we are successfully logged in.

        :returns: ``True`` if we are already logged in
        :rtype: `bool`
        """
        r = self.s.get(gurl('profile'))
        return 'login' not in r.url

    def login(self):
        """Login with our credentials.

        There is usually no need to call this directly, as it will be
        called from init when necessary.

        :raises AuthFailure: if login is not possible
        """
        r = self.s.post(gurl('register/addDevice'),
                        data={'email': self.username,
                              'password': self.password})
        if r.status_code >= 400:
            LOG.debug('Status code from login was %s' % r.status_code)
            raise AuthFailure('Login failed')

        if 'login' in r.url:
            LOG.debug('Post login expected /, got %s' % r.url)
            raise AuthFailure('Login failed')

        LOG.info('Login successful')

    def list_objects(self, objtype, archived=True):
        """Returns a list of object descriptions.

        This is similar to the result of :func:`~get_object()`, but with object
        references instead of full objects.

        :param objtype: The type of object to be listed
        :type objtype: str
        :param archived: If ``True``, archived objects will be included
        :type archived: bool
        :returns: A list of objects
        :rtype: `list`
        """
        assert objtype in ('folder', 'track', 'waypoint', 'photo')

        r = self.s.get(gurl('api', 'objects', objtype),
                       params={
                           'count': '5000', 'page': '1',
                           'routepoints': 'false',
                           'show_archived': 'true' if archived else 'false',
                           'show_filed': 'true',
                           'sort_direction': 'desc',
                           'sort_field': 'create_date',
                       })
        return r.json()

    def lookup_object(self, objtype, name):
        """Lookup a single object by name.

        This returns an object description like what you get in
        :func:`~list_objects()`, filtering by name. If more than one object
        with the specified name is found, an error is raised.

        :param objtype: The type of object to be found (waypoint, track, etc)
        :type objtype: str
        :param name: The name of the object to be found
        :type name: str
        :returns: An object description
        :rtype: `dict`
        :raises RuntimeError: When multiple objects by the same name are found
        :raises NotFound: When no object by the given name is found
        """
        objects = self.list_objects(objtype)
        return find(objects, 'title', name)

    def get_object(self, objtype, name=None, id_=None, fmt=None):
        """Return an object data structure by name or id.

        Fetches an object and returns the raw data structure. If
        provided, ``id_`` takes precedence over ``name``.

        :param name: The name of the object
        :type name: str
        :param id_: The id of the object
        :type id_: str
        :param fmt: Optional format (``'gpx'`` or ``'kml'``)
        :type fmt: str
        :returns: The waypoint data structure, or raw content if format
                  is specified
        :rtype: `dict` or `bytes`
        :raises NotFound: if no folder by the given name is found
        :raises RuntimeError: if more than one folder exists with the name
        """

        if not any([name, id_]):
            raise RuntimeError('Object name or id must be specified')

        if id_ is None:
            id_ = self.lookup_object(objtype, name)['id']

        if fmt is not None:
            # FIXME: Add GeoJSON
            assert fmt in ('gpx', 'kml')
            resource = '%s.%s' % (id_, fmt)
        else:
            resource = id_

        result = self.s.get(gurl('api', 'objects', objtype, resource))
        if fmt is None:
            objdata = result.json()
            LOG.debug('Retrieved object %s/%s: %s' % (
                objtype, resource, objdata))
            return objdata
        else:
            return result.content

    def create_object(self, objtype, objdata):
        """Create an object.

        :param objtype: The type of object to create (waypoint, track, etc)
        :type objtype: str
        :param objdata: The exact raw object structure
        :type objdata: dict
        :returns: The resulting object, if successful, else ``None``
        :rtype: `dict`
        """
        LOG.debug('Creating %s: %s' % (objtype, pprint.pformat(objdata)))
        r = self.s.post(gurl('api', 'objects', objtype), json=objdata)
        _logresp(r)
        if r:
            obj = r.json()
            if 'id' not in obj and 'id' in obj.get('properties', {}):
                # WTF Gaia?
                obj['id'] = obj['properties']['id']
            return obj

    def put_object(self, objtype, objdata):
        """Update an object.

        :param objtype: The type of object to be updated
        :type objtype: str
        :param objdata: The exact raw object structure
        :type objdata: dict
        :returns: The resulting object, if successful, else ``None``
        :rtype: `dict`
        """
        LOG.debug('Putting %s/%s: %s' % (objtype, objdata['id'],
                                         pprint.pformat(objdata)))
        r = self.s.put(gurl('api', 'objects', objtype, objdata['id']),
                       json=objdata)
        _logresp(r)
        if r.status_code <= 201:
            return r.json()
        elif r.status_code < 299:
            return True

    def delete_object(self, objtype, id_):
        """Delete an object by id.

        :param objtype: The type of object to delete
        :type objtype: str
        :param id_: The id of the object to delete
        :type id_: str
        """
        r = self.s.delete(gurl('api', 'objects', objtype, id_))
        _logresp(r)

    def add_object_to_folder(self, folderid, objtype, objid):
        """Adds an object to a folder.

        :param folderid: The id if the folder in question
        :type folderid: str
        :param objtype: The type of the object to add
        :type objtype: str
        :param objid: The id of the object to add
        :type objid: str
        :returns: The updated folder description
        :rtype: `dict`
        """

        assert objtype in ('waypoint', 'track', 'folder', 'photo')

        folders = self.list_objects('folder')
        folder = find(folders, 'id', folderid)

        if objtype == 'folder':
            # For some reason this is different for folders
            folder_list_key = 'children'
        else:
            folder_list_key = '%ss' % objtype
        assert objid not in folder[folder_list_key]
        folder[folder_list_key].append(objid)

        LOG.debug('Updating folder %s: %s' % (folderid,
                                              pprint.pformat(folder)))

        return self.put_object('folder', folder)

    def remove_object_from_folder(self, folderid, objtype, objid):
        """Removes an object from a folder.

        :param folderid: The id of the folder in question
        :type folderid: str
        :param objtype: The type of the object to remove
        :type objtype: str
        :param objid: The id of the object to remove
        :type objid: str
        :returns: The updated folder description
        :rtype: `dict`
        """

        assert objtype in ('waypoint', 'track', 'folder', 'photo')

        folders = self.list_objects('folder')
        folder = find(folders, 'id', folderid)
        if objtype == 'folder':
            # For some reason this is different for folders
            folder_list_key = 'children'
        else:
            folder_list_key = '%ss' % objtype
        assert objid in folder[folder_list_key]
        folder[folder_list_key].remove(objid)

        LOG.debug('Updating folder %s: %s' % (folderid,
                                              pprint.pformat(folder)))

        return self.put_object('folder', folder)

    def upload_file(self, filename):
        """Upload a file by name.

        :param filename: The local filename to upload
        :type filename: str
        :returns: The resulting folder object that is created to hold the
                  contents of the file, as you would get from
                  :func:`~get_object`. None is returned if the server reports
                  that the upload was queued for processing.
        :rtype: `dict`
        """
        files = {'files': open(filename, 'rb')}
        name = os.path.basename(filename)
        r = self.s.post(gurl('upload'), files=files,
                        data={'name': name},
                        allow_redirects=True)
        _logresp(r)
        if b'File uploaded to queue' in r.content:
            # This is unfortunately very  fragile, but there is not
            # much else we can do
            LOG.debug('Upload was queued')
            return None

        folder_id = r.url.rstrip('/').split('/')[-1]
        if folder_id == 'upload':
            # Redirected back to the upload page, which means the server
            # does not like our file
            raise RuntimeError('Server rejected file (likely '
                               'unsupported type)')
        LOG.debug('Upload URL is %s, folder id is %s' % (r.url, folder_id))
        return self.get_object('folder', id_=folder_id)

    def set_objects_archive(self, objtype, ids, archive=False):
        """Control archive (sync) status on a set of objects.

        :param objtype: The type of object to change
        :type objtype: str
        :param ids: A list of object IDs
        :type ids: str
        :param archive: ``True`` if the object should be archived
        :type archive: bool
        :returns: ``True`` on success, ``False`` otherwise
        :rtype: `bool`
        :raises RuntimeError: if the server refused to provide the image
        :raises NotFound: if the server reports the image does not exist
        """
        r = self.s.put(gurl('api', 'objects', objtype),
                       json={'deleted': archive,
                             objtype: ids})
        _logresp(r)
        return r.status_code == 200

    def get_photo(self, photoid, size='fullsize'):
        """Get the image contents of a photo by id.

        :param photoid: The id of the photo
        :type photoid: str
        :param size: The size of the image (one of ``fullsize``, ``scaled``,
                     or ``thumbnail``.
        :type size: str
        :returns: A tuple of content-type and the bytes content of the photo
        :rtype: `tuple` (`str`, `bytes`)
        """
        assert size in ('fullsize', 'thumbnail', 'scaled')

        photo = self.get_object('photo', id_=photoid)
        url = photo['properties']['%s_url' % size]
        r = self.s.get(url)
        if r.status_code != 200:
            LOG.debug('Attempt to fetch %r returned %i: %s' % (url,
                                                               r.status_code,
                                                               r.reason))
            raise RuntimeError('Server did not return image')
        content_type = r.headers['Content-Type']
        LOG.debug('Photo headers: %s' % r.headers)

        return content_type, r.content

    def get_access(self, folderid):
        """Get access information for a folder.

        :param folderid: The id of the folder
        :type folderid: str
        :returns: A list of API access objects for the folder
        :rtype: list
        :raises RuntimeError: if the server refuses to list accesses
        """

        r = self.s.get(gurl('api', 'objects', 'folder', folderid, 'access'))
        if r.status_code != 200:
            LOG.debug('Server refused folder access with %i: %s' % (
                r.status_code, r.reason))
            raise RuntimeError('Server refused to list access')

        return r.json()

    def get_invites(self, folderid):
        """Get invite information for a folder.

        :param folderid: The id of the folder
        :type folderid: str
        :returns: A list of API invite objects for the folder
        :rtype: list
        :raises RuntimeError: if the server refuses to list invites
        """

        r = self.s.get(gurl('api', 'objects', 'folder', folderid, 'invite'))
        if r.status_code != 200:
            LOG.debug('Server refused folder invites with %i: %s' % (
                r.status_code, r.reason))
            raise RuntimeError('Server refused to list invites')

        return r.json()
