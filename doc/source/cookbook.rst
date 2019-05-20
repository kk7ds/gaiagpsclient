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
  Coloring track 'b2addc30-4c1e-4ac3-b812-7624f97b631e' '#F90553'
  Coloring track '1344c969-50b0-4ee6-87bd-d6d23dd5a202' '#000000'
  Coloring track 'ca7083fe-eb17-498e-bd7d-841f0ab54513' '#F90553'
  Coloring track '82945a6f-319e-4af2-9885-b73094ec86bb' '#FFF011'
  Coloring track 'fc1afb0b-47f5-42a9-86d7-55616581ec14' '#009B89'
  Coloring track '03d553aa-9598-48ff-842d-640ba2cf6941' '#FFC900'
  Coloring track '4d556b5b-60fa-4c42-a5d9-5a12b98cf44e' '#B60DC3'

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

.. prompt:: bash $ auto

  gaiagps upload foo.gpx

.. note:: Large file uploads are sometimes queued, so you may need to
          wait between these steps until the upload appears.

.. prompt:: bash $

  $ gaiagps folder list
  +-------------------------+----------------------+-------------------+
  |           Name          |       Updated        |       Folder      |
  +-------------------------+----------------------+-------------------+
  |          foo.gpx        | 20 May 2019 14:23:11 |                   |
  +-------------------------+----------------------+-------------------+
  $ gaiagps track colorize --verbose --from-gpx-file=foo.gpx
  Looked up 2 tracks from 2 found in GPX file
  Coloring '3e009336-cba5-4d4d-a06a-e8a04d942520' to '#F90553'
  Coloring '2409824e-89bd-4f61-a357-df3e5e1b740b' to '#A4A4A4'
