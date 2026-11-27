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

Software to Install
-----------------------

The **tmtility** laptop needs the following. Everything else (the device clients, the
web app, and its database) comes in the app's zip files or runs under Docker. If you're
replacing an existing **tmtility** laptop, see `Moving to a New Laptop`_ first.

* turn off **Smart App Control**: in **Windows Security**, go to **App & browser control** >
  **Smart App Control settings** and select **Off**. Windows 11 turns it on by itself on a new
  laptop, and it blocks the app's device clients, which aren't code-signed: the TM reader and
  chip reader services stay stopped, and Windows shows "part of this app has been blocked".
  Microsoft Defender Antivirus stays on.

* edit ``C:\Windows\System32\Drivers\etc\hosts`` (as Administrator) and add the line
  ``127.0.0.1 tm.localhost``. The browser sees it only after a restart, so do this first;
  the restart that installing WSL needs covers it.

* **WSL** (Windows Subsystem for Linux), which Docker Desktop needs. In PowerShell
  **Run as Administrator**:

  .. code-block:: shell

      wsl --install

  You may need to enable virtualization in the BIOS. See https://aka.ms/enablevirtualization
  for details.

* **Docker Desktop**, from https://docs.docker.com/desktop/install/windows-install/

  .. note::

    the application uses Linux containers, so ignore the instructions about Windows containers

  Docker Desktop doesn't have to start when you sign in to Windows. If it doesn't, start it
  before using **tmtility** (see :ref:`users-guide-tm-connection`); the app starts with it.

* **Syncthing**, to copy the output file to the RaceDay Scoring laptop. See
  :ref:`sync results to rds`.

* **Google Chrome**, the recommended browser for **tmtility**

* set the laptop's clock to sync with internet time servers (see `Setting the Laptop Clock`_)

Then install the app (see `App Installation`_) and pair the Bluetooth devices (see
`Bluetooth Pairing`_).


App Installation
---------------------
* download both of the following files (``tm-csv-connector-js.zip`` contains vendor JavaScript
  and is required for a fresh install; it rarely changes after that):

  * https://github.com/louking/tm-csv-connector/blob/main/dist/tm-csv-connector.zip
  * https://github.com/louking/tm-csv-connector/blob/main/dist/tm-csv-connector-js.zip

  .. note:: your browser may want to scan each file for malware/virus. let it

* extract files from ``tm-csv-connector.zip`` into the directory you want the app to run from
* place ``tm-csv-connector-js.zip`` (do not extract it) into that same directory — the install
  procedure will extract it automatically
* start powershell **Run as Administrator**, and navigate to this directory

    .. note:: you'll have to accept the User Account Control challenge, which may be seen elsewhere on the taskbar

* before you execute these commands for the first time, you'll need to do the following

  * make sure the ``hosts`` file has ``tm.localhost`` (see `Software to Install`_)
  * allow PowerShell scripts to run

    .. code-block:: shell

      Set-ExecutionPolicy Bypass CurrentUser # type y to accept

    for details see https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.security/set-executionpolicy

  * log in to Docker

    .. code-block:: shell

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
  * enter the host path for rsync source (local directory that contains leaderboard html files to sync)
  * enter rsync destination host, user, and path (for optional leaderboard sync to a web server; press Enter to skip if not using this feature)
  * enter passwords for root and app database users -- accepting the defaults are fine

  .. note:: you can see the values of these later by navigating to ``config/db`` in the installation directory

* the first time it's run, it takes a bit of time for the app to create the database, etc
* with Chrome, navigate to http://tm.localhost:8080/
* if you're moving from another **tmtility** laptop, stop here and go back to
  `Moving to a New Laptop`_. The settings, races and Bluetooth devices come from the old
  laptop's database.
* open the Settings view at http://tm.localhost:8080/settings (it isn't on the menu; this only has to be done once)

  * add New setting, Setting=output-file, Value=tm-data.csv # or whatever filename you want the output put in

* set up Syncthing to share the output directory with the RaceDay Scoring laptop (see
  :ref:`sync results to rds`)


