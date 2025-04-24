******************
High Level Design
******************

The `Time Machine (TM) <https://timemachine.org/>`_ is a device used to time races. This device has a numeric keypad with an Enter button, and a printer. 
When a runner approaches the finish line, the operator uses the numeric keypad to enter their bib number, and when the runner crosses the finish line, 
the operator presses Enter to record their time. The position, bib number, and time are printed. If several runners approach the finish, the operator 
may not know the next who will cross so just hits Enter for each runner to record their times. The position and time are printed. 

The Time Machine has a wireless interface which is connected to a laptop via bluetooth. The same information which is displayed on the printer 
is sent over this interface.

`RaceDay Scoring <https://racedayscoring.blog/features/>`_ (RDS) is used on the laptop to connect bib numbers to participants, but doesn't have a direct 
interface to read the bluetooth connection.

Time Machine - CSV Connector (**tmtility**) reads the bluetooth connection and creates a file which RaceDay Scoring can ingest. 
It allows editing of result records to correct or add missing bib numbers.

RunSignUp (the vendor for RaceDay Scoring) had a program to do this function called TMKeyPad, but there were some issues which could not be resolved
so TMKeyPad was abandoned by the vendor.

.. note::
    While **tmtility** was designed for use with and tested with RaceDay Scoring, it it possible this can be used with other scoring software


Design
===============

There are several windows processes which are responsible for reading the serial
lines offered by the Time Machine, barcode scanner, and Trident reader. These
processes are responsible for reading data from external devices and posting the
data to a web backend. The web backend is responsible for writing the data to a
database, and provides the web server for the user interface.

The TM reader process is responsible for reading the Time Machine wireless
interface. When it sees a result it posts it to the web backend, which in turn
writes a row in the *result* table.

The barcode scanner reader process is responsible for reading the barcode
scanner interface. When it sees a scan it posts it to the web backend, which in
turn writes a row in the *scannedbib* table.

The Trident reader process is responsible for reading the Trident interface.
When it sees a read it posts it to the web backend, which in turn writes a row
in the *chipread* table. This process sets up a TCP connection to an IP
address rather than reading from a COM port, so it could have been done from the
Docker container. However, it seemed simplest to clone the behavior of the other
windows processes. 

A web frontend displays *results* table merged with the *scannedbib* table, and
"redraws" it periodically (nominally 1/sec). The web backend will pull data from
the database tables for the redraw. This picks up and displays new results and
scans.

The reader processes, web backend, and frontend are all on the same machine. The
web backend saves the data file to a directory on the machine used by RaceDay
Scoring.

The frontend has a way to manage the scanned bib numbers, i.e., to merge these
with the results from the Time Machine. There's also an edit capability using
datatables' editor functions, allowing edits, inserts, deletes, which causes the
backend to update the database appropriately. The operator can "confirm" the
results, which kicks off a file rewrite process which creates a temp file from
the database, renames the old file, renames the temp file to the expected name. 

There is locking between the reader process and the web backend to avoid the
race where the former is adding a row just at the wrong time. 

RDS maintains a pointer into the file to know where to look for new data, and is
signaled by the operating system when the file is appended to. The operator
causes new results to be sent to the file by "confirming" them. RDS then reads
the new data into as Time Machine raw reads.

..
   see https://www.graphviz.org/
   see http://graphs.grevian.org/
   see https://graphviz.org/doc/info/shapes.html#styles-for-nodes

.. graphviz::

   digraph records {
        graph [fontname = "helvetica"];
        node [fontname = "helvetica"];
        edge [fontname = "helvetica"];
        overlap = false;
        spline = true;

        tm [label="Time\nMachine", shape="parallelogram"];
        wtmrdr [label="TM reader (win)", shape="rectangle"];
        bs [label="BarCode\nScanner", shape="parallelogram"];
        wbsrdr [label="BS reader (win)", shape="rectangle"];
        chip [label="Trident", shape="parallelogram"];
        wchiprdr [label="Trident reader (win)", shape="rectangle"];

        rds [label="RaceDay\nScoring", shape="parallelogram"];

        subgraph cluster_0 {
            be [label="web backend", shape="rectangle"];
            dbres [label="result (db)", shape="oval"];
            dbscan [label="scannedbib (db)", shape="oval"];
            dbreads [label="chipread (db)", shape="oval"];
            label = "docker";
            color = "black";

            be -> dbres [label="lock,\nresult"];
            dbres -> be [label="results"];

            be -> dbscan [label="scan"];
            dbscan -> be [label="scans"];

            be -> dbreads [label="read"];
            dbreads -> be [label="reads"];
        }

        fe [label="browser", shape="rectangle"];

        file [label="csv file", shape="tab"];

        tm -> wtmrdr [label="result"];
        wtmrdr -> be [label="result"];
        be -> wtmrdr [label="control"];

        bs -> wbsrdr [label="scan"];
        wbsrdr -> be [label="scan"];
        be -> wbsrdr [label="control"];

        chip -> wchiprdr [label="reads"];
        wchiprdr -> be [label="reads"];
        be -> wchiprdr [label="control"];

        be -> file [label="result,\nunlock"];

        be -> file [label="lock,\nrewrite,\nunlock"];

        fe -> be [label="edit,\nnew,\ndelete"];
        be -> fe [label="results\nscans\nreads"];

        file -> rds;

        // { rank=same; tm, wtmrdr };
        // { rank=same; wbsrdr, bs };
        // { rank=same; wchiprdr, chip };

        {
            rank=same;
            edge[style=invis];
            file -> fe;
        }
    }


Other Notes
==========================

- The bulk of the application lives in a docker compose application, which
  reduces platform dependency to just docker. I.e., there are no requirements to
  install a database management system, web server, or python interpreter
- However, Windows docker does not allow access to serial ports from the docker
  container. For this reason the reader processes are native Windows and run
  outside of the container as a service. While these are python processes, the
  python interpreter is embedded in the exe files using the pyinstaller package.
