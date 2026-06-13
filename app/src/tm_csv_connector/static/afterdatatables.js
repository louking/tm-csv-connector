function afterdatatables() {
    console.log('afterdatatables()');

    // Prevent the periodic table redraw from canceling an in-progress scan button click.
    // A draw between mousedown and mouseup destroys the button element so the click event
    // never fires and scan_action() is never called. Block any draw while a button is held.
    let scan_mousedown = false;
    $(document).on('mousedown', '.scan-action-btn', function() {
        scan_mousedown = true;
        console.log('scan-action-btn mousedown: draw guard ON');
    });
    $(document).on('mouseup', function() {
        if (!scan_mousedown) return;
        // Delay so that the click event (fired synchronously during mouseup in most browsers)
        // has already been dispatched before we clear the guard.
        setTimeout(function() {
            scan_mousedown = false;
            console.log('scan-action-btn mouseup: draw guard OFF');
        }, 0);
    });
    // preDraw.dt (camelCase) is the correct DataTables event name; returning false cancels the draw.
    _dt_table.on('preDraw.dt', function() {
        if (scan_mousedown) {
            console.log('preDraw.dt: draw blocked by scan-action-btn guard');
            return false;
        }
    });

    let pathname = location.pathname;

    // show spinner when ajax is sent (hidden in .on('draw.dt'))
    _dt_table.on('preXhr.dt', function(e, settings, json) {
        $('#spinner').show();
    });

    // when the page has been drawn, need to do some housekeeping
    _dt_table.on( 'draw.dt', function () {
        // hide spinner if shown
        $('#spinner').hide();
    });
    
    if (pathname == '/results') {
        $('#clear-all-button').on('click', results_clear_all);
        $('#undo-clear-button').on('click', results_undo_clear);

        // indicate last draw time for editor submissions, then update
        last_draw = moment().format();
        editor.on('preSubmit', function(e, data, action) {
            data['last_draw'] = last_draw;
            last_draw = moment().format();
            return true;
        });

        editor.on('postCreate', function(e, json, data, id) {
            let resturl = window.location.pathname + `/rest?since=${last_draw}`;
            last_draw = moment().format();
            refresh_table_data(_dt_table, resturl, 'full-hold');
        });

        function start_updates() {
            let draw_interval = setInterval(function() {
                // if (scan_mousedown) return;
                results_cookie_mutex.promise()
                    .then(function(mutex) {
                        mutex.lock();
                        let resturl = window.location.pathname + `/rest?since=${last_draw}`;
                        last_draw = moment().format();
                        refresh_table_data(_dt_table, resturl, 'full-hold');
                        mutex.unlock();
                    })
                    .catch(function(err) {
                        mutex.unlock();
                        throw err;
                    });
            }, CHECK_TABLE_UPDATE);

            return draw_interval;
        }

        function stop_updates() {
            clearInterval(draw_interval);
        }

        let draw_interval = start_updates();

        _dt_table.on('select.dt', function(e, dt, type, indexes) {
            $('#updates-suspended').show();
            stop_updates();
        })

        _dt_table.on('deselect.dt', function(e, dt, type, indexes) {
            $('#updates-suspended').hide();
            draw_interval = start_updates();
        })

        // when remove is completed there's no selection, so need to start updates again
        editor.on('remove.dt', function(e, json, indexes) {
            $('#updates-suspended').hide();
            draw_interval = start_updates();
        })

        _dt_table.on('click', 'tbody td.bibno_field, tbody td.time_field', function (){
            editor.inline( this, {
                onBlur: 'submit',
                submit: 'allIfChanged'
            });
        });

    } else if (pathname == '/admin/resultssim') {
        // indicate last draw time for editor submissions, then update
        last_draw = moment().format();
        editor.on('preSubmit', function(e, data, action) {
            data['last_draw'] = last_draw;
            last_draw = moment().format();
            return true;
        });

        editor.on('postCreate', function(e, json, data, id) {
            let resturl = window.location.pathname + `/rest?since=${last_draw}`;
            last_draw = moment().format();
            refresh_table_data(_dt_table, resturl, 'full-hold');
        });

        function start_updates() {
            // TODO: need to send simulation state
            let draw_interval = setInterval(function() {
                if (scan_mousedown) return;
                results_cookie_mutex.promise()
                    .then(function(mutex) {
                        mutex.lock();
                        let resturl = window.location.pathname + `/rest?`;
                        refresh_table_data(_dt_table, resturl, 'full-hold');
                        mutex.unlock();
                    })
                    .catch(function(err) {
                        mutex.unlock();
                        throw err;
                    });
            }, CHECK_TABLE_UPDATE);

            return draw_interval;
        }

        function stop_updates() {
            clearInterval(draw_interval);
        }

        let draw_interval = start_updates();

        _dt_table.on('select.dt', function(e, dt, type, indexes) {
            $('#updates-suspended').show();
            stop_updates();
        })

        _dt_table.on('deselect.dt', function(e, dt, type, indexes) {
            $('#updates-suspended').hide();
            draw_interval = start_updates();
        })

        // when remove is completed there's no selection, so need to start updates again
        editor.on('remove.dt', function(e, json, indexes) {
            $('#updates-suspended').hide();
            draw_interval = start_updates();
        })

        _dt_table.on('click', 'tbody td.bibno_field, tbody td.time_field', function (){
            editor.inline( this, {
                onBlur: 'submit',
                submit: 'allIfChanged'
            });
        });

    } else if (pathname == '/chipreads') {
        // initialize import button handling
        chipreads_import_saeditor.init();

        chipreads_import_saeditor.saeditor.on('submitComplete', function(e, json, data, action) {
            // draw will retrieve data from server because it's server side
            _dt_table.draw();
        });

    } else if (pathname == '/chip2bib') {
        // initialize import button handling
        chip2bib_import_saeditor.init();

        chip2bib_import_saeditor.saeditor.on('submitComplete', function(e, json, data, action) {
            // draw will retrieve data from server because it's server side
            _dt_table.draw();
        });

    } else if (pathname == '/chipreaders') {
        // hide New if one or more chip readers defined
        // remove after #82 implemented
        function checklength() {
            let rows = _dt_table.rows();
            if (rows[0].length == 0) {
                _dt_table.button('.buttons-create').enable();
            } else {
                _dt_table.button('.buttons-create').disable();
            }
        }
        _dt_table.on( 'draw.dt', function () {
            checklength();
        });
        checklength();
        // end #82

    } else if (pathname == '/admin/simulationevents') {
        // initialize import button handling
        simulationevents_import_saeditor.init();
    } else if (pathname == '/admin/simulationexpected') {
        // initialize import button handling
        simulationexpected_import_saeditor.init();

    }

}