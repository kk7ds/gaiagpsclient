import argparse
import contextlib
import getpass
import http.cookiejar
import logging
import pprint
import prettytable
import os
import sys

from gaiagps import apiclient
from gaiagps import util


def folder_ops(parser, allownew=True):
    parser.add_argument('--existing-folder',
                        help='Add to existing folder with this name')
    if allownew:
        parser.add_argument('--new-folder',
                            help='Add to a new folder with this name')


def remove_ops(cmds, objtype):
    remove = cmds.add_parser('remove', help='Remove a %s' % objtype)
    remove.add_argument('name', help='Name (or ID)')


def move_ops(cmds):
    move = cmds.add_parser('move', help='Move to another folder')
    move.add_argument('name', help='Name (or ID)')
    move.add_argument('destination',
                      help='Destination folder (or "/" to move to root)')


def rename_ops(cmds):
    rename = cmds.add_parser('rename', help='Rename')
    rename.add_argument('name', help='Current name')
    rename.add_argument('new_name', help='New name')


def export_ops(cmds):
    export = cmds.add_parser('export', help='Export to file')
    export.add_argument('name', help='Name (or ID)')
    export.add_argument('filename', help='Export filename (or - for stdout)')
    export.add_argument('--format', default='gpx', choices=('gpx', 'kml'),
                        help='File format (default=gpx)')


def list_and_dump_ops(cmds):
    list = cmds.add_parser('list', help='List')
    list.add_argument('--by-id', action='store_true',
                      help='List items by ID only (for resolving duplicates')
    dump = cmds.add_parser('dump', help='Raw dump of the data structure')
    dump.add_argument('name', help='Name (or ID)')

    urlfor = cmds.add_parser('url', help='Show direct browser-suitable URL')
    urlfor.add_argument('name', help='Name (or ID)')


class Command(object):
    def __init__(self, client):
        self.client = client

    @property
    def objtype(self):
        return self.__class__.__name__.lower()

    @staticmethod
    def opts(parser):
        pass

    def dispatch(self, parser, args):
        if hasattr(args, 'subcommand') and args.subcommand:
            getattr(self, args.subcommand)(args)
        elif hasattr(self, 'default'):
            self.default(args)
        else:
            parser.print_usage()

    def get_object(self, name_or_id, **kwargs):
        objtype = kwargs.pop('objtype', self.objtype)
        if util.is_id(name_or_id):
            return self.client.get_object(objtype, id_=name_or_id,
                                          **kwargs)
        else:
            return self.client.get_object(objtype, name=name_or_id,
                                          **kwargs)

    def remove(self, args):
        objtype = self.objtype
        obj = self.get_object(args.name)
        self.client.delete_object(objtype, obj['id'])

    def rename(self, args):
        objtype = self.objtype
        obj = self.get_object(args.name)

        if objtype == 'waypoint':
            obj['properties']['title'] = args.new_name
        elif objtype == 'track':
            obj = {'id': obj['id'], 'title': args.new_name}
        else:
            raise RuntimeError('Internal error: unable to '
                               'rename %s objects' % objtype)
        if not self.client.put_object(objtype, obj):
            print('Failed to rename %s' % objtype)
            return 1

    def move(self, args):
        objtype = self.objtype
        if args.destination == '/':
            objs = self.client.list_objects(objtype)
            if util.is_id(args.name):
                key = 'id'
            else:
                key = 'title'
            obj = apiclient.find(objs, key, args.name)
            if obj['folder']:
                self.client.remove_object_from_folder(
                    obj['folder'], objtype, obj['id'])
            else:
                print('%s is already at root' % objtype.title())
        else:
            obj = self.get_object(args.name)
            if not obj:
                print('No such %s found' % objtype)
                return 1

            folder = self.get_object(args.destination,
                                     objtype='folder')
            if not folder:
                print('No such folder found')
                return 1

            self.client.add_object_to_folder(
                folder['id'], objtype, obj['id'])

    def export(self, args):
        data = self.get_object(args.name, fmt=args.format)
        if args.filename == '-':
            print(data)
        else:
            with open(args.filename, 'wb') as f:
                f.write(data)
            print('Wrote %s' % args.filename)

    def idlist(self, args):
        objtype = self.objtype
        items = self.client.list_objects(objtype)
        for item in items:
            print('%-36s %s' % (item['id'], item['title']))

    def list(self, args):
        if args.by_id:
            return self.idlist(args)

        objtype = self.objtype
        folders = {}

        def get_folder(ident):
            if not folders:
                folders.update({f['id']: f
                                for f in self.client.list_objects('folder')})
            return folders[ident]

        items = self.client.list_objects(objtype)
        for item in items:
            folder = (item['folder'] and
                      get_folder(item['folder'])['title'] or '')
            item['folder_name'] = folder

        table = prettytable.PrettyTable(['Name', 'Updated', 'Folder'])

        def sortkey(i):
            return i['folder_name'] + ' ' + i['title']

        for item in sorted(items, key=sortkey):
            table.add_row([item['title'],
                           util.datefmt(item),
                           item['folder_name']])
        print(table)

    def dump(self, args):
        pprint.pprint(self.get_object(args.name))

    def url(self, args):
        objtype = self.objtype
        obj = self.get_object(args.name)
        print('%s/datasummary/%s/%s' % (apiclient.BASE,
                                        objtype,
                                        obj['id']))


