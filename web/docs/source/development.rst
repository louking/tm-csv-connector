******************
Development
******************

* make sure tm-reader-client is not running as a service

  * in installtest folder, from run Administrator powershell, run :code:`disable-tm-reader.ps1`

* make sure docker-compose app isn't running

  * in Docker Desktop, check if tm-csv-connector is running, if so stop it

* run tm-reader-client

  * in vscode, from main folder, run :code:`python .\tm-reader-client\app.py`

* run tm-csv-connector

  * in vscode, from main folder, run :code:`docker compose -f docker-compose.yml -f docker-compose.build.yml -f docker-compose.dev.yml up --build -d`

* to do database migration, upgrade, stop tm-csv-connector then run migration and upgrade

  .. code-block:: powershell
    
    docker compose -f docker-compose.yml -f docker-compose.dev.yml down
    exec tm-csv-connector-shell-1 flask db migrate -m "races: add start_time"
    docker exec tm-csv-connector-shell-1 flask db upgrade
    # run tm-csv-connector as indicated above