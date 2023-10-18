****************
Admin Guide
****************

.. |rds-streams| image:: /images/rds-ico-streams.png
   :height: 3ex
   :class: no-scaled-link

The Time Machine Reader app runs as a Windows service, while the web backend
runs under Docker. Both together make the app known as **tmtility**.

Installation
======================

Docker Installation
-----------------------

See https://docs.docker.com/desktop/install/windows-install/
for installation of Docker before installing this application.

Install wsl. You may need to enable virtualization. See https://aka.ms/enablevirtualization for details.

.. code-block:: shell

    wsl --install

Follow instructions in https://docs.docker.com/get-docker/

* install Docker Desktop Installer (https://docs.docker.com/desktop/install/windows-install/)

  .. note::

    the application is a Linux container, so ignore all the stuff about windows containers on the webpage


App Installation
---------------------
* download https://github.com/louking/tm-csv-connector/blob/main/dist/tm-csv-connector.zip
* extract files from the downloaded file you want the app to run from
* navigate to this directory
* start powershell **Run as Administrator**, and navigate to this directory

    .. note:: you'll have to accept the User Account Control challenge, which may be seen elsewhere on the taskbar

* before you execute these commands for the first time, you'll need to do the following

  .. code-block:: shell

    edit `c:\Windows\System32\Drivers\etc\hosts`, add 127.0.0.1 tm.localhost
    Set-ExecutionPolicy Bypass # type y to accept
    docker login # then enter your credentials

  * if you see something similar to 

      .. code-block:: shell

          The package(s) come(s) from a package source that is not marked as trusted.
          Are you sure you want to install software from
          'https://onegetcdn.azureedge.net/providers/nuget-2.8.5.208.package.swidtag'?
          [Y] Yes  [A] Yes to All  [N] No  [L] No to All  [S] Suspend  [?] Help (default is "N"):
  
    type `a`

* run the install procedure

    .. code-block:: shell

        ./install

    * enter directory names for the output csv file, and for the logging files (full path)
    * enter passwords for root and app database users -- accepting the defaults are fine

    .. note:: you can see the values of these later by navigating to config/db in the installation directory

* the first time it's run, it takes a bit of time for the app to create the database, etc
* with your browser, navigate to http://tm.localhost:8080/ 
* navigate to Settings view (this only has to be done once)

  * add New setting, Setting=output-file, Value=tm-data.dsv # or whatever filename you want the outputput put in


App Upgrade
-------------
* download https://github.com/louking/tm-csv-connector/blob/main/dist/tm-csv-connector.zip
* start powershell **Run as Administrator**, and navigate to the install directory

    .. note:: you'll have to accept the User Account Control challenge, which may be seen elsewhere on the taskbar

* disable the app

    .. code-block:: shell

        ./disable-all

* extract files from the downloaded file to the install directory

* run the install procedure

    .. code-block:: shell

        ./install


.. _set up RDS:

Set up RaceDay Scoring
======================
* at Streams |rds-streams| panel, create a stream for Time Machine

  * Stream Name: Time Machine
  * Stream Type: File (Custom or Chip System Type)
  * File Type: File (Custom or Chip System Type)
  * Folder Path: MAIN-FOLDER-PATH
  * File Extension: csv
  * Passing Format: [IGNORE],[BIBCODE],[TIME]
  * Field Delimiter: ,
  * Assign as a Backup Stream for these Timing Locations: Finish

Jackery Working Time
======================
* 241Wh * 0.85 / operating power of device

  * for laptop, approx operating power is 30W, giving 6.8 hours of runtime, plus laptop battery reserve