Bluetooth Pairing
-----------------------------

Before using the app, the Time Machine wireless interface or barcode scanner
needs to be connected to the laptop's bluetooth. These instructions are for
Windows 11. If you're using a USB Bluetooth adapter, set it up first (see
`Using a USB Bluetooth Adapter`_).

For the Time Machine connection, make sure the Time Machine has the Wireless
Interface connected, and is powered on. The Wireless Interface LED should be
blinking red.

For a barcode scanner, make sure the scanner is powered on and in SPP mode. The
scanner should be in pairing mode. See the scanner's user's manual for details.

In the taskbar's search bar, search for bluetooth. Click on **Bluetooth and other
devices settings**. Set **Bluetooth devices discovery** to Advanced, then click
**Add Device**. 

.. figure:: images/win11-bluetooth-settings.*
    :align: center

|

Then click **Bluetooth**

.. figure:: images/win11-add-device.*
    :align: center

|

Select the device you're trying to pair with. In this case it's a barcode scanner **BarCode Scanner spp**. Make note of the name used for this connection as it will be needed when
configuring the :ref:`Bluetooth Devices view`.

.. figure:: images/win11-add-device-select-scanner.*
    :align: center

|

Click **Connect**

Windows gives each device paired in SPP mode two serial ports, an outgoing and an incoming one;
the app finds and uses the outgoing one. To check them, in Device Manager (Windows-x > Device
Manager) expand **Ports (COM & LPT)**: each device adds two entries named **Standard Serial
over Bluetooth link (COMn)**. The names don't say which device each port is for. If a device
is missing from its port list on the results page, check here first: a device that isn't in
SPP mode (e.g., a scanner in HID or BLE mode) still pairs, but gets no ports.

Now you need to determine the device's Bluetooth Hardware address. 

* bring up the Windows Device Manager (Windows-x > Device Manager)
* expand the **Bluetooth** section


.. figure:: images/win11-device-manager-view.*    
    :align: center

|

.. figure:: images/win11-device-manager-bluetooth.*
    :align: center  

|

* right-click on the device you just connected, and select **Properties** > **Details**
* select **Bluetooth device address** from the **Property** dropdown

.. figure:: images/win11-device-manager-bluetooth-properties-1.*
    :align: center

|

* copy the value of the **Value** field. This is the Bluetooth Hardware address
  for the device, and will be used in the :ref:`Bluetooth Devices view`

.. figure:: images/win11-device-manager-bluetooth-properties-2.*
    :align: center

|

* create the device using :ref:`Bluetooth Devices view`. The **Name** field
  should be a suitable name of the device you just connected (label the device
  with this), and the **Type** field should be set to the type of device you
  just connected. The **HW Addr** field should be set to the Bluetooth Hardware
  address you just copied.


Using a USB Bluetooth Adapter
-----------------------------
A USB Bluetooth adapter with an external antenna, on a USB extension cable, can reach the
Time Machine and scanner farther than the laptop's internal Bluetooth. Windows uses only one
Bluetooth radio at a time, and with both on, you can't control which one it uses. So turn the
internal Bluetooth off, and pair the devices after that: a device paired on one radio has to be
paired again on the other.

Turn the internal Bluetooth off in the BIOS. Turning it off in Device Manager also works, but a
driver or Windows update can turn it back on, which the BIOS setting is safe from. Wi-Fi isn't
affected, even though it's often on the same card as the internal Bluetooth.

On a Dell laptop (menu names vary a little by model):

#. restart the laptop, and press **F2** repeatedly as soon as the Dell logo appears, to open
   BIOS Setup. If Windows starts instead, restart and try again. **F12** opens a one-time boot
   menu, which also has **BIOS Setup**.
#. go to **Connection** (on some models, **Wireless**), then **Wireless Device Enable**
#. clear the **Bluetooth** check box, and leave **WLAN** (Wi-Fi) checked
#. select **Apply Changes**, then **Exit**. The laptop restarts into Windows.

