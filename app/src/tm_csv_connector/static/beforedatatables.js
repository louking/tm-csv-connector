$( function () {
    // if groups are being used, need to set up translation variables before datatables is initialized
    // required for datatables option {serverside:true}
});


/**
 * check if any results have bib alert, and if so, check with user before sending confirm
 * 
 * @returns true if user confirms or if no bib alerts, false if user cancels
 */
function confirmConfirm(dt) {
    // only one row is selected, the bib alerts need to be checked for any rows up to this one
    var selected_row = dt.row({selected: true}).data();

    var bibalert_rows = dt
        .rows()
        .data()
        .filter(function(row, instance){
            // only check rows up to the currently selected row, and only if not already confirmed
            if (row.is_confirmed != undefined && row.is_confirmed != "") return false;  
            if (row.placepos > selected_row.placepos) return false;

            return row.bibalert != undefined && row.bibalert != "" && row.bibalert != null;
        });
        
    if (bibalert_rows.length > 0) {
        return confirm(`There are ${bibalert_rows.length} results with bib alerts. Are you sure you want to confirm them?`);
    } else {
        return true;
    }
}

/**
 * handles the Confirm button on the Results view
 * 
 * @param {*} e 
 * @param {datatable} dt 
 * @param {*} node 
 * @param {*} config 
 */
function results_confirm( e, dt, node, config ) {
    // check if any results have bib alert, and if so, check with user before sending confirm
    if (!confirmConfirm(dt)) {
        return;
    }

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
