import argparse
import contextlib
import datetime
import getpass
import http.cookiejar
import logging
import pprint
import prettytable
import random
import re
import os
import subprocess
import sys
import textwrap
import time
import traceback
import yaml

from gaiagps import apiclient
from gaiagps import util


class _Safety(Exception):
    pass


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
            start = datetime.datetime.strptime(dates[0], fmt)
            if len(dates) > 1:
                # End was specified
                end = datetime.datetime.strptime(dates[1], fmt)
            else:
                # No end, so re-parse start so we get another object
                # we can mutate below
                end = datetime.datetime.strptime(dates[0], fmt)

            # End date is inclusive, so make it 23:59:59
            end = (end +
                   datetime.timedelta(hours=24) -
                   datetime.timedelta(seconds=1))

            setattr(namespace, self.dest, (start, end))
        except ValueError:
            raise argparse.ArgumentError(self, 'Invalid date format')


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
    remove.add_argument('name', help='Name (or ID)', nargs='+')
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


class Command(object):
    def __init__(self, client, verbose=False):
        self.client = client
        if verbose:
            self.verbose = lambda x, e=None: print(x, end=e)
        else:
            self.verbose = lambda x: None

    @property
    def objtype(self):
        return self.__class__.__name__.lower()

    @staticmethod
    def opts(parser):
        pass

    def dispatch(self, parser, args):
        if hasattr(args, 'subcommand') and args.subcommand:
            fn_name = args.subcommand.replace('-', '_')
            return getattr(self, fn_name)(args)
        elif hasattr(self, 'default'):
            return self.default(args)
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

    def find_objects(self, names_or_ids, objtype=None, match=False,
                     date_range=None, allow_missing=False):
        matched_objs = []
        objs = self.client.list_objects(objtype or self.objtype)
        if names_or_ids:
            for name_or_id in names_or_ids:
                if util.is_id(name_or_id):
                    matched_objs.append(apiclient.find(objs, 'id', name_or_id))
                elif match:
                    matched_objs.extend(apiclient.match(objs, 'title',
                                                        name_or_id))
                else:
                    try:
                        matched_objs.append(apiclient.find(objs, 'title',
                                                           name_or_id))
                    except apiclient.NotFound:
                        if not allow_missing:
                            raise
        else:
            matched_objs = objs

        if date_range:
            matched_objs = [x for x in matched_objs
                            if self._match_date(x, date_range)]

        if not names_or_ids and len(matched_objs) == len(objs):
            # Refuse to find all objects because no criteria was specified
            raise _Safety()

        return matched_objs

    def _confirm_recursive(self, args, obj):
        sub_objs = ('tracks', 'waypoints', 'children', 'maps')
        if any(obj[o] for o in sub_objs):
            if hasattr(args, 'force') and args.force:
                self.verbose('Warning: folder %r is not empty' % (
                    obj['title']))
                return True
            elif os.isatty(sys.stdin.fileno()):
                answer = input(
                    'Folder %s is not empty. Remove anyway? [y/n] ' % (
                        obj['title']))
                return answer.strip().lower() in ('y', 'yes')
            else:
                print('Folder %r is not empty; skipping.' % obj['title'])
                return False

        return True

    def remove(self, args):
        objtype = self.objtype
        to_remove = self.find_objects(args.name, match=args.match)
        for obj in to_remove:
            if objtype == 'folder' and not self._confirm_recursive(args, obj):
                continue
            self.verbose('Removing %s %r (%s)' % (
                objtype, obj['title'], obj['id']))
            if not args.dry_run:
                self.client.delete_object(objtype, obj['id'])
        if args.dry_run:
            print('Dry run; no action taken')

    def rename(self, args):
        objtype = self.objtype
        obj = self.get_object(args.name)

        if objtype == 'waypoint':
            obj['properties']['title'] = args.new_name
        elif objtype in ('track', 'folder'):
            obj = {'id': obj['id'], 'title': args.new_name}
        else:
            raise RuntimeError('Internal error: unable to '
                               'rename %s objects' % objtype)
        self.verbose('Renaming %r to %r' % (args.name, args.new_name))
        if args.dry_run:
            print('Dry run; no action taken')
        elif not self.client.put_object(objtype, obj):
            print('Failed to rename %r' % objtype)
            return 1

    def move(self, args):
        objtype = self.objtype
        try:
            to_move = self.find_objects(args.name, match=args.match,
                                        date_range=args.match_date)
        except _Safety:
            print('Specify name(s) of objects to move or filter criteria')
            return 1

        if not to_move:
            self.verbose('No items matched criteria')
            return

        if args.destination == '/':
            for obj in to_move:
                if obj['folder']:
                    self.verbose('Moving %s %r (%s) to /' % (
                        objtype, obj['title'], obj['id']))
                    if not args.dry_run:
                        self.client.remove_object_from_folder(
                            obj['folder'], objtype, obj['id'])
                else:
                    print('%s %r is already at root' % (
                        objtype.title(), obj['title']))
        else:
            folder = self.get_object(args.destination,
                                     objtype='folder')
            for obj in to_move:
                self.verbose('Moving %s %r (%s) to %s' % (
                    objtype, obj['title'], obj['id'],
                    folder['properties']['name']))
                if not args.dry_run:
                    self.client.add_object_to_folder(
                        folder['id'], objtype, obj['id'])
        if args.dry_run:
            print('Dry run; no action taken')

    def export(self, args):
        data = self.get_object(args.name, fmt=args.format)
        if args.filename == '-':
            print(data)
        else:
            with open(args.filename, 'wb') as f:
                f.write(data)
            print('Wrote %r' % args.filename)

    def idlist(self, args):
        objtype = self.objtype
        items = self.client.list_objects(objtype)
        for item in items:
            print('%-36s %20s %r' % (item['id'],
                                     util.datefmt(item),
                                     item['title']))

    def _match_date(self, item, date_range):
        start, end = date_range
        item_dt = util.date_parse(item)
        if item_dt:
            item_dt = item_dt.replace(tzinfo=None)
            return item_dt >= start and item_dt <= end
        else:
            return False

    def list(self, args):
        if args.format and args.format.lower() == 'help':
            msg = ['--format takes a python-like format string, such as: ',
                   '',
                   '    %(title)s: %(latitude).4f,%(longitude).5f',
                   '',
                   'which might display something like this:',
                   '',
                   '    My Campsite: 45.1234,-122.98765',
                   '',
                   'Where the field name can be anything in "properties" ',
                   'for an object (as displayed by the "show" command). ',
                   'Also, the following special format keys are available: ',
                   '']
            fmt = util.ThingFormatter({})
            for key in fmt.keys:
                doc = getattr(fmt, 'format_%s' % key).__doc__
                msg.append(' - %s: %s' % (key, doc))

            msg.extend(
                ['',
                 'Note that using --format causes an API call for each item ',
                 'in a list in order to fetch the full set of properties. ',
                 'Please limit the list in some way to avoid undue stress ',
                 'on gaiagps.com.'])

            print(os.linesep.join(msg))
            return 0

        if args.by_id:
            return self.idlist(args)

        objtype = self.objtype
        folders = {}

        def get_folder(ident):
            if not folders:
                folders.update({f['id']: f
                                for f in self.client.list_objects('folder')})
            return folders[ident]

        if args.archived is not None:
            show_archived = args.archived
            only_archived = show_archived
        else:
            show_archived = True
            only_archived = False

        items = self.client.list_objects(objtype, archived=show_archived)
        for item in items:
            folder = (item['folder'] and
                      get_folder(item['folder'])['title'] or '')
            item['folder_name'] = folder

        table = prettytable.PrettyTable(['Name', 'Updated', 'Folder'])

        def sortkey(i):
            return i['folder_name'] + ' ' + i['title']

        for item in sorted(items, key=sortkey):
            if args.match and not re.search(args.match, item['title']):
                continue
            if args.match_date and not self._match_date(item, args.match_date):
                continue
            if only_archived and not item['deleted']:
                continue
            if args.format:
                # This is unfortunately very heavy, but since we do not seem to
                # be able to get whole objects in list format, this is really
                # the only option at the moment.
                item = self.get_object(item['id'])
                print(args.format % util.ThingFormatter(item))
            else:
                table.add_row([item['title'],
                               util.datefmt(item),
                               item['folder_name']])
        if not args.format:
            print(table)

    def dump(self, args):
        pprint.pprint(self.get_object(args.name))

    def url(self, args):
        objtype = self.objtype
        obj = self.get_object(args.name)
        print('%s/datasummary/%s/%s' % (apiclient.BASE,
                                        objtype,
                                        obj['id']))

    def _archive(self, args, archive):
        objtype = self.objtype
        try:
            to_hit = self.find_objects(args.name, match=args.match,
                                       date_range=args.match_date)
        except _Safety:
            print('Specify name(s) of objects to archive or filter criteria')
            return 1

        if not to_hit:
            self.verbose('No items matched criteria')
            return

        for item in to_hit:
            op = archive and 'Archiving' or 'Unarchiving'
            self.verbose('%s %r' % (op, item['title']))
        if not args.dry_run:
            self.client.set_objects_archive(objtype,
                                            [i['id'] for i in to_hit],
                                            archive)
        else:
            print('Dry run; no action taken')

    def archive(self, args):
        return self._archive(args, True)

    def unarchive(self, args):
        return self._archive(args, False)

    def show(self, args):
        obj = self.get_object(args.name)

        try:
            props = obj['properties']
        except KeyError:
            try:
                props = obj['features'][0]['properties']
            except KeyError:
                props = None

        if props is None:
            raise RuntimeError(
                ('Internal error: unable to '
                 'find properties for object of type "%s"') % self.objtype)

        for k in args.only_key:
            if k not in props:
                print('%s %r does not have key %r' % (
                    self.objtype.title(), args.name, k))
                return 1

        if args.field_separator and args.only_vals:
            print('Options --only-vals and --field-separator are '
                  'mutally exclusive')
            return 1

        if args.expand_key == ['all']:
            args.expand_key = list(props.keys())

        props = [(k, props[k])
                 for k in sorted(props.keys())
                 if not args.only_key or k in args.only_key]
        if args.only_vals:
            for k, v in props:
                if v:
                    print(v)
        elif args.field_separator:
            for k, v in props:
                print('%s%s%s' % (
                    k, args.field_separator, v))
        else:
            table = prettytable.PrettyTable(['Key', 'Value'])
            table.align['Value'] = 'l'
            for k, v in props:
                if isinstance(v, list) and k not in args.expand_key:
                    v = '(%s items)' % len(v)
                elif isinstance(v, dict) and k not in args.expand_key:
                    v = '(%s keys)' % len(v.keys())
                table.add_row((k, v))
            print(table)

    def _edit_preamble(self):
        """Return a list of lines that should be prepended to an editable
        YAML document to assist the user."""
        return ['This is a YAML document. Take care not to change the format!']

    def _edit_preprocess(self, obj):
        """Pre-process the object direct from the server before the user
        edits it"""
        return obj

    def _edit_postprocess(self, obj):
        """Post-process the object after it has been updated from
        the server with the user's edits. The result will be the direct
        PUT document."""
        return obj

    def _dump_for_edit(self, objs, editable, temp_fn):
        """Dump objects to yaml.

        editable is a list paths into each object, dicts and lists. Example:

        ["id",                        # obj['id']
         "properties/foo",            # obj['properties']['foo']
         "features/0/properties/bar", # obj['features'][0]['properties']['bar']
        ]
        """
        editable_objects = []
        for obj in objs:
            obj = self.client.get_object(self.objtype, id_=obj['id'])
            editable_object = {}
            for path in editable:
                # Pointer to which part of the object we have drilled
                # down to
                tmp = self._edit_preprocess(obj)

                # Pointer to the current level in editable_object we are
                # constructing
                parent = editable_object

                # Drill through the path, moving both pointers down,
                # and only copying from the object to editable_object
                # for the leaves
                elements = path.split('/')
                while elements:
                    element = elements.pop(0)
                    if element.isdigit():
                        element = int(element)
                        childtype = type(tmp[element])
                        tmp = tmp[element]
                    else:
                        childtype = type(tmp[element])
                        tmp = tmp.get(element, {})
                    if elements:
                        try:
                            parent.setdefault(element, childtype())
                        except AttributeError:
                            if len(parent) < element + 1:
                                parent.append(childtype())
                    else:
                        # Assume leaf parent is a dict
                        parent[element] = tmp
                    parent = parent[element]
            editable_objects.append(editable_object)

        if editable_objects:
            with open(temp_fn, 'w') as f:
                f.write(os.linesep.join(['# %s' % line
                                         for line in self._edit_preamble()]))
                f.write(os.linesep * 2)
                f.write(yaml.dump(editable_objects, default_flow_style=False))
        return len(editable_objects)

    def _load_for_edit(self, objs, editable, fn):
        # See definition of editable above in _dump_for_edit()
        log = logging.getLogger('shell_edit')
        with open(fn, 'r') as f:
            editable_objects = yaml.load(f.read())

        if not isinstance(editable_objects, list):
            raise Exception('Input file format is incorrect. The top level '
                            'YAML must be a list')

        if len(editable_objects) != len(objs):
            raise Exception(
                ('Input file contains %i items but matched %i from the '
                 'server. Adding and deleting items via the edit process '
                 'is not supported.') % (len(editable_objects), len(objs)))

        for i, editable_object in enumerate(editable_objects):
            obj = self.client.get_object(self.objtype, id_=objs[i]['id'])

            # We stored the revision in the waypoint file,
            # and we are processing a stable ordering. Compare
            # the n'th server waypoint's revision with the n'th
            # in the file to make sure we have not gotten out of
            # sync with the server (as best we can)
            try:
                self._rev_match(obj, editable_object)
            except Exception as e:
                print('%s #%i: %s' % (self.objtype.title(), i, e))
                continue

            if obj['id'] != editable_object.get('id'):
                log.debug('Server id is %r, local is %r' % (
                    obj['id'], editable_object.get('id')))
                print(('Object %i (%s) id does not match the server;. '
                       'Unable to apply changes') % (
                           i, obj['properties']['title']))
                continue

            for path in editable:
                elements = path.split('/')
                src = editable_object
                dst = obj
                while len(elements) > 1:
                    element = elements.pop(0)
                    if element.isdigit():
                        element = int(element)
                    src = src[element]
                    dst = dst[element]
                leaf = elements[0]

                try:
                    dst[leaf] = src[leaf]
                except KeyError:
                    # User removed this key, so just skip
                    raise Exception(
                        'Missing key %s from object #%i. '
                        'Deleting values during edit is not allowed.' % (path,
                                                                         i))

            obj = self._edit_postprocess(obj)

            log.debug('Updating object: %s' % obj)
            try:
                title = obj['properties']['title']
            except KeyError:
                try:
                    title = obj['features'][0]['properties']['title']
                except KeyError:
                    title = obj['id']
            if self.client.put_object(self.objtype, obj):
                self.verbose('Updated object %i (%s)' % (i, title))
            else:
                raise Exception(('Failed to update object %i (%s): '
                                 'server rejected changes') % (i, title))

    def _edit(self, args, editable):
        if args.in_folder:
            folder = self.get_object(args.in_folder, objtype='folder')
        else:
            folder = None

        log = logging.getLogger('shell_edit')
        try:
            objs = self.find_objects(args.name, match=args.match)
        except _Safety:
            if folder:
                objs = [o for o in self.client.list_objects(self.objtype)
                        if o['folder'] == folder['id']]
            else:
                objs = []

        # Make sure we get a stable sort order across GET/PUT
        objs = sorted(objs, key=lambda o: o['id'])
        if folder:
            objs = [obj for obj in objs if obj['folder'] == folder['id']]
            log.debug('Limiting to folder %s: %s' % (folder['id'], len(objs)))

        if not objs:
            print('No objects matched criteria.')
            return 1

        temp_fn = '%ss.yml' % self.objtype

        if args.interactive:
            self._dump_for_edit(objs, editable, temp_fn)
            orig_mtime = os.path.getmtime(temp_fn)
            subprocess.call([util.get_editor(), temp_fn])
            new_mtime = os.path.getmtime(temp_fn)
            if orig_mtime == new_mtime:
                print('No changes made; not updating')
                return 0
            try:
                self._load_for_edit(objs, editable, temp_fn)
            except Exception as e:
                log.debug(traceback.format_exc())
                print(e)
                return 1

        elif args.file:
            try:
                self._load_for_edit(objs, editable, args.file)
            except Exception as e:
                log.debug(traceback.format_exc())
                print(e)
                return 1
        else:
            count = self._dump_for_edit(objs, editable, temp_fn)
            print(('Wrote %i %ss to %r. Edit and then apply '
                   'with edit -f') % (count, self.objtype, temp_fn))


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
        add.add_argument('--notes', help='Set the notes field', default='')
        add.add_argument('--icon', help='Set the icon field', default='')
        add.add_argument('--dry-run', action='store_true',
                         help=('Do not actually add anything '
                               '(use with --verbose)'))
        edit_ops(cmds)
        folder_ops(add)
        remove_ops(cmds, 'waypoint')
        move_ops(cmds)
        rename_ops(cmds)
        export_ops(cmds)
        list_and_dump_ops(cmds)
        archive_ops(cmds)
        show_ops(cmds)

        cmds.add_parser('list-icons',
                        help='List available icons')

        coords = cmds.add_parser('coords', help='Display coordinates')
        coords.add_argument('name', help='Name (or ID)')

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
        wpt = self.get_object(args.name)
        gc = wpt['geometry']['coordinates']
        print('%.6f,%.6f' % (gc[1], gc[0]))

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