On other laptops, look for a Bluetooth or wireless setting in the BIOS's connection,
wireless or onboard device settings.

Then:

* plug in the adapter. Install its driver if its instructions say to.
* in Device Manager (Windows-x > Device Manager), expand **Bluetooth** and check that the
  adapter is listed (e.g., **TP-Link Bluetooth USB Adapter**), with nothing from the internal
  radio (often named Intel Wireless Bluetooth). Entries named **Microsoft Bluetooth
  Enumerator**, **Microsoft Bluetooth LE Enumerator** and **Bluetooth Device (RFCOMM Protocol
  TDI)** are part of Windows and are always there. A model whose BIOS has no Bluetooth setting
  can turn the internal one off here instead: right-click it and choose **Disable device**.
* pair the Time Machine and scanners (see `Bluetooth Pairing`_). Their COM ports will change,
  but their hardware addresses don't, so devices already in the :ref:`Bluetooth Devices view`
  don't need changing.
* on the results page, check that each device's port shows in its port list, and that each
  connects

.. note::
    Keep the adapter with the laptop. With the internal Bluetooth off, the laptop has no
    Bluetooth without the adapter. To go back to the internal Bluetooth, check **Bluetooth**
    in the BIOS again and pair the devices again.

Setting the Laptop Clock
-------------------------
The device clients stamp each result and scan with the laptop's clock (see the
:ref:`Results Log view`), and the client logs use it too. The chip reader stamps its reads
with its own clock, which it sets from GPS. If the laptop's clock is off, its times won't
line up with the chip reads. Windows syncs its clock only about once a week by default, and
its time server setting can be wrong: two of our race-day laptops were found about 40 and
16 seconds off.

To check the clock, open https://time.is in Chrome. It shows how far ahead or behind the
laptop's clock is.

To set the laptop to sync with several internet time servers, open Command Prompt with
**Run as administrator** (these commands don't work as written in PowerShell) and run:

.. code-block:: shell

    w32tm /config /manualpeerlist:"time.nist.gov,0x8 us.pool.ntp.org,0x8 time.cloudflare.com,0x8" /syncfromflags:manual /update
    sc config w32time start= auto
    net stop w32time
    net start w32time
    w32tm /resync /rediscover

``sc config`` makes the Windows Time service start with Windows. If ``w32tm /resync`` says
"no time data was available", the service hasn't reached the servers yet: wait a minute and
run it again. Then check that it worked:

.. code-block:: shell

    w32tm /query /source
    w32tm /query /peers

``/query /source`` should name one of the servers, not **Local CMOS Clock** or
**Free-running System Clock**, which mean the laptop isn't syncing. ``/query /peers`` lists
each server's state; one still pending is fine. Check https://time.is again: the clock
should now be within a fraction of a second.

Syncing needs an internet connection. The race network normally has one, through its
cellular hotspot, so the laptop keeps syncing at the race. Where there's no cellular
signal, check the clock at home before race day.


App Upgrade
-------------
* download https://github.com/louking/tm-csv-connector/blob/main/dist/tm-csv-connector.zip

    .. note:: your browser may want to scan the file for malware/virus. let it

* vendor JavaScript (``tm-csv-connector-js.zip``) rarely changes between releases; only download
  it if the release notes mention updated vendor JavaScript:
  https://github.com/louking/tm-csv-connector/blob/main/dist/tm-csv-connector-js.zip
  If you do download it, place it (do not extract it) in the install directory — ``./install``
  will extract it automatically

* start powershell **Run as Administrator**, and navigate to the install directory

    .. note:: you'll have to accept the User Account Control challenge, which may be seen elsewhere on the taskbar

* disable the app

    .. code-block:: shell

        ./disable-all

* if you have manually edited ``.env`` since the last install, run the following first to
  save those values so they survive the upgrade

    .. code-block:: shell

        ./edit-env

  press Enter at each prompt to accept the current values

* extract files from ``tm-csv-connector.zip`` to the install directory
* if you downloaded ``tm-csv-connector-js.zip``, place it (do not extract it) in the install
  directory — the install procedure will extract it automatically

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


Backup and Restore
---------------------
The database holds the races, results, scanned bibs, chip reads, results log, settings and
Bluetooth devices. It lives in a Docker volume, not in the install directory, so copying the
install directory doesn't copy it. Use these steps to back it up, e.g., before an upgrade, or to
move it to another laptop.

Run the commands in PowerShell, in the install directory, with Docker Desktop running and the app
enabled. Don't back up during a race.

* back up the database to ``tmtility-backup.sql`` in the install directory

    .. code-block:: shell

        docker compose exec db sh -c 'MYSQL_PWD=$(cat /run/secrets/db-password) mysqldump -uroot --single-transaction --databases tm-csv-connector > /tmp/tmtility-backup.sql'
        docker compose cp db:/tmp/tmtility-backup.sql ./tmtility-backup.sql

* to restore, put ``tmtility-backup.sql`` in the install directory and run the following. This
  replaces the database's tables with the backup's. The backup must come from the same release
  of **tmtility** as the install you restore it to.

    .. code-block:: shell

        docker compose cp ./tmtility-backup.sql db:/tmp/tmtility-backup.sql
        docker compose exec db sh -c 'MYSQL_PWD=$(cat /run/secrets/db-password) mysql -uroot tm-csv-connector < /tmp/tmtility-backup.sql'
        docker compose restart app


Moving to a New Laptop
-------------------------
To replace the **tmtility** laptop, set up the new laptop on its own first, then move the
database and switch the RaceDay Scoring sync over. Only the middle steps need both laptops,
and none of them needs the Time Machine, scanner or chip reader.

On the new laptop, before you need the old one:

#. install the software in `Software to Install`_
#. install the app as in `App Installation`_, up to the step that says to come back here. Use
   the same release that's on the old laptop; if the old laptop is behind, upgrade it first
   (see `App Upgrade`_), so its backup matches.
#. if you're adding a USB Bluetooth adapter, set it up now, before pairing anything (see
   `Using a USB Bluetooth Adapter`_)
