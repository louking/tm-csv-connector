****************
Admin Reference
****************

This document has the reference for all of the views supported by **tmtility**. Each view has the name of the view, navigation buttons,
and the release version at the top of the view. **Admin Guide** can be clicked to see the top level of this documentation.

.. figure:: images/view-heading.*
    :align: center

    View heading


.. _Races view:

Races view
======================
Results are collected by race. The Races view is used to configure the races in the system.

    :Date:
        date of race in ISO format (yyyy-mm-dd)
    
    :Name:
        name of race

.. figure:: images/races-view.*
    :align: center

    Races view

.. figure:: images/races-new.*
    :align: center

    Create new race (click New)


.. _Results view:

Results view
======================
The Results view is used to see the results for a particular Race as they come
in from the Time Machine, and to adjust them as needed. 

    :Place:
        current place of this result after edits, insertions, deletions
    
    :TM Pos:
        position (place) as known by the time machine. This can be compared
        against the paper tape

    :Bib No:
        bib number

    :Time:
        result time

The view has the following controls:

    :Connect / Disconnect:
        the button on the left of the controls is used to connect or disconnect
        from the time machine. If the button says "placeholder" for more than a
        second or two, there's a problem communicating with the reader service
    
    :Race:
        choose the race previously defined at :ref:`Races view`
    
    :Port:
        the COM port which has been set up to communicate with the Time Machine.
        See `Wireless Computer Interface User's Guide
        <https://timemachine.org/tmwci_user_s_guide.pdf>`_ for information on
        how to set up the communication.

To select a row, click on the row. Note when any row is selected, updates to the
display are suspended and a warning is displayed. The row must be deselected by
clicking on it again to resume results display. Edits to Bib No and Time can be
done inline by clicking on the field to be updated. Clicking off the field after
update, or hitting return submits the edit to the database.

Confirmed results have been sent to RaceDay Scoring via the csv file. The
confirmed results are shown in green. To confirm a set of results, click on the
last result to be confirmed (i.e., with the highest *Place* number), then click
the **Confirm** button.

.. figure:: images/results-view.*
    :align: center

    Results view

.. figure:: images/results-view-scanner.*
    :align: center

    Results view with Barcode Scanner Connected

.. figure:: images/results-edit-inline.*
    :align: center

    Inline edit (click on field)

.. figure:: images/results-new.*
    :align: center

    Create new result (click New)

.. figure:: images/results-edit-modal.*
    :align: center

    Full result edit (select row, click Edit)

If a bib barcode scanner is connected, the Scanned Bib No and ≠ columns are shown.


.. _Settings view:

Settings view
======================
The Settings view is used to update individual settings required by the system.

    :Setting:
        the setting to be edited
    
    :Value:
        value of the setting

Defined Settings

    :output-file:
        the name of the csv file used to save result data. This is stored in the OUTPUT_DIR defined at installation or modified
        within the .env file.

.. figure:: images/settings-view.*
    :align: center

    Settings view

