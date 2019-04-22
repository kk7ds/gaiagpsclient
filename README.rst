=============
gaiagpsclient
=============

.. image:: https://travis-ci.org/kk7ds/gaiagpsclient.svg?branch=master
    :target: https://travis-ci.org/kk7ds/gaiagpsclient

.. image:: https://readthedocs.org/projects/gaiagpsclient/badge/?version=latest
    :target: https://gaiagpsclient.readthedocs.io/en/latest/?badge=latest

.. image:: https://coveralls.io/repos/github/kk7ds/gaiagpsclient/badge.svg?branch=master&killcache=1
    :target: https://coveralls.io/github/kk7ds/gaiagpsclient?branch=master


A Python API and CLI client for GaiaGPS. I wrote this for myself, but it may be useful for others. Gaia does not have a published API, so this was developed by reverse engineering the browser client and thus may be incomplete or poorly behaved. It is possible to use this to put undue strain on gaiagps.com, so please be judicious with its use. This client is not supported or blessed by Gaia, so do not complain about it to them or ask them for help.

Installation
------------

On a modern Linux (and MacOS with python3 from brew), something like this should work:

.. code-block:: shell

  $ git clone https://github.com/kk7ds/gaiagpsclient
  $ cd gaiagpsclient
  $ python setup.py install

CLI Usage
---------

The command line client will attempt to login to gaiagps.com only when necessary, caching the session credentials whenever possible. Thus, at least the first use requires your Gaia credentials, and any time after that session expires. After installation, try testing your connection, which will perform a login and validate that communication is possible:

.. code-block:: shell

  $ gaiagps --user user@domain.com test
  Password:
  Success!

After that, you can perform commands without providing your username or password.

The available high-level commands are displayed with ``--help``::

  $ gaiagps --help
  usage: gaiagps [-h] [--user USER] [--pass PASS] [--debug] [--verbose]
                 {waypoint,folder,test,tree,track,upload} ...

  Command line client for gaiagps.com

  positional arguments:
    {waypoint,folder,test,tree,track,upload}
      waypoint            Manage waypoints
      folder              Manage folders
      test                Test access to Gaia
      tree                Display all data in tree format
      track               Manage tracks
      upload              Upload an entire file of tracks and/or waypoints

  optional arguments:
    -h, --help            show this help message and exit
    --user USER           Gaia username
    --pass PASS           Gaia password (prompt if unspecified)
    --debug               Enable debug output
    --verbose             Enable verbose output

Help per-command is displayed the same way::

  $ gaiagps waypoint --help
  usage: gaiagps waypoint [-h]
                          {add,remove,move,rename,export,list,dump,url,coords}
                          ...

  This command allows you to take action on waypoints, such as adding, removing,
  and renaming them.

  positional arguments:
    {add,remove,move,rename,export,list,dump,url,coords}
      add                 Add a waypoint
      remove              Remove a waypoint
      move                Move to another folder
      rename              Rename
      export              Export to file
      list                List
      dump                Raw dump of the data structure
      url                 Show direct browser-suitable URL
      coords              Display coordinates

  optional arguments:
   -h, --help            show this help message and exit


  $ gaiagps waypoint add --help
  usage: gaiagps waypoint add [-h] [--existing-folder EXISTING_FOLDER]
                              [--new-folder NEW_FOLDER]
                              name latitude longitude [altitude]

  positional arguments:
    name                  Name (or ID)
    latitude              Latitude (in decimal degrees)
    longitude             Longitude (in decimal degrees)
    altitude              Altitude (in meters

  optional arguments:
    -h, --help            show this help message and exit
    --existing-folder EXISTING_FOLDER
                          Add to existing folder with this name
    --new-folder NEW_FOLDER
                          Add to a new folder with this name

Examples
~~~~~~~~

Here are some example common operations to demonstrate usage::

  # Add a waypoint by lat/lon
  $ gaiagps waypoint add 'My Campsite' 45.123 -122.9876

  # Show the waypoints so far
  $ gaiagps waypoint list
  +--------------------------------+----------------------+------------------+
  |              Name              |       Updated        |      Folder      |
  +--------------------------------+----------------------+------------------+
  |          My Campsite           | 19 Apr 2019 03:41:53 |                  |
  +--------------------------------+----------------------+------------------+

  # Create a folder and move our waypoint into that folder
  $ gaiagps folder add 'Camping Trip'
  $ gaiagps waypoint move 'My Campsite' 'Camping Trip'
  $ gaiagps waypoint list
  +--------------------------------+----------------------+------------------+
  |              Name              |       Updated        |      Folder      |
  +--------------------------------+----------------------+------------------+
  |          My Campsite           | 19 Apr 2019 03:41:53 |   Camping Trip   |
  +--------------------------------+----------------------+------------------+

  # Upload a GPX file with a track inside
  $ gaiagps upload --existing-folder 'Camping Trip' myhike.gpx
  $ gaiagps track list
  +--------------------------------+----------------------+------------------+
  |              Name              |       Updated        |      Folder      |
  +--------------------------------+----------------------+------------------+
  |           Cool Hike            | 19 Apr 2019 03:42:17 |   Camping Trip   |
  +--------------------------------+----------------------+------------------+

  # Dump all data in Gaia account (assuming more has been added), like a filesystem
  $ gaiagps tree
  DIR 18 Apr 2019 22:08:14 Camping Trip/
      WPT 19 Apr 2019 03:41:53 My Campsite
      TRK 19 Apr 2019 03:42:17 Cool Hike

  DIR 09 Apr 2019 00:32:11 My Other Folder/

      DIR 19 Apr 2019 00:37:51 A Subfolder/
          WPT 19 Apr 2019 00:38:03 Some random waypoint

      WPT 11 Apr 2019 01:56:19 Waterfall
      WPT 11 Apr 2019 01:52:56 Trailhead


Testing and Docs
----------------

Tests are split into unit and functional groups. Unit tests can be run in isolation; functional tests run against gaiagps.com itself and require credentials to be set in the environment to run. As functional testing has the potential to generate potentialy-unwanted load on Gaia's servers, try to avoid running those more than necessary.

Testing and building docs requires tox::

  $ pip install tox
  $ tox -e style,unit,doc

Docs will be built and available in ``doc/build/index.html``, or you can read them at RTD_.

  .. _RTD: https://gaiagpsclient.readthedocs.io/en/latest/
