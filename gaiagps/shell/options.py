import argparse
import datetime

from gaiagps import util


def folder_ops(parser, allownew=True):
    parser.add_argument('--existing-folder',
                        help='Add to existing folder with this name')
    if allownew:
        parser.add_argument('--new-folder',
                            help='Add to a new folder with this name')


class DateRange(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        try:
            fmt = '%Y-%m-%d'
            dates = values.split(':', 1)

            if len(dates) == 1:
                # Just one date given, assume the whole day
                start_date = end_date = dates[0]
            else:
                start_date = dates[0]
                end_date = dates[1]

            if not start_date:
                # Assume the epoch is early enough as a lower-bound
                start_date = '1970-01-01'
            if not end_date:
                # Assume a year in the future is late enough as an upper-bound
                end_date = (datetime.datetime.now() +
                            datetime.timedelta(days=365)).strftime(fmt)

            start = datetime.datetime.strptime(start_date, fmt)
            end = datetime.datetime.strptime(end_date, fmt)

            # End date is inclusive, so make it 23:59:59
            end = (end +
                   datetime.timedelta(hours=24) -
                   datetime.timedelta(seconds=1))

            setattr(namespace, self.dest, (start, end))
        except ValueError as e:
            raise argparse.ArgumentError(self, 'Invalid date: %s' % e)


class FuzzyBoolean(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        if values and values.lower() in ['y', 'yes', 't', 'true']:
            setattr(namespace, self.dest, True)
        elif values and values.lower() in ['n', 'no', 'f', 'false']:
            setattr(namespace, self.dest, False)
        else:
            raise argparse.ArgumentError(
                self, 'Invalid value for %s: must be "yes" or "no"' % values)


def remove_ops(cmds, objtype):
    remove = cmds.add_parser(
        'remove', help='Remove a %s' % objtype,
        description='Delete %s objects from the server forever' % objtype)
    remove.add_argument('--match', action='store_true',
                        help=('Treat names as regular expressions and include '
                              'all matches'))
    remove.add_argument('--dry-run', action='store_true',
                        help=('Do not actually remove anything '
                              '(use with --verbose)'))
    remove.add_argument('--in-folder',
                        help='Limit to items in this folder')
    remove.add_argument('name', help='Name (or ID)', nargs='*')
    return remove


def move_ops(cmds):
    move = cmds.add_parser('move', help='Move to another folder',
                           description='Move objects into a folder')
    move.add_argument('--match', action='store_true',
                      help=('Treat names as regular expressions and include '
                            'all matches'))
    move.add_argument('--match-date', metavar='YYYY-MM-DD',
                      action=DateRange,
                      help=('Match items with this date. Specify an '
                            'inclusive range with START:END.'))
    move.add_argument('--dry-run', action='store_true',
                      help=('Do not actually move anything '
                            '(use with --verbose)'))
    move.add_argument('--in-folder',
                      help='Limit to items in this folder')
    move.add_argument('name', help='Name (or ID)', nargs='*')
    move.add_argument('destination',
                      help='Destination folder (or "/" to move to root)')


def rename_ops(cmds):
    rename = cmds.add_parser('rename', help='Rename',
                             description='Rename objects on the server')
    rename.add_argument('--dry-run', action='store_true',
                        help=('Do not actually rename anything '
                              '(use with --verbose)'))
    rename.add_argument('name', help='Current name')
    rename.add_argument('new_name', help='New name')


def export_ops(cmds):
    export = cmds.add_parser(
        'export', help='Export to file',
        description='Export objects into a local GPX or KML file')
    export.add_argument('name', help='Name (or ID)')
    export.add_argument('filename', help='Export filename (or - for stdout)')
    export.add_argument('--format', default='gpx', choices=('gpx', 'kml'),
                        help='File format (default=gpx)')


def list_and_dump_ops(cmds):
    list = cmds.add_parser('list', help='List',
                           description='List objects on the server')
    list.add_argument('--by-id', action='store_true',
                      help='List items by ID only (for resolving duplicates')
    list.add_argument('--match', metavar='NAME',
                      help='List only items matching this regular expression')
    list.add_argument('--match-date', metavar='YYYY-MM-DD',
                      action=DateRange,
                      help=('Match items with this date. Specify an '
                            'inclusive range with START:END.'))
    list.add_argument('--archived', action=FuzzyBoolean,
                      help='Match items with archived state ("yes" or "no")')
    list.add_argument('--format',
                      help=('Set explicit output format instead of default '
                            'table layout. Use --format=help for '
                            'instructions'))
    list.add_argument('--in-folder',
                      help='Limit to items in this folder')
    dump = cmds.add_parser('dump', help='Raw dump of the data structure',
                           description=('Dump the low-level representation of '
                                        'an object on the server '
                                        '(for debugging)'))
    dump.add_argument('name', help='Name (or ID)')

    urlfor = cmds.add_parser('url', help='Show direct browser-suitable URL')
    urlfor.add_argument('name', help='Name (or ID)')


def archive_ops(cmds):
    archive = cmds.add_parser(
        'archive',
        help='Archive (set sync=off)',
        description=('Archive an object on the server '
                     '(so that it does not sync to devices'))
    unarchive = cmds.add_parser(
        'unarchive',
        help='Unarchive (set sync=on)',
        description=('Unarchive an object on the server '
                     '(so that it does sync to devices)'))
    for i in (archive, unarchive):
        i.add_argument('name', nargs='*',
                       help='Name (or ID)')
        i.add_argument('--match', action='store_true',
                       help=('Treat names as regular expressions and include '
                             'all matches'))
        i.add_argument('--match-date', metavar='YYYY-MM-DD',
                       action=DateRange,
                       help=('Match items with this date. Specify an '
                             'inclusive range with START:END.'))
        i.add_argument('--dry-run', action='store_true',
                       help=('Do not actually change anything '
                             '(use with --verbose)'))
        i.add_argument('--in-folder',
                       help='Limit to items in this folder')


def edit_ops(cmds):
    edit = cmds.add_parser(
        'edit',
        help='Edit all attributes of one or more items',
        description=("""
        This command will download one or more items into
        an editable text file, and allow you to upload those
        changes back to the server in bulk. Interactive mode
        will automate that into a single process, spawning an
        editor between download and upload. Care must be taken
        when doing this that the format of the file is
        maintained and that nothing else is modifying the
        server side during the edit.

        Example of editing two waypoints:

        `gaiagps waypoint edit -i Camp1 Camp2`
        """))

    edit.add_argument('name', help='Name (or ID)', nargs='*')
    if util.get_editor():
        edit.add_argument('-i', '--interactive', action='store_true',
                          help='Interactively edit properties')
    edit.add_argument('-f', '--file',
                      help='Apply edits from a file')
    edit.add_argument('--match', action='store_true',
                      help=('Treat names as regular expressions and include '
                            'all matches'))
    edit.add_argument('--in-folder',
                      help='Only edit items in this folder')


def show_ops(cmds):
    show = cmds.add_parser(
        'show',
        help='Show all available details for a single item',
        description='Show all available details about an item')
    show.add_argument('name',
                      help='Name (or ID)')
    show.add_argument('--field-separator', '-f',
                      help=('Specify a string to separate the key=value '
                            'fields for easier parsing'))
    show.add_argument('--only-key', '-K', default=[], action='append',
                      help=('Only display these keys (specify multiple '
                            'times for multiple keys)'))
    show.add_argument('--expand-key', '-k', default=[], action='append',
                      help=('Expand these keys (specify multiple times '
                            'for multiple keys) to their full values '
                            '(or \'all\')'))
    show.add_argument('--only-vals', '-V', action='store_true',
                      help=('Only show values'))