class Waypoint(Command):
    """Manage waypoints

    This command allows you to take action on waypoints, such as adding,
    removing, and renaming them.
    """
    @staticmethod
    def opts(parser):
        cmds = parser.add_subparsers(dest='subcommand')
        add = cmds.add_parser('add', help='Add a waypoint')
        add.add_argument('name', help='Name (or ID)')
        add.add_argument('latitude', help='Latitude (in decimal degrees)')
        add.add_argument('longitude', help='Longitude (in decimal degrees)')
        add.add_argument('altitude', help='Altitude (in meters', default=0,
                         nargs='?')
        folder_ops(add)
        remove_ops(cmds, 'waypoint')
        move_ops(cmds)
        rename_ops(cmds)
        export_ops(cmds)
        list_and_dump_ops(cmds)

        coords = cmds.add_parser('coords', help='Display coordinates')
        coords.add_argument('name', help='Name (or ID)')

    def add(self, args):
        try:
            args.latitude = util.validate_lat(args.latitude)
            args.longitude = util.validate_lon(args.longitude)
            args.altitude = util.validate_alt(args.altitude)
        except ValueError as e:
            print('Unable to add waypoint: %s' % e)
            return 1

        if args.existing_folder:
            folder = self.get_object(args.existing_folder,
                                     objtype='folder')
        else:
            folder = None

        wpt = self.client.create_object('waypoint',
                                        util.make_waypoint(args.name,
                                                           args.latitude,
                                                           args.longitude,
                                                           args.altitude))

        if not wpt:
            print('Failed to create waypoint')
            return 1

        if args.new_folder:
            folder = self.client.create_object(
                'folder',
                util.make_folder(args.new_folder))

        if folder:
            self.client.add_object_to_folder(
                folder['id'], 'waypoint', wpt['id'])

    def coords(self, args):
        wpt = self.get_object(args.name)
        gc = wpt['geometry']['coordinates']
        print('%.6f,%.6f' % (gc[1], gc[0]))


class Track(Command):
    """Manage tracks

    This command allows you to take action on tracks, such as adding,
    removing, and renaming them.
    """
    @staticmethod
    def opts(parser):
        cmds = parser.add_subparsers(dest='subcommand')
        remove_ops(cmds, 'track')
        rename_ops(cmds)
        move_ops(cmds)
        export_ops(cmds)
        list_and_dump_ops(cmds)


class Folder(Command):
    """Manage folders

    This command allows you to take action on folders, such as
    adding, removing, and moving them.
    """
    @staticmethod
    def opts(parser):
        cmds = parser.add_subparsers(dest='subcommand')
        add = cmds.add_parser('add', help='Add a folder')
        add.add_argument('name', help='Name (or ID)')
        folder_ops(add, allownew=False)
        remove_ops(cmds, 'folder')
        move_ops(cmds)
        export_ops(cmds)
        list_and_dump_ops(cmds)

    def add(self, args):
        if args.existing_folder:
            folder = self.get_object(args.existing_folder,
                                     objtype='folder')
        else:
            folder = None

        new_folder = self.client.create_object('folder',
                                               util.make_folder(args.name))
        if not new_folder:
            print('Failed to add folder')
            return 1

        if folder:
            if not self.client.add_object_to_folder(folder['id'], 'folder',
                                                    new_folder['id']):
                print('Created folder, but failed to add it to '
                      'existing folder')
                return 1


class Test(Command):
    """Test access to Gaia

    This command just attempts to use your credentials to log into
    the gaia API. If it is successful, it will say so.
    """
    def default(self, args):
        if self.client.test_auth():
            print('Success!')
        else:
            print('Unable to access gaia')


class Tree(Command):
    """Display all data in tree format

    This command will print all waypoints, tracks, and folders in a
    hierarchical layout, purely for visualization purposes.
    """
    def default(self, args):
        folders = self.client.list_objects('folder')
        root = util.make_tree(folders)
        tree = util.resolve_tree(self.client, root)
        util.pprint_folder(tree)


