import argparse
import contextlib
import getpass
import http.cookiejar
import logging
import os
import sys
import traceback

from gaiagps import apiclient
from gaiagps.shell import command
from gaiagps.shell import photo
from gaiagps.shell import upload
from gaiagps.shell import track
from gaiagps.shell import folder
from gaiagps.shell import waypoint


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


def main(args=None):
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

    command_classes = [waypoint.Waypoint, folder.Folder, command.Test,
                       command.Tree, track.Track, upload.Upload,
                       photo.Photo]
    commands = {}

    if 'GAIAGPSCLIENTDEV' in os.environ:
        command_classes.append(command.Query)

    for ccls in sorted(command_classes, key=lambda c: c.__name__):
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

    try:
        args = parser.parse_args(args)
    except SystemExit as e:
        return int(str(e))

    logging.basicConfig(level=logging.WARNING)
    root_logger = logging.getLogger()
    if args.debug:
        root_logger.setLevel(logging.DEBUG)
        import http.client
        http.client.HTTPConnection.debuglevel = 1
        logging.getLogger('parser').debug('Arguments: %s' % args)
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

        cmd = commands[args.cmd](client, verbose=args.verbose)
        try:
            return int(cmd.dispatch(parser, args) or 0)
        except (apiclient.NotFound, RuntimeError) as e:
            root_logger.debug(traceback.format_exc())
            print(e)
            return 1
