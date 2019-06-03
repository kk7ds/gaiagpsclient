import prettytable

from gaiagps.shell import command
from gaiagps.shell import options
from gaiagps import util


class Folder(command.Command):
    """Manage folders

    This command allows you to take action on folders, such as
    adding, removing, and moving them.
    """
    @staticmethod
    def opts(parser):
        cmds = parser.add_subparsers(dest='subcommand')
        add = cmds.add_parser('add', help='Add a folder')
        add.add_argument('name', help='Name (or ID)')
        add.add_argument('--dry-run', action='store_true',
                         help=('Do not actually add anything '
                               '(use with --verbose)'))
        options.folder_ops(add, allownew=False)
        remove = options.remove_ops(cmds, 'folder')
        remove.add_argument('--force', action='store_true',
                            help='Remove even if not empty')
        access = cmds.add_parser('access', help='Manage access (sharing)')
        access.add_argument('--list', action='store_true',
                            help='List information about users with access')
        access.add_argument('name', help='Name (or ID)')

        options.move_ops(cmds)
        options.export_ops(cmds)
        options.list_and_dump_ops(cmds)
        options.archive_ops(cmds)
        options.show_ops(cmds)
        options.rename_ops(cmds)

    def add(self, args):
        if args.existing_folder:
            folder = self.get_object(args.existing_folder,
                                     objtype='folder')
        else:
            folder = None

        self.verbose('Creating folder %r' % args.name)
        if not args.dry_run:
            new_folder = self.client.create_object('folder',
                                                   util.make_folder(args.name))
        else:
            new_folder = {'id': 'dry-run'}
        if not new_folder:
            print('Failed to add folder')
            return 1

        if folder:
            self.verbose('Adding folder %r to folder %r' % (
                args.name, args.existing_folder))
            if not args.dry_run:
                updated = self.client.add_object_to_folder(folder['id'],
                                                           'folder',
                                                           new_folder['id'])
                if not updated:
                    print('Created folder, but failed to add it to '
                          'existing folder')
                    return 1

        if args.dry_run:
            print('Dry run; no action taken')

    def access(self, args):
        folder = self.get_object(args.name)

        def perm(readwrite, admin):
            if admin:
                return 'admin'
            elif readwrite:
                return 'read/write'
            else:
                return 'readonly'

        if args.list:
            access = self.client.get_access(folder['id'])
            invites = self.client.get_invites(folder['id'])
            table = prettytable.PrettyTable(['User', 'Access'])
            for grant in access:
                table.add_row(['%s (%s)' % (grant['user_displayname'],
                                            grant['user_username']),
                               perm(grant['write'], grant['admin'])])
            for invite in invites:
                table.add_row(['Pending (%s)' % invite['to_email'],
                               perm(invite['write_access'],
                                    invite['admin_access'])])
            print(table)
        else:
            print('Specify an access operation')
            return 1