class Upload(Command):
    """Upload an entire file of tracks and/or waypoints

    This command takes a file (in a format supported by Gaia) and
    uploads the data within to gaiagps.com. By default gaiagps.com
    places this in a new folder of its own, according to the filename.
    If the --existing-folder or --new-folder options are provided, the
    uploaded data will be moved out of the temporary upload folder
    and the latter will be deleted afterwards.
    """
    @staticmethod
    def opts(parser):
        parser.add_argument('filename', help='File to upload')
        folder_ops(parser)

    def default(self, args):
        log = logging.getLogger('upload')

        if args.existing_folder:
            dst_folder = self.get_object(args.existing_folder,
                                         objtype='folder')
        else:
            dst_folder = None
        new_folder = self.client.upload_file(args.filename)

        log.debug(new_folder)
        log.info('Uploaded file to new folder %s/%s' % (
            new_folder['properties']['name'],
            new_folder['id']))

        if args.new_folder:
            dst_folder = self.client.create_object('folder',
                                                   util.make_folder(
                                                       args.new_folder))
            if not dst_folder:
                print('Uploaded file, but failed to create folder %s' % (
                    args.new_folder))
                return 1

        if dst_folder:
            # I want that...other version of a folder
            folders = self.client.list_objects('folder')
            new_folder_desc = apiclient.find(folders, 'id', new_folder['id'])
            dst_folder_desc = apiclient.find(folders, 'id', dst_folder['id'])

            log.info('Moving contents of %s to %s' % (
                new_folder['properties']['name'],
                dst_folder['properties']['name']))

            for waypoint in new_folder_desc['waypoints']:
                log.info('Moving waypoint %s' % waypoint)
                dst_folder_desc['waypoints'].append(waypoint)
            for track in new_folder_desc['tracks']:
                log.info('Moving track %s' % track)
                dst_folder_desc['tracks'].append(track)
            updated_dst = self.client.put_object('folder', dst_folder_desc)
            log.info('Updated destination folder %s' % (
                dst_folder['properties']['name']))
            if not updated_dst:
                print('Failed to move tracks and waypoints from '
                      'upload folder %s to requested folder %s' % (
                          new_folder['properties']['name'],
                          dst_folder['properties']['name']))
            log.info('Deleting temporary folder %s' % (
                new_folder['properties']['name']))
            self.client.delete_object('folder', new_folder['id'])


@contextlib.contextmanager
def cookiejar():
    if sys.platform == 'win32':
        cookiepath = 'gaiagpsclient-cookies.txt'
    else:
        cookiepath = os.path.expanduser('~/.gaiagpsclient')

    jar = http.cookiejar.LWPCookieJar(cookiepath)
    if os.path.exists(cookiepath):
        jar.load()

    try:
        yield jar
    finally:
        jar.save()


def main():
    parser = argparse.ArgumentParser(
        description='Command line client for gaiagps.com')
    parser.add_argument('--user', help='Gaia username')
    parser.add_argument('--pass', metavar='PASS', dest='pass_',
                        help='Gaia password (prompt if unspecified)', )
    parser.add_argument('--debug', help='Enable debug output',
                        action='store_true')
    parser.add_argument('--verbose', help='Enable verbose output',
                        action='store_true')

    cmds = parser.add_subparsers(dest='cmd')

    command_classes = [Waypoint, Folder, Test, Tree, Track, Upload]
    commands = {}

    for ccls in command_classes:
        command_name = ccls.__name__.lower()
        commands[command_name] = ccls
        try:
            helptxt, desctxt = ccls.__doc__.split('\n', 1)
        except ValueError:
            helptxt = ccls.__doc__
            desctxt = ''
        ccls.opts(cmds.add_parser(command_name,
                                  description=desctxt.strip(),
                                  help=helptxt.strip()))

    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)
    root_logger = logging.getLogger()
    if args.debug:
        root_logger.setLevel(logging.DEBUG)
        import http.client
        http.client.HTTPConnection.debuglevel = 1
    elif args.verbose:
        root_logger.setLevel(logging.INFO)

    if not args.cmd:
        parser.print_help()
        return 1
    else:
        is_terminal = os.isatty(sys.stdin.fileno())
        if args.user and not args.pass_ and is_terminal:
            args.pass_ = getpass.getpass()

        with cookiejar() as cookies:
            try:
                client = apiclient.GaiaClient(args.user, args.pass_,
                                              cookies=cookies)
            except Exception as e:
                print('Unable to access Gaia: %s' % e)
                return 1

        command = commands[args.cmd](client)
        try:
            return command.dispatch(parser, args)
        except (apiclient.NotFound, RuntimeError) as e:
            print(e)
            return 1

if __name__ == '__main__':
    sys.exit(main())
