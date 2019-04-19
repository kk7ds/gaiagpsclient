import logging
import os
import requests
import sys
import pprint


logging.getLogger('requests').setLevel(logging.ERROR)

BASE = 'https://www.gaiagps.com'
LOG = logging.getLogger(__name__)


class AuthFailure(Exception):
    pass


class NotFound(Exception):
    pass


def gurl(*sub):
    """Build a gaiagps.com url from components."""
    return '/'.join([BASE] + list(sub))


def find(iterable, key, value):
    """Find a key=value item in iterable.

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
except:
    pass
USER_AGENT = 'https://github.com/kk7ds/gaiagpsclient (%s)' % (
    '; '.join(USER_AGENT_ELEMENTS))


class GaiaClient(object):
    """A low-level client for gaiagps.com."""

    def __init__(self, username, password, cookies=None):
        """
        Initialize and login (if necessary) to gaiagps.com. If
        a cookiejar is provided and the session stored within is
        still active, login credentials are not used.

        :param username: Username for gaiagps.com
        :param password: Password for gaiagps.com
        :param cookies: A http.cookiejar.CookieJar or None
        :raises: AuthFailure if login fails
        :raises: RuntimeError if session is stale and credentials are
                 not provided
        """
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
            LOG.info('Not authenticated, logging in...')
            self.login()
        else:
            LOG.info('Already logged in')

    def test_auth(self):
        """Test the session to see if we are successfully logged in.

        :returns: True if we are already logged in
        """
        r = self.s.get(gurl('login'))
        return 'login' not in r.url

    def login(self):
        """Login with our credentials.

        There is usually no need to call this directly, as it will be
        called from init when necessary.

        :raises: AuthFailure if login is not possible
        """
        r = self.s.post(gurl('login/'),
                        data={'username': self.username,
                              'password': self.password,
                              'next': '/'})
        if r.status_code >= 400:
            LOG.debug('Status code from login was %s' % r.status_code)
            raise AuthFailure('Login failed')

        if 'login' in r.url:
            LOG.debug('Post login expected /, got %s' % r.url)
            raise AuthFailure('Login failed')

        LOG.info('Login successful')

    def list_objects(self, objtype):
        """Returns a list of object descriptions.

        This is similar to the result of get_object(), but with object
        references instead of full objects.
        """
        assert objtype in ('folder', 'track', 'waypoint')

        r = self.s.get(gurl('api', 'objects', objtype),
                       params={
                           'count': '5000', 'page': '1',
                           'routepoints': 'false',
                           'show_archived': 'false',
                           'show_filed': 'true',
                           'sort_direction': 'desc',
                           'sort_field': 'create_date',
                       })
        return r.json()

    def lookup_object(self, objtype, name):
        """Lookup a single object by name.

        This returns an object description like what you get in
        list_objects(), filtering by name. If more than one object
        with the specified name is found, an error is raised.

        :param objtype: The type of object to be found (waypoint, track, etc)
        :param name: The name of the object to be found
        :returns: An object description
        :raises RuntimeError: When multiple objects by the same name are found
        :raises NotFound: When no object by the given name is found
        """
        objects = self.list_objects(objtype)
        return find(objects, 'title', name)

    def get_object(self, objtype, name=None, id_=None, fmt=None):
        """Return an object data structure by name or id.

        Fetches an object and returns the raw data structure. If
        provided, an id takes precedence over a name.

        :param name: The name of the object
        :param id_: The id of the object
        :param fmt: Optional format ('gpx' or 'kml')
        :returns: The waypoint data structure
        :raises: NotFound if no folder by the given name is found
        :raises: RuntimeError if more than one folder exists with the name
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
        :oaram objdata: The exact raw object structure
        :returns: The resulting object, if successful, else None
        """
        LOG.debug('Creating %s: %s' % (objtype, pprint.pformat(objdata)))
        r = self.s.post(gurl('api', 'objects', objtype + '/'), json=objdata)
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
        :param objdata: The exact raw object structure
        :returns: The resulting object, if successful, else None
        """
        LOG.debug('Putting %s/%s: %s' % (objtype, objdata['id'],
                                         pprint.pformat(objdata)))
        r = self.s.put(gurl('api', 'objects', objtype, objdata['id'] + '/'),
                       json=objdata)
        _logresp(r)
        if r.status_code <= 201:
            return r.json()
        elif r.status_code < 299:
            return True

    def delete_object(self, objtype, id_):
        """Delete an object by id.

        :param objtype: The type of object to delete
        :param id_: The id of the object to delete
        """
        r = self.s.delete(gurl('api', 'objects', objtype, id_))
        _logresp(r)

    def add_object_to_folder(self, folderid, objtype, objid):
        """Adds an object to a folder.

        :param folderid: The id if the folder in question
        :param objtype: The type of the object to add
        :param objid: The id of the object to add
        :returns: The updated folder description
        """

        assert objtype in ('waypoint', 'track', 'folder')

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
        :param objtype: The type of the object to add
        :param objid: The id of the object to add
        :returns: The updated folder description
        """

        assert objtype in ('waypoint', 'track', 'folder')

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
        :returns: The resulting folder object that is created to hold the
                  contents of the file
        """
        files = {'files': open(filename, 'rb')}
        r = self.s.post(gurl('upload/'), files=files,
                        data={'name': os.path.basename(filename)},
                        allow_redirects=True)
        _logresp(r)
        folder_id = r.url.rstrip('/').split('/')[-1]
        LOG.debug('Upload URL is %s, folder id is %s' % (r.url, folder_id))
        return self.get_object('folder', id_=folder_id)
