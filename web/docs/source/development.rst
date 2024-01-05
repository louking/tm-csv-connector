******************
Development
******************

* make sure tm-reader-client is not running as a service, docker-compose app aren't running

  * in installtest folder, from run Administrator powershell, run :code:`./disable-all.ps1`

* start tm-reader-client

  * in vscode, Run and Debug > Python: tm-reader-client

* start tm-csv-connector (debug)

  * ctrl-p task docker-compose: debug
  * in vscode, Run and Debug > Python: Remote Attach

* start tm-csv-connector (no debug)

  * ctrl-p task docker-compose: up

* stop tm-csv-connector

  * ctrl-p task docker-compose: down

* to do database migration, upgrade, run migration then upgrade by starting app [needs test]

  from docker pane, right click tm-csv-connector-app > Attach Shell

  .. code-block:: shell

    flask db migrate -m "races: add start_time"
  
  OR from powershell

  .. code-block:: powershell
    
    docker exec tm-csv-connector-app-1 flask db migrate -m "races: add start_time"

  then stop tm-csv-connector, start tm-csv-connector as above
