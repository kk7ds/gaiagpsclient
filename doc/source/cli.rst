Command Line Usage
==================

Overview
--------

Assuming a normal install, the command-line client is called ``gaiagps`` and is self-documenting. For
example, this gives an overview of global options and the top-level commands::

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

The client attempts to login to gaiagps.com as infrequently as possible and stores session information
to reduce the frequency of having to provide credentials. However, the first time user will have to login
at least once, and any time the session expires. To do this the first time, use the ``test`` command::

  $ gaiagps --user user@domain.com test
  Password:
  Success!

Afterwards, you need not provide your username for subsequent usage (until your session expires)::

  $ gaiagps test
  Success!

Commands
--------

The utility is arranged hierarchically with top-level commands, some
of which have sub commands. For example, the ``waypoint`` command  has
multiple sub-commands for things like ``add``, ``rename``, ``remove``,
etc::

  $ gaiagps waypoint add 'My Campsite' 45.124 -122.987
  $ gaiagps waypoint rename 'My Campsite' 'Cool Campsite'
  $ gaiagps waypoint remove 'Cool Campsite'

For the primary data types that Gaia stores, the ``waypoint``,
``track``, and ``folder`` commands provide the bulk of the
functionality of the utility. Each command has its own ``--help``
output, which tells you what you can do with each thing. For example::

  $ gaiagps folder --help
  usage: gaiagps folder [-h] {add,remove,move,export,list,dump,url} ...

  This command allows you to take action on folders, such as adding, removing,
  and moving them.

  positional arguments:
    {add,remove,move,export,list,dump,url}
      add                 Add a folder
      remove              Remove a folder
      move                Move to another folder
      export              Export to file
      list                List
      dump                Raw dump of the data structure
      url                 Show direct browser-suitable URL

  optional arguments:
    -h, --help            show this help message and exit

Folder Organization
-------------------

Gaia organizes data loosely into a hierarchical structure. By default,
all data items live at the "root" level, but can be moved into
folders. Folders can also be moved into folders, creating an
arbitrarily deep tree structure. For example, to create a folder and
move a waypoint into that folder, do the following::

  $ gaiagps folder add 'My Folder'
  $ gaiagps waypoint move 'Cool Campsite' 'My Folder'

.. note::

  Removing a folder will remove all the contents of that folder,
  including other folders. Use caution when removing folders!

Some operations that create data allow those items to be automatically
moved into a new or existing folder. For example, to create a new
folder inside another folder, you would::

  $ gaiagps folder add --existing-folder 'My Folder' 'Subfolder'

When you create a waypoint, you can add it to an existing folder, or
create new folder at the same time::

  $ gaiagps waypoint add --new-folder 'My New Folder' 'Trailhead' 45.321 -122.9012

Duplicate Names
---------------

Gaia allows you to create data objects with identical names. This
makes it hard to distinguish one from the other, both in the web UI as
well as at the command line. If you get into a situation where you
have multiple objects with the same name, some work is required to
disambiguate them. Consider the following scenario::

  $ gaiagps waypoint list
  +--------------------------------+----------------------+------------------+
  |              Name              |       Updated        |      Folder      |
  +--------------------------------+----------------------+------------------+
  |          My Campsite           | 20 Apr 2019 02:58:21 |                  |
  |          My Campsite           | 19 Apr 2019 03:41:53 |                  |
  +--------------------------------+----------------------+------------------+

Here we have two waypoints called "My Campsite". If I wanted to take
action on on of them, say move it into a folder, I am unable to
specify the name::

  $ gaiagps waypoint move 'My Campsite' 'My Folder'
  Multiple items with title=My Campsite found

In this case, assume I was on a weekend camping trip and I marked the
campsite where we stayed each night on my tablet. Not thinking about
it, I named them the same thing. Now, months later, I want to suggest
one of those sites to a friend, but I don't remember which was
which. The timestamp of the waypoint may be enough to determine which
is which, but maybe not. Either way, the steps for renaming one or
both are:

 1. Get the unique ID of each one
 2. Confirm which one is which
 3. Rename one of them using the ID instead of the name

To show the items with names and IDs, use the ``--by-id`` option to
list::

  $ gaiagps waypoint list --by-id
  6e87d380-00a0-44b0-9b01-b127dc8e0ffe 20 Apr 2019 02:58:21 'My Campsite'
  7568434e-c9e3-42b4-b65f-29a855087672 19 Apr 2019 03:41:53 'My Campsite'

If the timestamp is enough to know which campsite is which, then you
now have the ID necessary for the rename step. If the timestamp is not
sufficient, you can get the browser-friendly URL of the item, by id,
and look at it in the Gaia web UI to figure it out::

  $ gaiagps waypoint url 6e87d380-00a0-44b0-9b01-b127dc8e0ffe
  https://www.gaiagps.com/datasummary/waypoint/6e87d380-00a0-44b0-9b01-b127dc8e0ffe

To continue the example, I now have enough information to know that
the first campsite from 20-April-2019 is the one I want to share. In
order to change the name of it to distinguish it from the other, I can
use the ID::

  $ gaiagps waypoint rename 6e87d380-00a0-44b0-9b01-b127dc8e0ffe 'Awesome Campsite'

Now, my waypoint list looks like this::

  $ gaiagps waypoint list
  +--------------------------------+----------------------+------------------+
  |              Name              |       Updated        |      Folder      |
  +--------------------------------+----------------------+------------------+
  |       Awesome Campsite         | 20 Apr 2019 02:58:21 |                  |
  |         My Campsite            | 19 Apr 2019 03:41:53 |                  |
  +--------------------------------+----------------------+------------------+

Since they now have different names, I can now manage them each by their name.

Matching and Bulk Operations
----------------------------

Some commands support operating on multiple items at once. For
example, you can move multiple waypoints into a folder in a single
command::

  $ gaiagps waypoint move 'Campsite' 'Trailhead' 'Summit' 'My Hike'

Further, you can also use a regular expression to select multiple
items to operate on::

  $ gaiagps waypoint move --match 'Camp.*' 'All Campsites'

.. note::

  Matching with a regular expression is very powerful, but has the
  potential to let you do a lot of damage very easily. Exercise
  caution when using this feature.