#. pair the Time Machine and barcode scanners with Windows (see `Bluetooth Pairing`_). You
   don't need to add them in the :ref:`Bluetooth Devices view`; they come with the database,
   and the app finds their COM ports by their hardware addresses, which don't change.

With both laptops on the same network:

#. in Syncthing, connect the two laptops, and share a new folder (e.g., ``C:\tmtility-transfer``)
   from the old laptop as **Send Only** to the new laptop as **Receive Only**. A USB stick
   works too.
#. on the old laptop, `back up <Backup and Restore_>`_ the database and copy
   ``tmtility-backup.sql`` into that folder. You can also copy the old laptop's logging
   directory there to keep past races' client logs.
#. on the new laptop, copy ``tmtility-backup.sql`` from the folder into the install directory
   and `restore <Backup and Restore_>`_ it
#. open http://tm.localhost:8080/ on the new laptop, and check that the races, the Settings view at http://tm.localhost:8080/settings
   (including **output-file**) and the :ref:`Bluetooth Devices view` came across. On the results
   page, check that each device's port shows in its port list, and that each connects.
#. on the old laptop, disable the app, so that it can't write the output file

    .. code-block:: shell

        ./disable-all

#. switch the RaceDay Scoring sync to the new laptop (see :ref:`sync results to rds`). On the
   new laptop, add the output directory with the same **Folder ID** that the old laptop used,
   and share it with the RaceDay Scoring laptop. On the RaceDay Scoring laptop, share that
   folder with the new laptop, and stop sharing it with the old one. RaceDay Scoring's
   **Folder Path** stays the same.
#. remove the transfer folder from Syncthing on both laptops

.. _sync results to rds:

