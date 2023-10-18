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

One process (reader) reads the wireless interface data and when it sees a result writes a row in a database table, and appends a row to the 
file (open, append, close).

A web frontend displays a results table, and "redraws" it periodically (nominally 1/sec). The web backend will pull data from the database table 
for the redraw. This is to pick up new reads. It's possible to optimize this to only pick up new reads since the last redraw, but this doesn't
seem necessary to add this complexity.

The web backend and frontend is local on the machine used with RaceDay Scoring.

The frontend has an edit capability using datatables' editor functions, allowing edits, inserts, deletes, which causes the backend 
to update the database appropriately, then kicks off a file rewrite process which creates a temp file from the database, renames the old file, 
renames the temp file to the expected name. 

There is locking between the reader process and the web backend to avoid the race where the former is adding a row just at the wrong time. 

RDS maintains a pointer into the file to know where to look for new data, and is signaled by the operating system when the file is appended to. 
In order for RDS to pick up edits, the operator needs to do "stream replay" after any edits. This causes RDS to clear its "raw reads" from the 
stream, open, and read the file.

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
        rds [label="RaceDay\nScoring", shape="parallelogram"];
        wrdr [label="reader (windows)", shape="rectangle"];

        subgraph cluster_0 {
            be [label="web backend", shape="rectangle"];
            db [label="results table", shape="oval"];
            label = "docker";
            color = "black";

            be -> db [label="lock,\nresult"];
            db -> be [label="results"];

        }

        fe [label="browser", shape="rectangle"];

        file [label="csv file", shape="tab"];

        tm -> wrdr [label="result"];
        wrdr -> be [label="result"];
        be -> wrdr [label="control"];

        be -> file [label="result,\nunlock"];

        be -> file [label="lock,\nrewrite,\nunlock"];

        fe -> be [label="edit,\nnew,\ndelete"];
        be -> fe [label="results"];

        file -> rds;

        { rank=same; tm, wrdr };
        {
            rank=same;
            edge[style=invis];
            file -> fe;
        }
    }


Other Notes
==========================

- The bulk of the application lives in a docker compose application, which reduces platform dependency to just docker. I.e., there are no requirements 
  to install a database management system, web server, or python interpreter
- However, Windows docker does not allow access to serial ports from the docker container. For this reason the reader process is native Windows
  and runs outside of the container as a service. While this is a python process, the python interpreter is embedded in the exe file using
  the pyinstaller package.
