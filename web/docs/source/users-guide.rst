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

* On the laptop, in browser, navigate to `http://tm.localhost:8080/
  <http://tm.localhost:8080/>`_

  * create the Race using :ref:`Races view`, with date and start time configured
    the same as RaceDay Scoring
  * navigate to :ref:`Results view` for duration of the race
  * verify **Race** is set correctly
  
    .. note::
        after race, move csv file to a new race folder
  
  * verify **Port** is set correctly, then click **Connect**
  
    * LED on Time Machine wireless interface should change to steady green,
      **Connect** button display changes to **Disconnect**


If chip timing, synchronize actual start times
-------------------------------------------------

.. note::

    it's important this this is done soon after the race starts, and in any event 
    before any participant finishes

If chip timing is in use, the chip timing system will send time of day for each
result to RaceDay Scoring. For Time Machine backup results to work correctly,
it's important that the actual start time be synchronized between RDS and
**tmtility**.

The *actual start time* can be driven by a GPS watch, be based on a 'start'
timestamp from the chip system, or be determined by the first raw read time seen
at the start by the chip timing system.

* in RaceDay Scoring, under Scored Events |rds-scored-events|, update **Actual
  Start Time**
* in **tmtility**, under Races, update **Start Time** for this race

Time Machine Operation
----------------------------

Use of the Time Machine (TM) is identical to the technique used prior to use of
RaceDay Scoring data collection.

* Time Machine is turned on and configured with a new race number in Cross
  Country Mode (the default)
* initial time is set to 0:0:0 (the default)
* printer should be turned on
* when race starts

  * depress Start Time button

* when runner approaches the finish line, if it is clear this will be the next
  finisher

  * "select" the runner's bib number with the Time Machine keypad
  * as runner crosses the finish, depress ENTER button

* sometimes too many runners will cross the finish line at the same time, or it
  won't be clear which runner in a group will be first

  * as each runner finishes, depress ENTER button (i.e., there's no "select" of
    the bib number)


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
tag. After updating **tmtility** to match the pull tags, these results need to be
confirmed to send them to the csv file.

.. note:: 
    when editing rows, the grid display update is disabled. Deselect any selected 
    row to resume the display updates

To fix an incorrect/missing bib number (or time)

* click on the incorrect bib number (or time)
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

To confirm a set of results

* select the last result which is to be confirmed by clicking on the row (away
  from the bib number or time fields to avoid inline edit of these)
* click **Confirm**
* the confirmed rows will be displayed in green shortly thereafter

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
* results are not sent to RaceDay Scoring until they have been confirmed in
  **tmtility**, so if all the confirmed results are correct, there is no
  need for any additional action in RaceDay Scoring
* if any results which had been previously confirmed are subsequently edited in
  **tmtility**, the Time Machine stream needs to be replayed after removing any
  affected Raw Reads

  .. warning::

    the following is likely to change based on the outcome of
    `louking/tm-csv-connector#48 RaceDay Scoring showing old result after edit
    <https://github.com/louking/tm-csv-connector/issues/48>`_

  * if any bib numbers were removed (e.g., in the case of a mistyped bib number,
    the bib number that was incorrectly entered was removed) 
    
      * on the Dashboard |rds-home| view, click **RAW READS** 
      * on the Raw Reads view, under *Action* select the bib number(s) which
        were removed, then click **DELETE SELECTED READS** 
      * on the Dashboard |rds-home| view, under RAW READS, click **RECALC**,
        then click **RECALCULATE**

  * on the Streams |rds-streams| view, next to Time Machine click **REPLAY**
  * on the Scored Events |rds-scored-events| view, click **Save**
  * click Dashboard |rds-home| to get back to the race overview

  .. note::

    the result updates are recalculated in the background so be patient
  
Awards
--------------------

To see the awards, click Reports |rds-reports|

* the Age Group Report is probably the one you're interested in
* alternately, assuming internet connectivity, the results / awards can be seen
  on the RunSignUp race site under **Results**
