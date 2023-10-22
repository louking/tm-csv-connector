# tm-csv-connector
Time Machine - CSV Connector (**tmtility**) creates a CSV file from time machine input, for scoring software to read

The [Time Machine](https://timemachine.org/) (TM) is a device used to time
races. This has a numeric keypad with an Enter button, and a printer. When a
runner approaches the finish line, the operator uses the numeric keypad to enter
their bib number, and when the runner crosses the finish line, the operator
presses Enter to record their time. The position, bib number, and time are
printed. If several runners approach the finish, the operator may not know the
next who will cross so just hits Enter for each runner to record their times.
The position and time are printed. 

The Time Machine has a wireless interface which is connected to a laptop via
bluetooth. The same information which is displayed on the printer is sent over
this interface.

RaceDay Scoring (RDS) is used on the laptop to connect bib numbers to
participants, but doesn't have a direct interface to read the bluetooth
connection.

Time Machine - CSV Connector (**tmtility**) reads the bluetooth connection and
creates a file which RaceDay Scoring can ingest. It allows editing of result
records to correct or add missing bib numbers.

This may work for scoring software other than RDS, but is only tested with RDS.

Documentation can be found at https://tm-csv-connector.readthedocs.io/
