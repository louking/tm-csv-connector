****************
User's Guide
****************
.. |rds-age-groups| image:: /images/rds-ico-age-groups.png
   :height: 3ex
   :class: no-scaled-link

.. |rds-home| image:: /images/rds-ico-home.png
   :height: 3ex
   :class: no-scaled-link

.. |rds-locations| image:: /images/rds-ico-locations.png
   :height: 3ex
   :class: no-scaled-link

.. |rds-main| image:: /images/rds-ico-main.png
   :height: 3ex
   :class: no-scaled-link

.. |rds-participants| image:: /images/rds-ico-participants.png
   :height: 3ex
   :class: no-scaled-link

.. |rds-reads| image:: /images/rds-ico-reads.png
   :height: 3ex
   :class: no-scaled-link

.. |rds-reports| image:: /images/rds-ico-reports.png
   :height: 3ex
   :class: no-scaled-link

.. |rds-scored-events| image:: /images/rds-ico-scored-events.png
   :height: 3ex
   :class: no-scaled-link

.. |rds-streams| image:: /images/rds-ico-streams.png
   :height: 3ex
   :class: no-scaled-link

Before Race
==================

Set Up Race in RunSignUp
-------------------------------------

* in the Race Wizard page 1 (Basic Info) set Timers to **FSRC Race Support Services**

Set Up Race in RaceDay Scoring
-------------------------------------

* click |rds-main| to the left of **Select a Race**
  
  * click **MANAGE RACES**
  * if race is already in the list, and listed as Upcoming
  
    * click the race to see the race dashboard
  
  * if race is already in the list, and listed as Passed
  
    * click **RENEW**
    * click the race to see the race dashboard
  
  * else if race is not on the list
    
    * click **IMPORT A RACE ALREADY ON RUNSIGNUP**
    * select the race date filter, click **SEARCH**
    * click the race you want to import
    * you'll be shown the race dashboard

.. Padding. See https://github.com/sphinx-doc/sphinx/issues/2258

* at the race dashboard, configure or verify the following
  
  * click Participants/Teams |rds-participants|
  
    * click **SET UP PARTICIPANT/GROUP SYNC**
    * click **SAVE SYNC SETTINGS** (i.e., use defaults)
  
  * click Scored Events |rds-scored-events|
  
    * click Quick Setup
    * set Start Time Location: Not a timed start
    * verify Actual Start Time is set to the race start time
    * click **Save**
  
  * click Streams |rds-streams|
  
    * make sure "Time Machine" is under Assigned Streams (see :ref:`set up RDS`)
    
      * Open Time Machine stream
      * Assign location to Finish (backup stream)
      * File extension csv
      * click **Save**
  
  * click Age Groups/Team Classifications |rds-age-groups| to set up divisions
  
    * click **SET TOP FINISHERS** to set up overall finishers by gender
    
      * Description: Overall
      * How Many Overall xxx: set to desired number for each gender
    
    * click **RANGE INSERT** to set up age groups
    * click **SAVE**

  .. Padding. See https://github.com/sphinx-doc/sphinx/issues/2258

  * click timing locations |rds-locations| to set times

    * delete Start location
    * click Finish **SETTINGS**
  
      * set Consider Finish/Split Finish Times after (earliest expected Finish/Split Time): 12:00:00.00 AM race day
      * click **SAVE**

  .. Padding. See https://github.com/sphinx-doc/sphinx/issues/2258

  * click reports |rds-reports| to set up autosave

    * click **AUTO-SAVE SETTINGS**
    * click **+** under RunSignup Results
    * under Advanced Options
    
      * set Chip Time: [blank]
      * set Custom Field: Gender Place: *Send as Whole Number*

    * click **ADD STREAM**
    * click **SAVE SETTINGS**

Race Day
====================

RaceDay Scoring Setup
---------------------------

