****************
Admin Guide
****************

.. |rds-streams| image:: /images/rds-ico-streams.png
   :height: 3ex
   :class: no-scaled-link

The Time Machine Reader app runs as a Windows service, while the web server
runs under Docker. 

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

.. warning:: LOTS TO BE ADDED HERE


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
