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

        let draw_interval = setInterval(function() {
            let resturl = window.location.pathname + `/rest?since=${last_draw}`;
            last_draw = moment().format();
            refresh_table_data(_dt_table, resturl, 'full-hold');
        }, CHECK_TABLE_UPDATE);
    }
}