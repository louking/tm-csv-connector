$( function () {
    // if groups are being used, need to set up translation variables before datatables is initialized
    // required for datatables option {serverside:true}
});

/**
 * handles the Confirm button on the Results view
 * 
 * @param {*} e 
 * @param {datatable} dt 
 * @param {*} node 
 * @param {*} config 
 */
function results_confirm( e, dt, node, config ) {
    // the preSubmit event is used to annotate the currently selected row with "confirm"
    // this is done only once, for the next edit/submit
    editor.one('preSubmit', function(e, data, action) {
        var id = dt.rows( {selected: true} ).ids()[0]
        data.data[id].confirm = true;
    })
    editor
        .edit(dt.rows( {selected: true} ).indexes(), false)
        .submit();
    dt.rows({selected: true}).deselect();
}

// https://stackoverflow.com/a/62737413/799921
function numberRoundDecimal(num, decimals) {
    return Math.round(num*Math.pow(10,decimals))/Math.pow(10,decimals)
}

function render_secs2time(data, type, row, meta) {
    if (data) {
        let time = new Date(null);
        let itime = parseInt(data);
        let ftime = parseFloat(data);
        time.setSeconds(itime);
        time.setMilliseconds(1000*numberRoundDecimal(ftime-itime,2));
        return time.toISOString().slice(11,22);
    } else {
        return data
    }
}

function scan_action(e, options) {
    e.stopPropagation();
    console.log(`scanaction()`);

    // set up for table redraw
    let resturl = window.location.pathname + '/rest';

    $.ajax( {
        url: '/_scanaction',
        type: 'post',
        dataType: 'json',
        data: options,
        success: function ( json ) {
            if (json.status == 'success') {
                refresh_table_data(_dt_table, resturl);
            }
            else {
                alert(json.error);
            }
        }
    } );
}