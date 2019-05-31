import logging
import os
import sys
import time
import traceback

from gaiagps import apiclient
from gaiagps import util
from gaiagps.shell import command
from gaiagps.shell import options
from gaiagps.shell import track


class Upload(command.Command):
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
        options.folder_ops(parser)

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
            sys.stdout.flush()
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
            track_cmd = track.Track(self.client, verbose=args.verbose)
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
            for t in new_folder_desc['tracks']:
                log.info('Moving track %s' % t)
                dst_folder_desc['tracks'].append(t)
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
