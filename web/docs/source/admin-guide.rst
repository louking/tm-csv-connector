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

    .. note:: your browser may want to scan the file for malware/virus. let it
    
* extract files from the downloaded file you want the app to run from
* navigate to this directory
* start powershell **Run as Administrator**, and navigate to this directory

    .. note:: you'll have to accept the User Account Control challenge, which may be seen elsewhere on the taskbar

* before you execute these commands for the first time, you'll need to do the following

  .. code-block:: shell

    edit `c:\Windows\System32\Drivers\etc\hosts`, add 127.0.0.1 tm.localhost
    Set-ExecutionPolicy Bypass [<ExecutionPolicyScope>] # type y to accept
    # for details see https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.security/set-executionpolicy 
    docker login # then enter your credentials

* run the install procedure

    .. code-block:: shell

        ./install

  * if you see something similar to the following, type *a* for Yes to All

      .. code-block:: shell

          The package(s) come(s) from a package source that is not marked as trusted.
          Are you sure you want to install software from
          'https://onegetcdn.azureedge.net/providers/nuget-2.8.5.208.package.swidtag'?
          [Y] Yes  [A] Yes to All  [N] No  [L] No to All  [S] Suspend  [?] Help (default is "N"):

  * enter directory names for the output csv file, and for the logging files (full path)
  * enter passwords for root and app database users -- accepting the defaults are fine

  .. note:: you can see the values of these later by navigating to config/db in the installation directory

* the first time it's run, it takes a bit of time for the app to create the database, etc
* with your browser, navigate to http://tm.localhost:8080/ 
* navigate to Settings view (this only has to be done once)

  * add New setting, Setting=output-file, Value=tm-data.dsv # or whatever filename you want the output put in


App Upgrade
-------------
* download https://github.com/louking/tm-csv-connector/blob/main/dist/tm-csv-connector.zip

    .. note:: your browser may want to scan the file for malware/virus. let it

* start powershell **Run as Administrator**, and navigate to the install directory

    .. note:: you'll have to accept the User Account Control challenge, which may be seen elsewhere on the taskbar

* disable the app

    .. code-block:: shell

        ./disable-all

* extract files from the downloaded file to the install directory

* run the install procedure

    .. code-block:: shell

        ./install

  if you see the error

    .. code-block:: shell

        ./install : File <...>\install.ps1 cannot be loaded. The file <...>\install.ps1 is not digitally signed. You cannot run this script on the current system. 
        For more information about running scripts and setting execution policy, see about_Execution_Policies at https:/go.microsoft.com/fwlink/?LinkID=135170.
        At line:1 char:1
        + ./install
        + ~~~~~~~~~
            + CategoryInfo          : SecurityError: (:) [], PSSecurityException
            + FullyQualifiedErrorId : UnauthorizedAccess

  enter the following 

    .. code-block:: shell

        Set-ExecutionPolicy Bypass CurrentUser # type y to accept
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


Bib Barcode Scanner
=========================

A bib barcode scanner can be used to automatically serialize bibs which cross
the finish line, similar to the use of pull tags and a spindle. **tmtility** was
tested with Tera Model D5100 Wireless 2D Barcode Scanner
(https://www.amazon.com/dp/B07M68LS2N). The requirement is that the scanner
connect via a USB port, and send the bib numbers followed by one or more CR (\\r)
characters.

The scanner needs to be set to use USB-COM mode after a factory reset. This
needs to be done once, but the barcode commands are here just in case of a
problem.

.. figure:: images/scanner-factory-default.*
    :align: center

|

.. figure:: images/scanner-usb-com.*
    :align: center

|

If there is any issue pairing with the scanner, this barcode can be used to put
the scanner into pairing mode. Again this shouldn't be needed as the scanner
should already be paired with the dongle attached to it.

.. figure:: images/scanner-pairing.*
    :align: center

|


Jackery Working Time
======================
* Jackery Portable Power Station 240 uses 241Wh * 0.85 / operating power of
  device

  * for Dell Inspiron 15 3520 laptop, max operating power is 45W, so Jackery
    gives 4.5 hours of full-throttle runtime, plus laptop battery reserve