* On the laptop, start RaceDay Scoring

  * log into your RunSignUp account, if necessary
  
    * you need to know your password
    * your account must previously have been set up as a "secondary owner" of the FSRC Race Support Services "timing company" under RunSignUp
  
  * if you're at the main dashboard |rds-main|
  
    * click **MANAGE RACES**
    * select the race

  * RaceDay Scoring should be active, connected to read from **tmtility**'s configured output file

Time Machine and **tmtility** Connection
------------------------------------------------

* turn on Time Machine

  * set up as normal (Event#)
  * LED on wireless interface should be blinking red

* On the laptop, in browser, navigate to `http://tm.localhost:8080/ <http://tm.localhost:8080/>`_

  * create the Race using :ref:`Races view`, with date and start time configured the same as RaceDay Scoring
  * navigate to :ref:`Results view` for duration of the race
  * verify **Race** is set correctly
  
    .. note::
        after race, move csv file to a new race folder
  
  * verify **Port** is set correctly, then click **Connect**
  
    * LED on Time Machine wireless interface should change to steady green, **Connect** button display changes to **Disconnect**


Time Machine Operation
----------------------------

Use of the Time Machine (TM) is identical to the technique used prior to use of RaceDay Scoring data collection.

* Time Machine is turned on and configured with a new race number in Cross Country Mode (the default)
* initial time is set to 0:0:0 (the default)
* printer should turned on
* when race starts

  * depress Start Time button

* when runner approaches the finish line, if it is clear this will be the next finisher

  * "select" the runner's bib number with the Time Machine keypad
  * as runner crosses the finish, depress ENTER button

* sometimes too many runners will cross the finish line, or it won't be clear which runner in a group will be first

  * as each runner finishes, depress ENTER button (i.e., there's no "select" of the bib number)


.. _tmtility operation:

**tmtility** Operation
--------------------------

**tmtility** displays a grid with TM Pos, Bib No, Time, similar to the Time
Machine printer tape. In addition, the currently computed Place is displayed.
**tmtility** allows the Bib No and Time to be edited, which can't be done on the
Time Machine itself. Normally the Time should not be edited, but the Bib No can
be edited for the following cases

* no bib number was selected
* wrong bib number was selected

In the case the Time Machine operator depressed ENTER too many times, an extra
row will appear in the grid. In the case the TM operator missed a runner, a row
will be missing in the grid.

All of these cases can be corrected in **tmtility**.

The pull tag spindles should be collected periodically from the finish line. The
pull tags should be reviewed to verify there is a row in the grid for each pull
tag.

.. note:: 
    when editing rows, the grid display update is disabled. Deselect any selected 
    row to resume the display updates

To fix an incorrect/missing bib number (or time)

* doubleclick on the incorrect bib number (or time)
* to accept the edit, press ENTER on the keyboard or click away from the field
* make sure the row is deselected to allow results display to resume (e.g.,
  click on the row to deselect if highlighted)

To fix an extra finish result

* click on the row with the extra result (row will be highlighted)
* click **Delete** and accept the popup challenge

To add a missing result

* click **New**
* enter Bib No and Time for the missing result (leave TM Pos blank)
* click **Create**

RaceDay Scoring Operation
-----------------------------

monitor Time Machine reads
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

* click **Reads** |rds-reads|
* click **YES, START THE CONNECTOR**
* light by **Reads** should turn green

problems must be fixed in **tmtility**
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

* see :ref:`tmtility operation` to fix bib number or time problems
* once several problems have been fixed, the Time Machine stream need to be
  replayed after clearing Raw Reads

  * on the Dashboard |rds-home| view, under RAW READS, click **CLEAR**, then
    click **DELETE**
  * on the Streams |rds-streams| view, next to Time Machine click **REPLAY**
  * click Dashboard |rds-home| to get back to the race overview
  
* the reads get recalculated in the background, so it might take just a
  little while

Awards
--------------------

To see the awards, click Reports |rds-reports|

* the Age Group Report is probably the one you're interested in
* alternately, assuming internet connectivity, the results / awards can be seen on the RunSignUp race registration site
