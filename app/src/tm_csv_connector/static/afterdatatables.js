function afterdatatables() {
    console.log('afterdatatables()');

    let pathname = location.pathname;

    if (pathname == '/results') {
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
                let resturl = window.location.pathname + `/rest?since=${last_draw}`;
                last_draw = moment().format();
                refresh_table_data(_dt_table, resturl, 'full-hold');
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

    }
}