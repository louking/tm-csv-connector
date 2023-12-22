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
