import logging
import textwrap

from gaiagps.shell import command
from gaiagps.shell import options
from gaiagps import util


class Waypoint(command.Command):
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
        add.add_argument('--notes', help='Set the notes field', default='')
        add.add_argument('--icon', help='Set the icon field', default='')
        add.add_argument('--dry-run', action='store_true',
                         help=('Do not actually add anything '
                               '(use with --verbose)'))
        options.edit_ops(cmds)
        options.folder_ops(add)
        options.remove_ops(cmds, 'waypoint')
        options.move_ops(cmds)
        options.rename_ops(cmds)
        options.export_ops(cmds)
        options.list_and_dump_ops(cmds)
        options.archive_ops(cmds)
        options.show_ops(cmds)

        cmds.add_parser('list-icons',
                        help='List available icons')

        coords = cmds.add_parser('coords', help='Display coordinates')
        coords.add_argument('name', help='Name (or ID)', nargs='*')
        coords.add_argument('--match', action='store_true',
                            help=('Treat names as regular expressions and '
                                  'include all matches'))
        coords.add_argument('--in-folder',
                            help='Limit to items in this folder')
        coords.add_argument('--just-one', action='store_true',
                            help=('Fail if more than one match is found '
                                  '(useful in a script when the output needs '
                                  'to be asserted as a single lat,lon)'))
        coords.add_argument('--show-name', action='store_true',
                            help=('Show the waypoint name after the '
                                  'coordinates, separated by a single space'))

    def list_icons(self, args):
        for alias, filename in util.ICON_ALIASES.items():
            print('%s (%s)' % (alias, filename))

    def add(self, args):
        try:
            args.latitude = util.validate_lat(args.latitude)
            args.longitude = util.validate_lon(args.longitude)
            args.altitude = util.validate_alt(args.altitude)
        except ValueError as e:
            print('Unable to add waypoint: %r' % e)
            return 1

        if args.existing_folder:
            folder = self.get_object(args.existing_folder,
                                     objtype='folder')
        else:
            folder = None

        if args.icon and args.icon in util.ICON_ALIASES:
            args.icon = util.ICON_ALIASES[args.icon]

        self.verbose('Creating waypoint %r' % args.name)
        if not args.dry_run:
            wpt = self.client.create_object(
                'waypoint',
                util.make_waypoint(args.name,
                                   args.latitude,
                                   args.longitude,
                                   alt=args.altitude,
                                   notes=args.notes,
                                   icon=args.icon))
        else:
            wpt = {'id': 'dry-run'}

        if not wpt:
            print('Failed to create waypoint')
            return 1

        if args.new_folder:
            self.verbose('Creating new folder %r' % args.new_folder)
            if not args.dry_run:
                folder = self.client.create_object(
                    'folder',
                    util.make_folder(args.new_folder))
            else:
                folder = {'properties': {'name': args.new_folder}}
        if folder:
            self.verbose('Adding waypoint %r to folder %r' % (
                args.name, folder['properties']['name']))
            if not args.dry_run:
                self.client.add_object_to_folder(
                    folder['id'], 'waypoint', wpt['id'])

        if args.dry_run:
            print('Dry run; no action taken')

    def coords(self, args):
        try:
            wpts = self.find_objects(args.name, match=args.match)
        except command._Safety:
            wpts = []

        folder_filter = self.folder_filter(args.in_folder)
        wpts = list(folder_filter(wpts))

        if not wpts:
            raise RuntimeError('No waypoints matched')
        elif args.just_one and len(wpts) != 1:
            raise RuntimeError('More than one waypoints matched')

        for wpt in wpts:
            wpt = self.get_object(wpt['id'])
            gc = wpt['geometry']['coordinates']
            output = '%.6f,%.6f' % (gc[1], gc[0])
            if args.show_name:
                output += ' %s' % wpt['properties']['title']
            print(output)

    def _rev_match(self, server, local):
        if (server['properties']['revision'] !=
                local.get('properties', {}).get(('revision'))):
            logging.getLogger('waypoint').debug(
                'Server revision is %r, local is %r' % (
                    server['properties']['revision'],
                    local.get('properties', {}).get('revision')))
            raise Exception(
                ('%s has changed on the server or '
                 'lists are out of sync; unable to apply changes') % (
                     server['properties']['title']))

    def _edit_preamble(self):
        return (super(Waypoint, self)._edit_preamble() +
                textwrap.wrap('Available icons are: ' +
                              ' '.join(util.ICON_ALIASES.keys())))

    def _edit_preprocess(self, obj):
        icon_rev = {v: k for k, v in util.ICON_ALIASES.items()}
        obj['properties']['icon'] = icon_rev.get(obj['properties']['icon'],
                                                 obj['properties']['icon'])
        return obj

    def _edit_postprocess(self, obj):
        icon_fwd = util.ICON_ALIASES
        obj['properties']['icon'] = icon_fwd.get(obj['properties']['icon'],
                                                 obj['properties']['icon'])
        return obj

    def edit(self, args):
        editable = ['id'] + \
            ['properties/%s' % p for p in ('icon', 'notes', 'public', 'title',
                                           'revision')]
        return self._edit(args, editable)
