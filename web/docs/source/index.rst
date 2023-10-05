.. Time Machine - CSV Connector documentation master file, created by
   sphinx-quickstart on Sat Sep 23 17:38:42 2023.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to Time Machine - CSV Connector's Admin Guide
========================================================

.. toctree::
   :maxdepth: 2
   :caption: Contents:

Installation
****************

The Time Machine Reader app runs as a Windows service, while the web server
runs under Docker. 

Docker Installation
======================

See https://docs.docker.com/desktop/install/windows-install/
for installation of Docker before installing this application.

Install wsl. You may need to enable virtualization. See https://aka.ms/enablevirtualization for details.

.. code-block:: shell

    wsl --install

Follow instructions in https://docs.docker.com/get-docker/

* install Docker Desktop Installer (https://docs.docker.com/desktop/install/windows-install/)

  .. note::

    the application is a Linux container, so ignore all the stuff about windows containers on the webpage



Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