class Track(Command):
    """Manage tracks

    This command allows you to take action on tracks, such as adding,
    removing, and renaming them.
    """

    _editable_properties = ('color', 'notes', 'public', 'title', 'revision')

    @staticmethod
    def opts(parser):
        cmds = parser.add_subparsers(dest='subcommand')

        colorize = cmds.add_parser(
            'colorize', help='Colorize tracks',
            description=('Colorize tracks in various ways. This will allow '
                         'colorizing tracks in various ways, including '
                         'attempting to match tracks in a GPX file and '
                         'changing the GaiaGPS color to match.'))
        colorize.add_argument('name', nargs='*',
                              help='Name (or ID)')
        colorize.add_argument('--in-folder', metavar='FOLDER',
                              help='Only affect items in this folder')
        colorize.add_argument('--match', action='store_true',
                              help=('Treat names as regular expressions and '
                                    'include all matches'))
        colorize.add_argument('--random', action='store_true',
                              help='Randomly colorize selected tracks')
        colorize.add_argument('--from-gpx-file', metavar='FILE',
                              help=('Attempt to colorize tracks to match '
                                    'corresponding data in a GPX file'))
        colorize.add_argument('--dry-run', action='store_true',
                              help=('Do not actually change colors. It is '
                                    'HIGHLY recommended that you use this '
                                    'to validate an approach before allowing '
                                    'changes to be made!'))
        colorize.add_argument('--color',
                              help=('Change matching tracks to this color. '
                                    'Provide an HTML color code '
                                    '(like #FBABCD).'))

        edit_ops(cmds)
        remove_ops(cmds, 'track')
        rename_ops(cmds)
        move_ops(cmds)
        export_ops(cmds)
        list_and_dump_ops(cmds)
        archive_ops(cmds)
        show_ops(cmds)

    def _rev_match(self, server, local):
        srev = server['features'][0]['properties']['revision']
        try:
            lrev = local['features'][0]['properties']['revision']
        except KeyError:
            lrev = None
        if srev != lrev:
            logging.getLogger('track').debug(
                'Server revision is %r, local is %r' % (
                    srev, lrev))
            raise Exception(
                ('%s has changed on the server or '
                 'lists are out of sync; unable to apply changes') % (
                    server['features'][0]['properties']['title']))

    def _edit_preamble(self):
        return (super(Track, self)._edit_preamble() +
                textwrap.wrap('Available colors are: ' +
                              ' '.join(util.COLOR_ALIASES.keys())))

    def _edit_preprocess(self, obj):
        color_rev = {v: k for k, v in util.COLOR_ALIASES.items()}
        props = {k: obj['features'][0]['properties'][k]
                 for k in self._editable_properties}
        props['color'] = color_rev.get(props['color'].upper(), props['color'])
        props['id'] = obj['id']
        obj['features'][0]['properties'] = props
        return obj

    def _edit_postprocess(self, obj):
        # For some reason tracks are different than waypoints. The PUT
        # seems to expect just a dict of properties. We include id here
        # because apiclient expects it for logging, but otherwise just
        # dump the properties into the payload.
        color_fwd = util.COLOR_ALIASES
        props = obj['features'][0]['properties']
        # For some reason the server changes the colors slightly on upload.
        # The COLOR_ALIASES are the ones defined in the web app.
        props['color'] = color_fwd.get(props['color'].lower(),
                                       props['color'])
        return dict({k: v for k, v in props.items()
                     if k in self._editable_properties},
                    id=obj['id'])

    def edit(self, args):
        editable = ['id'] + \
            ['features/0/properties/%s' % p for p in self._editable_properties]
        return self._edit(args, editable)

    def _colorize_tracks_by_id(self, dry_run, tracks):
        for (track_name, track_id), color_code in tracks.items():
            self.verbose('Coloring track %r %r' % (track_name, color_code))
            if dry_run:
                continue
            if not self.client.put_object('track',
                                          {'id': track_id,
                                           'color': color_code}):
                raise RuntimeError('Failed to set track %r to %r' % (
                    track_id, color_code))

    def colorize(self, args):
        try:
            objs = self.find_objects(args.name, match=args.match)
        except _Safety:
            objs = []

        if args.name and not objs:
            # Some query was provided but we found nothing. Run no further.
            print('No matching objects to colorize')
            return 1

        if args.in_folder:
            folder_id = self.get_object(args.in_folder, objtype='folder')['id']
        else:
            folder_id = None

        def only_folder(objs):
            return [o for o in objs
                    if folder_id is None or o['folder'] == folder_id]

        if args.random:
            colors = list(util.COLOR_ALIASES.values())
            self._colorize_tracks_by_id(
                args.dry_run,
                {(t['title'], t['id']): random.choice(colors)
                 for t in only_folder(objs)})
        elif args.from_gpx_file:
            gpx_tracks = util.get_track_colors_from_gpx(args.from_gpx_file)
            to_change = {}

            if not gpx_tracks:
                print('No colored tracks found in %r' % args.from_gpx_file)
                return 1

            if not objs:
                # No names/ids specified, so try to look up everything
                # in the GPX file. This is not very efficient, but alas.
                objs = self.find_objects(gpx_tracks.keys(), allow_missing=True)
                self.verbose(
                    'Looked up %i tracks from %i found in GPX file' % (
                        len(objs), len(gpx_tracks)))

            if not objs:
                print('No matching objects to colorize')
                return 1

            for obj in only_folder(objs):
                if obj['title'] in gpx_tracks:
                    to_change[(obj['title'], obj['id'])] = (
                        util.COLOR_ALIASES[
                            util.GPXX_COLORS_TO_GAIA[
                                gpx_tracks[obj['title']]]])
                else:
                    self.verbose('Track %r not found in GPX file' % (
                        obj['title']))
            self._colorize_tracks_by_id(args.dry_run, to_change)
        elif args.color:
            if not re.match('^#?[A-f0-9]{6}$', args.color):
                print('Invalid color code. Provide an HTML color like #FCEBDA')
                return 1
            if not args.color.startswith('#'):
                args.color = '#%s' % args.color
            self._colorize_tracks_by_id(
                args.dry_run,
                {(o['title'], o['id']): args.color for o in only_folder(objs)})


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
        add.add_argument('--dry-run', action='store_true',
                         help=('Do not actually add anything '
                               '(use with --verbose)'))
        folder_ops(add, allownew=False)
        remove = remove_ops(cmds, 'folder')
        remove.add_argument('--force', action='store_true',
                            help='Remove even if not empty')
        move_ops(cmds)
        export_ops(cmds)
        list_and_dump_ops(cmds)
        archive_ops(cmds)
        show_ops(cmds)
        rename_ops(cmds)

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
            return 1


