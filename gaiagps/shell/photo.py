import os
import pathvalidate
import time

from gaiagps.shell import command
from gaiagps.shell import options
from gaiagps import util

type_to_extension = {
    'image/jpeg': 'jpg',
    'image/png': 'png',
    'image/gif': 'gif',
}


class Photo(command.Command):
    """Manage Photos

    This command allows you to take action on photos, such as downloading
    them. Note that GaiaGPS.com treats photos mostly as waypoints, so
    you should use the waypoint command to move, rename, and delete them.
    """
    @staticmethod
    def opts(parser):
        cmds = parser.add_subparsers(dest='subcommand')

        export = cmds.add_parser('export', help='Export (download) to a file',
                                 description=('Export a photo from gaiagps '
                                              'to a local file (named as '
                                              'TITLE.EXT, based on the '
                                              'metadata about the photo when '
                                              'it is downloaded)'))
        export.add_argument('--match', action='store_true',
                            help=('Treat names as regular expressions and '
                                  'include all matches'))
        export.add_argument('--match-date', metavar='YYYY-MM-DD',
                            action=options.DateRange,
                            help=('Match items with this date. Specify an '
                                  'inclusive range with START:END.'))
        export.add_argument('--dry-run', action='store_true',
                            help=('Do not actually export anything '
                                  '(use with --verbose)'))
        export.add_argument('name', help='Name (or ID)',
                            nargs='*')

        options.list_and_dump_ops(cmds)
        options.show_ops(cmds)

    def export(self, args):
        try:
            to_export = self.find_objects(args.name, match=args.match,
                                          date_range=args.match_date)
        except command._Safety:
            to_export = []

        if not to_export:
            self.verbose('No items matched criteria')
            return 1

        for photo in to_export:
            if args.dry_run:
                self.verbose('Would download %r' % photo['title'])
            else:
                ds = util.date_parse(photo)
                ts = time.mktime(ds.timetuple())
                content_type, content = self.client.get_photo(photo['id'])
                extension = type_to_extension.get(content_type, 'dat')
                filename = '%s.%s' % (
                    pathvalidate.sanitize_filename(photo['title']), extension)
                if os.path.exists(filename):
                    print('File %r already exists; not overwriting' % filename)
                    continue
                with open(filename, 'wb') as f:
                    f.write(content)
                os.utime(filename, (ts, ts))
                self.verbose('Wrote %r' % filename)