Syncing Results to RaceDay Scoring
====================================
The output CSV file (see **output-file** in :ref:`Settings view`) is written by
**tmtility** on the timing laptop, and must be readable by RaceDay Scoring,
which normally runs on a separate laptop. If RaceDay Scoring reads the file over
a network share (e.g. ``\\host\share``), it loses access to the file -- and the
read connector requires a restart -- whenever the venue network drops, even
briefly (see `issue #144
<https://github.com/louking/tm-csv-connector/issues/144>`_).

`Syncthing <https://syncthing.net/>`_ avoids this: it's a free, open-source, peer-to-peer
file sync tool with no cloud/internet dependency, so it keeps working over the local network
alone even if the venue has no internet access.

Install Syncthing on both laptops, then share the ``OUTPUT_DIR`` folder used by
**tmtility** (see :ref:`Settings view`) between them:

* on the **tmtility** laptop, add the folder and set its type to **Send Only**
* on the **RaceDay Scoring** laptop, accept the shared folder and set its type to
  **Receive Only**
* point RaceDay Scoring's **Folder Path** (below) at the local Syncthing-synced copy of
  the folder on the RDS laptop, instead of a network share path

Recommended settings, beyond the folder types above:

    :Watch for Changes:
        on, for the folder on the **tmtility** laptop -- this triggers a sync as soon as
        the CSV file changes, instead of waiting for the periodic rescan

    :Rescan Interval:
        30-60 seconds for the folder on the **tmtility** laptop, as a fallback in case the
        filesystem watcher misses a change (the default of 3600s is too slow for results
        that update throughout a race)

    :Local Discovery:
        on (default) -- lets the two laptops find each other on the venue's LAN
        automatically, even though both get their IP address via DHCP, so there's no need
        to configure a static IP for either laptop

    :Global Discovery / Relaying:
        off, under **Actions > Settings > Connections** -- these features rely on
        Syncthing's internet-based servers, which aren't needed (and may not be reachable)
        at a race venue; turning them off also keeps sync traffic strictly local

    :Versioning:
        not needed -- the Send Only / Receive Only folder types already prevent RaceDay
        Scoring from overwriting the source file

.. note::
    Both laptops must be on the same local network (same venue WiFi, hotspot, or switch)
    for Local Discovery to find each other.

.. _set up RDS:

Set up RaceDay Scoring
======================
* at Streams |rds-streams| panel, create a stream for Time Machine

  * Stream Name: Time Machine
  * Stream Type: File (Custom or Chip System Type)
  * File Type: File (Custom or Chip System Type)
  * Folder Path: MAIN-FOLDER-PATH, the local path on the RDS laptop for the Syncthing-synced
    folder described in `Syncing Results to RaceDay Scoring`_
  * File Extension: csv
  * Passing Format: [IGNORE],[BIBCODE],[TIME]
  * Field Delimiter: ,
  * Assign as a Backup Stream for these Timing Locations: Finish


Bluetooth devices
========================
Bluetooth devices are used to connect the Time Machine and Barcode Scanner to
the laptop. The Bluetooth device must be set to SPP mode, paired with the
laptop, and configured in :ref:`Bluetooth Devices view` before starting the app.

To configure a bluetooth device, 

* set the device into pairing mode (see the device's user's manual)
* use the laptop's bluetooth settings to pair the device with the laptop

.. figure:: images/win11-bluetooth-settings.*
    :align: center



Bib Barcode Scanner
=========================

A bib barcode scanner can be used to automatically serialize bibs which cross
the finish line, similar to the use of pull tags and a spindle. **tmtility** was
tested with Tera Model H00002 and inatech BCST-72 scanners. The requirement is that the scanner
connect via a USB port, and send the bib numbers followed by one or more CR (\\r) or LF (\\n) 
characters.

The scanner needs to be set to use SPP mode after a factory reset. See the scanner user's 
manual for details. The scanner should be paired with the laptop before starting.



Jackery Working Time
======================
* Jackery Portable Power Station 240 uses 241Wh * 0.85 / operating power of
  device

  * for Dell Inspiron 15 3520 laptop, max operating power is 45W, so Jackery
    gives 4.5 hours of full-throttle runtime, plus laptop battery reserve
