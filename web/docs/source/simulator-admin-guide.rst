******************************
Admin Guide (Simulator Mode)
******************************

The administrator configures and manages the simulations supported by
**tmtility** when in simulator mode. The administrator can create new
simulations, define the events to be simulated and their expected results, and
manage the simulation runs and results.

Each simulation scenario must be defined before it can be worked with. This is
done using :ref:`simulations view`.

Once a simulation is defined, the events to be simulated must be created. This
is done using :ref:`simulation events view`. In general, the events are created
by importing a csv file which contains the event definitions. To reproduce a
specific race situation, the log file which was created by **tmtility** during
a race can be used as the source for the event definitions.

In order to evaluate the user's performance of a simulation run, the expected
results must be defined. This is done using :ref:`simulation expected results
view`. The expected results are generally created by importing a csv file which
contains the expected result definitions.

Once the simulations are defined, the events created, and the expected results
defined, the simulations can be run by a user using :ref:`[Simulation] results
view`.

The administrator can view the simulation runs and their results using
:ref:`simulation run view` and :ref:`simulation run results view`