class Tree(Command):
    """Display all data in tree format

    This command will print all waypoints, tracks, and folders in a
    hierarchical layout, purely for visualization purposes.
    """
    @staticmethod
    def opts(parser):
        parser.add_argument('--long', action='store_true',
                            help='Show long format with dates')

    def default(self, args):
        folders = self.client.list_objects('folder')
        root = util.make_tree(folders)
        tree = util.resolve_tree(self.client, root)
        util.pprint_folder(tree, long=args.long)


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
        parser.add_argument('--strip-gpx-extensions', action='store_true',
                            help=('Remove all schema extensions from file '
                                  'before uploading. This applies only to '
                                  'GPX files and may help improve '
                                  'compatibility as gaiagps will choke on '
                                  'files with extensions.'))
        parser.add_argument('--poll', action='store_true',
                            help=('Poll server for up to a minute for '
                                  'completion in the case where an upload '
                                  'is queued for processing.'))
        parser.add_argument('--colorize-tracks', action='store_true',
                            help=('Attempt to colorize tracks after upload '
                                  'to match the source file (GPX only)'))
        folder_ops(parser)

    def _poll_for_upload(self, expected_folder):
        sleep_time = 5
        timeout = 60
        self.verbose('Waiting for upload to appear...', '')
        for i in range(0, timeout // sleep_time):
            try:
                folder = self.client.get_object('folder', expected_folder)
                self.verbose('done')
                return folder
            except apiclient.NotFound:
                pass

            self.verbose('.', '')
            time.sleep(sleep_time)

    def default(self, args):
        log = logging.getLogger('upload')

        if args.strip_gpx_extensions:
            tmpfile = os.path.join(
                os.path.dirname(args.filename),
                'clean-%s' % os.path.basename(args.filename))
            self.verbose('Stripping GPX extensions from input file')
            util.strip_gpx_extensions(args.filename, tmpfile)
            args.filename = tmpfile

        if args.existing_folder:
            dst_folder = self.get_object(args.existing_folder,
                                         objtype='folder')
        else:
            dst_folder = None

        new_folder = self.client.upload_file(args.filename)

        if not new_folder and args.poll:
            new_folder = self._poll_for_upload(os.path.basename(args.filename))

        if not new_folder:
            print('File upload has been queued at the server and '
                  'may take time to appear.')
            if dst_folder:
                print('Unable to move to destination folder until '
                      'processing is complete.')
            return

        log.debug(new_folder)
        log.info('Uploaded file to new folder %s/%s' % (
            new_folder['properties']['name'],
            new_folder['id']))

        if args.colorize_tracks:
            track_cmd = Track(self.client, verbose=args.verbose)
            args.name = []
            args.match = None
            args.random = None
            args.dry_run = None
            args.from_gpx_file = args.filename
            args.in_folder = new_folder['properties']['name']
            try:
                track_cmd.colorize(args)
            except Exception as e:
                log.debug(traceback.format_exc())
                print('Failed to colorize track: %s' % e)

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
                return 1
            log.info('Deleting temporary folder %s' % (
                new_folder['properties']['name']))
            self.client.delete_object('folder', new_folder['id'])


class Query(Command):
    """Allow direct query by URL for debugging.

    Developer tool for issuing manual queries against the API.
    """
    @staticmethod
    def opts(parser):
        parser.add_argument('path',
                            help='API URL path')
        parser.add_argument('-a', nargs='*', metavar='KEY=VALUE',
                            dest='args', default=[],
                            help='Query string argument in the form key=value')
        parser.add_argument('-X', default='GET', choices=('GET', 'PUT', 'POST',
                                                          'DELETE', 'OPTIONS',
                                                          'HEAD'),
                            dest='method', metavar='METHOD',
                            help='Method (default is GET)')
        parser.add_argument('-q', action='store_true',
                            dest='quiet',
                            help=('Suppress response information; '
                                  'only print content'))

    def default(self, args):
        method = getattr(self.client.s, args.method.lower())
        r = method(apiclient.gurl(*args.path.split('/')),
                   params=dict(x.split('=', 1) for x in args.args))
        if not args.quiet:
            print('HTTP %i %s' % (r.status_code, r.reason))
            for h in r.headers:
                print('%s: %s' % (h, r.headers[h]))
            print()

        if 'json' in r.headers.get('Content-Type', ''):
            pprint.pprint(r.json())
        else:
            print(r.content)


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

    command_classes = [Waypoint, Folder, Test, Tree, Track, Upload]
    commands = {}

    if 'GAIAGPSCLIENTDEV' in os.environ:
        command_classes.append(Query)

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

        command = commands[args.cmd](client, verbose=args.verbose)
        try:
            return int(command.dispatch(parser, args) or 0)
        except (apiclient.NotFound, RuntimeError) as e:
            root_logger.debug(traceback.format_exc())
            print(e)
            return 1


if __name__ == '__main__':
    sys.exit(main())
