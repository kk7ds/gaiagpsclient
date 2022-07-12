import logging
import os
import pprint
import prettytable
import re
import subprocess
import sys
import traceback
import yaml

from gaiagps import apiclient
from gaiagps import util


class _Safety(Exception):
    pass


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

    def folder_filter(self, name_or_id):
        """Return a function that will filter a list of items by folder, or
        generate all items in a folder.

        This returns a function which, when called with an iterable, will
        generate results that are inside the specified folder (or all if
        name_or_id is None). If the iterable is empty, then generate all
        items (of self.objtype) in the folder.
        """
        if name_or_id == '':
            # An empty string folder id means "at the root" to gaiagps
            folder_id = ''
        elif name_or_id is None:
            # None means no folder was requested
            folder_id = None
        else:
            folder_id = self.get_object(name_or_id, objtype='folder')['id']

        def _folder_filter(items):
            if not items and folder_id is not None:
                self.verbose('Generating list of items in folder %r' % (
                    name_or_id))
                items = self.client.list_objects(self.objtype)
            for item in items:
                if folder_id is None or item['folder'] == folder_id:
                    yield item

        return _folder_filter

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
        try:
            to_remove = self.find_objects(args.name, match=args.match)
        except _Safety:
            to_remove = []
        folder_filter = self.folder_filter(args.in_folder)
        for obj in folder_filter(to_remove):
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
            to_move = []

        folder_filter = self.folder_filter(args.in_folder)
        to_move = list(folder_filter(to_move))

        if not to_move:
            self.verbose('No items matched criteria')
            return 1

        if args.destination == '/':
            for obj in folder_filter(to_move):
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
            for obj in folder_filter(to_move):
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

        folder_filter = self.folder_filter(args.in_folder)

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

        for item in sorted(folder_filter(items), key=sortkey):
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
            to_hit = []

        folder_filter = self.folder_filter(args.in_folder)
        to_hit = list(folder_filter(to_hit))

        if not to_hit:
            self.verbose('No items matched criteria')
            return 1

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
        folder_filter = self.folder_filter(args.in_folder)

        log = logging.getLogger('shell_edit')
        try:
            objs = self.find_objects(args.name, match=args.match)
        except _Safety:
            objs = []

        # Make sure we get a stable sort order across GET/PUT
        objs = sorted(list(folder_filter(objs)), key=lambda o: o['id'])

        if not objs:
            print('No objects matched criteria.')
            return 1

        temp_fn = '%ss.yml' % self.objtype

        if hasattr(args, 'interactive') and args.interactive:
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
