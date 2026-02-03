.. Time Machine - CSV Connector documentation master file, created by
   sphinx-quickstart on Sat Sep 23 17:38:42 2023.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

#########################################################
Time Machine - CSV Connector (**tmtility**)
#########################################################

Time Machine - CSV Connector (**tmtility**) - creates CSV file from time machine input, for
scoring software to read

The `Time Machine (TM) <https://timemachine.org/>`_ is a device used to time races. This device has a numeric keypad with an Enter button, and a printer. 
When a runner approaches the finish line, the operator uses the numeric keypad to enter their bib number, and when the runner crosses the finish line, 
the operator presses Enter to record their time. The position, bib number, and time are printed. If several runners approach the finish, the operator 
may not know the next who will cross so just hits Enter for each runner to record their times. The position and time are printed. 

The Time Machine has a wireless interface which is connected to a laptop via bluetooth. The same information which is displayed on the printer 
is sent over this interface.

`RaceDay Scoring <https://racedayscoring.blog/features/>`_ (RDS) is used on the laptop to connect bib numbers to participants, but doesn't have a direct 
interface to read the bluetooth connection.

**tmtility** reads the bluetooth connection and creates a file which RaceDay Scoring can ingest. 
It allows editing of result records to correct or add missing bib numbers.

Source can be found at https://github.com/louking/tm-csv-connector

.. toctree::
   :maxdepth: 4
   :caption: Contents:

.. toctree::
    :maxdepth: 3

    standard
    simulator
    design
    background
    development
    typographical-conventions

*******************
Indices and tables
*******************

* :ref:`genindex`
* :ref:`search`
