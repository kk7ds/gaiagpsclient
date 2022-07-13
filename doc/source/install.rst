Installing gaiagpsclient
========================

The home page for the project is on `github`__, but the following recipes
will be what most people will want.

.. _github: https://github.com/kk7ds/gaiagpsclient

__ github_

Linux
-----

In a modern Linux, the requirements are just ``python3``, the ``pip`` module, and ``git``. Below are commands for common distros to install these packages and gaiagpsclient itself.

Ubuntu/Debian
~~~~~~~~~~~~~

.. prompt:: bash

  sudo apt-get install -y python3-pip git
  sudo python3 -mpip install git+https://github.com/kk7ds/gaiagpsclient

Fedora/Red Hat
~~~~~~~~~~~~~~

.. prompt:: bash

  sudo dnf -y install python3-pip git
  sudo python3 -mpip install git+https://github.com/kk7ds/gaiagpsclient

macOS
-----

On a Mac, homebrew_ is required. Install it first with the instructions on `their page`__. Once installed, you can install the required packages from it:

.. prompt:: bash

  brew install python3 git
  sudo python3 -mpip install git+https://github.com/kk7ds/gaiagpsclient

.. _homebrew: https://brew.sh

__ homebrew_

Windows
-------

On Windows, you first need to download Python from `python.org <https://www.python.org/downloads/>`_.

.. note:: During the install, **be sure** to select *Add Python to PATH*.

Next, you can use ``python`` and ``pip`` to install directly from github. `Open the command prompt <https://www.lifewire.com/how-to-open-command-prompt-2618089>`_ and type::

  python -mpip install https://github.com/kk7ds/gaiagpsclient/archive/master.zip


.. _ValidateInstall:

Validating the install
----------------------

Regardless of your platform, once you have installed the client you should confirm that it is working. To do this, use the ``test`` command to perform your first login. Use your own gaiagps.com username and provide your password prompted.

.. prompt:: bash $ auto

  $ gaiagps --user foo@domain.com test
  Password:
  Success!

If you see the success message, then you can proceed to regular :doc:`usage <cli>`.
