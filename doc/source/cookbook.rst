========
Cookbook
========

This document provides several examples of common operations for which
gaiagpsclient may be helpful. These are things that may be hard,
laborious, or impossible with the main web client or associated apps.

This document assumes you have completed :doc:`install` already and
have performed the :ref:`ValidateInstall` process.

Add a waypoint by coordinates
=============================

One of the most fundamental things that is (or has been) impossible
via the web client is the simple task of adding a waypoint by
coordinates (i.e. latitiude and longitude). This is easy with gaiagpsclient:

.. prompt:: bash

  gaiagps waypoint add 'My Campsite' 45.5522 -122.91234

For more information on adding waypoints, run ``gaiagps waypoint add --help``.

Upload a GPX file with extensions
=================================

Many mature applications that deal with GPX files include standardized
"extensions" to the base GPX information to specify things like track
colors, route shaping, etc. GaiaGPS cannot handle these extensions and
will give you an obscure message like this::

  Your upload for 'test.gpx' has failed

  Invalid file format

if it is unable to handle the extensions within. Other factors can
cause this response as well, but if you've exported a GPX file from an
application and receive this error from GaiaGPS, try removing the
extensions.

To strip the extensions from a GPX file and upload the bare data, do this:

.. prompt:: bash

  gaiagps upload --strip-gpx-extensions test.gpx

Bulk Edits
==========

The GaiaGPS web client can be rather click-intensive when needing to
make changes to multiple items at once. With the *edit* function,
gaiagpsclient allows making changes to several objects and properties
in a single operation, using a plain text editor.

Suppose I have added three waypoints and I want to add notes for all
three. I can use the interactive edit function to do this:

.. prompt:: bash

  gaiagps waypoint edit -i camp1 camp2 camp3

This will jump into an editor with the mutable fields in YAML
format. I can make my edits, save the file, and when I exit, the
changes will be uploaded back to GaiaGPS::

  - id: cb81e0e2-558a-4b8f-8689-9d3c84f5740d
    properties:
      icon: campsite
      notes: 'Backup camp spot in gravel lot'
      public: false
      revision: 4863
      title: camp1
  - id: cc7ef68b-99f3-481a-b000-235abd0f5837
    properties:
      icon: campsite
      notes: 'Primary camp spot'
      public: false
      revision: 4865
      title: camp2
  - id: 6d9a5fb5-ce68-4c57-af99-ca01a5f8b40c
    properties:
      icon: campsite
      notes: 'Camp spot for second day'
      public: false
      revision: 287
      title: camp3

Colorize Tracks
===============

GaiaGPS supports colorized tracks, but only (currently) when set
manually. Colorizing a lot of tracks, especially when importing from a
source that already has said colors, can be laborious. The ``track
colorize`` function in gaiagpsclient can help to some degree.

In general, colors are provided as `HTML color codes <https://jonasjacek.github.io/colors/>`_.

If your tracks are named in a predictable way, you might be able to
use pattern matching to set some colors. For example:

.. prompt:: bash

  gaiagps track colorize --color #ff0000 --match 'Snowmachine Route'

Which would change the color of any tracks with "Snowmachine Route" in the name to red.

You also might want to just randomize the colors of several routes so
you can more easily see where they begin and end:

.. prompt:: bash $ auto

  $ gaiagps track colorize --verbose --random --match 'Memorial Day Hikes'
  Coloring track 'Hike Day 1' '#F90553'
  Coloring track 'Hike Day 2' '#000000'
  Coloring track 'Hike Day 3' '#F90553'
  Coloring track 'Hike Day 1' '#FFF011'

.. note:: Be sure to use ``--dry-run`` and ``--verbose`` when working
          with this function to check an operation before you let it
          actually run to make sure you are matching the tracks you
          expect. It would be bad to accidentally change the color of
          all the tracks in your account to a single color!

A very common point of frustration is having a GPX file full of tracks
that already contain route coloring information, only to find that
GaiaGPS ignores them when you upload. We can try to match tracks that
exist in a GPX file and use the colors within to update GaiaGPS' track
colors. Assuming we have a GPX file locally, we can first upload that
file and then re-process it for track color information:

.. prompt:: bash

  gaiagps upload foo.gpx

.. note:: Large file uploads are sometimes queued, so you may need to
          wait between these steps until the upload appears.

.. prompt:: bash $ auto

  $ gaiagps folder list
  +-------------------------+----------------------+-------------------+
  |           Name          |       Updated        |       Folder      |
  +-------------------------+----------------------+-------------------+
  |          foo.gpx        | 20 May 2019 14:23:11 |                   |
  +-------------------------+----------------------+-------------------+
  $ gaiagps track colorize --verbose --from-gpx-file=foo.gpx
  Looked up 2 tracks from 2 found in GPX file
  Coloring 'Path to trailhead' to '#F90553'
  Coloring 'Epic mountaintop hike' to '#A4A4A4'

.. note:: It is also possible to do this as a single operation, by
          passing ``--colorize-tracks`` to ``upload``. You will likely
          need ``--poll`` as well as larger files with long tracks are
          likely to be queued by the server for background processing
          and track colorizing must be done after that is complete.

Combine two folders
===================

Currently, GaiaGPS does not make it easy to combine two folders
(i.e. copy all of one folder's contents into another). This is easy
with gaiagpsclient, moving the waypoints and tracks in separate steps.

For example, we can move all waypoints from one folder into another:

.. prompt:: bash $ auto

  $ gaiagps --verbose waypoint move --in-folder 'Some Extra Items' 'My Trip'
  Generating list of items in folder 'Some Extra Items'
  Moving waypoint 'Camp spot?' (86898502-b448-46c2-b592-c12a5676e9af) to My Trip
  Moving waypoint 'Nice camp spot' (51280d87-b16d-41f6-9ba4-9e465618ad2f) to My Trip
  Moving waypoint 'Flat camping off road a ways' (2dce8501-9a34-4898-bf2a-141c1caea277) to My Trip
  Moving waypoint 'Camp spots' (a8047fb7-60fa-42ea-8531-b66e78e9774c) to My Trip
  Moving waypoint 'Good camp spot near here' (8c262804-28fe-443b-842a-5fc4db91d924) to My Trip
  Moving waypoint 'Road spur blocked' (ddb24ec2-a5e5-4ef9-9056-3e658d4c838e) to My Trip

After that, we can move the tracks as well:

.. prompt:: bash $ auto

  $ gaiagps --verbose track move --in-folder 'Some Extra Items' 'My Trip'
  Generating list of items in folder 'Some Extra Items'
  Moving track 'Path to campsite' (86898502-b448-46c2-b592-c12a5676e9af) to My Trip

Finally, we can (if desired) remove the original, now-empty folder:

.. prompt:: bash $ auto

  $ gaiagps folder remove 'Some Extra Items'
  Removing folder 'Some Extra Items' (7eb228e1-43a3-47bd-8641-1c4184eef269)
