// constants
const CHECK_TABLE_UPDATE = 1000;     // ms, interval to check for table updates
const RESULTS_COOKIE_TIMEOUT = 5000; // ms, timeout for cookie mutex

// mutex
let results_cookie_mutex = new MutexPromise('results-cookie', {timeout: RESULTS_COOKIE_TIMEOUT});

// duplicate bib and scan flags (#158). The server sends each flagged row's dup_places: the places
// of the other results with the same bib ('bib') or scan ('scan'). The flag's label shows them,
// and a right-click on a flagged cell jumps to the next one.
const DUP_LABEL_MAX_PLACES = 3;
const DUP_CELLS = {bib: 'td.bibno_field', scan: 'td.scanned_bibno_field'};

function dup_label(places) {
    let shown = places.slice(0, DUP_LABEL_MAX_PLACES).join(', ');
    return places.length > DUP_LABEL_MAX_PLACES ? `${shown}…` : shown;
}

// set the cells' data-dup attributes, which style.css shows after the flag; call on draw
function update_dup_labels(table) {
    table.rows({page: 'current'}).every(function() {
        let node = this.node();
        if (!node) return;
        // an editor response has no dup_places; the next poll restores them
        let dups = this.data().dup_places || {};
        $.each(DUP_CELLS, function(kind, selector) {
            $(node).find(selector).attr('data-dup', dups[kind] ? dup_label(dups[kind]) : null);
        });
    });
}

// on right-click of a flagged cell, show the result with the next place with the same bib or
// scan, wrapping around after the last
function jump_to_dup(table, e, kind) {
    let data = table.row($(e.currentTarget).closest('tr')).data();
    let places = data && data.dup_places ? data.dup_places[kind] : undefined;
    // leave the browser's menu alone if there's nowhere to go
    if (!places || !places.length) return;
    e.preventDefault();

    let next = places.find(function(place) { return place > data.placepos; });
    if (next === undefined) next = places[0];
    let target = table.row(function(idx, rowdata) { return rowdata.placepos == next; });
    if (!target.any()) return;

    // the target may be on another page
    let pos = table.rows({order: 'current', search: 'applied'}).indexes().indexOf(target.index());
    let len = table.page.len();
    if (pos >= 0 && len > 0 && Math.floor(pos / len) !== table.page()) {
        table.page(Math.floor(pos / len)).draw('page');
    }

    // not selected, since selecting a row stops the table updates
    let node = target.node();
    node.scrollIntoView({block: 'center'});
    let cell = $(node).find(DUP_CELLS[kind]);
    cell.addClass('dup-jump-target');
    setTimeout(function() { cell.removeClass('dup-jump-target'); }, 2000);
}

function init_dup_flags(table) {
    table.on('draw.dt', function() { update_dup_labels(table); });
    update_dup_labels(table);
    table.on('contextmenu', 'tbody tr.dup-bib td.bibno_field', function(e) { jump_to_dup(table, e, 'bib'); });
    table.on('contextmenu', 'tbody tr.dup-scan td.scanned_bibno_field', function(e) { jump_to_dup(table, e, 'scan'); });
}
