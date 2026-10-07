// global #connect-disconnect, #scanner-connect-disconnect buttons
var cd, scd;

// global websockets
var tm_reader; // process which interacts directly with time machine
var scanner;   // process which interacts directly with scanner
var trident;   // process which interacts directly with trident
const serveruri = 'ws://tm.localhost:8080/tm_reader';
const readeruri = 'ws://tm.localhost:8081/';
const scanneruri = 'ws://tm.localhost:8082/';
const tridenturi = 'ws://tm.localhost:8083/';
// track checkConnected interval
var ccinterval, scanner_ccinterval, trident_ccinterval, start_time_interval;

// remember if connected, websockets open
var connected, scanner_connected, trident_connected, trident_status;
var trident_status_prev = null;
// client status ('connected', 'connecting', 'reconnecting', 'disconnected'), see client_status()
var scanner_status, trident_client_status;
var scanner_status_prev = null;
// set when a stop is sent while connecting/reconnecting -- it takes effect only when the client's current
// attempt gives up (up to ~21s for the chip reader), so the button shows Stopping... until then
var scanner_stopping = false, trident_stopping = false;
// port the scanner client is connected to or retrying, null if not running
var scanner_client_port = null;
var tm_websocket_open = false;
var scanner_websocket_open = false;
var trident_websocket_open = false;

// form, port parameters
var raceid, logdir;
var port, scannerport;

// constants
const PING_INTERVAL = 30000;
const CHECK_CONNECTED_WAIT = 3000;
const CHECK_INITIALIZED_WAIT = 1000;
const GET_COMPORTS_WAIT = 1000;
const REOPEN_SOCKET_WAIT = 5000;

// chip reader statuses which show the alert banner (and beep on the transition into one)
const CHIPREADER_ALERTS = {
    'network-unreachable': 'Chip reader A: network unreachable',
    'no-response':         'Chip reader A: not responding',
    'reconnecting':        'Chip reader A: connection lost, reconnecting',
};

// bluetooth type mapping
const bluetooth_select_id = {
    scanner: 'scannerport',
    tmwif:   'port',
};

// save last draw time
var last_draw;

$( function() {
    cd = $('#connect-disconnect');
    cd.on('click', cdbuttonclick);

    scd = $('#scanner-connect-disconnect');
    scd.on('click', scanner_cdbuttonclick);

    // #82 requires work here, and elsewhere
    tcd = $('#chipreaderA-connect-disconnect');
    tcd.on('click', trident_cdbuttonclick);

    $('#set-start-time-button').on('click', set_start_time_click);

    $('#race').select2({
        placeholder: 'select a race',
        width: "style",
    });
    $('#port').select2({
        placeholder: 'select a port',
        width: "style",
    });
    $('#scannerport').select2({
        placeholder: 'select a port',
        width: "style",
    });

    // determine text for connect/disconnect button by querying tm-reader-client over websocket
    // handle response for 'get_comports'
    tm_reader = new StableWebSocket({
        name: 'reader',
        uri: readeruri,
        open_callback: function() {
            tm_websocket_open = true;
            update_alert_banner($('#tm-alert-banner'), null);
            send_raceid(tm_reader);
        },
        close_callback: function() {
            connected = false;
            cd.text('Connect');
            client_not_running(tm_websocket_open, $('#tm-alert-banner'),
                'Time Machine reader client is not running -- results are not being received');
        },
        recv_msg_callback: function(msg) {
            let rsp = JSON.parse(msg);
            if (rsp.opcode == 'connection_status') {
                // console.log(`reader: received ${msg}`);
                connected = rsp.connected;
                if (rsp.connected) {
                    cd.text('Disconnect');
                } else {
                    cd.text('Connect');
                }    
            
            // what are the current devices? this comes in when the view is initialized
            } else if (rsp.opcode == 'available_devices') {
                // https://select2.org/programmatic-control/add-select-clear-items
                Object.keys(bluetooth_select_id).forEach(bttype => {
                    let portselect = $(`#${bluetooth_select_id[bttype]}`);

                    // remember if any is selected
                    let portselected = portselect.val();

                    // let's remember if what was selected before is available
                    let portselected_reset = false;

                    // empty out the current select and add an empty option
                    portselect.empty();
                    portselect.append(new Option('select port', null));

                    // add the current devices
                    let these_devices = rsp.devices[bttype];
                    for (let j=0;j<these_devices.length; j++) {
                        let device = these_devices[j];
                        option = new Option(device.text, device.id);
                        portselect.append(option);
                        if (portselected == device.id) {
                            portselected_reset = true;
                        }
                    }

                    // reset the previously selected
                    if (portselected_reset) {
                        portselect.val(portselected);
                    }

                    // let select2 and others know of the changes
                    portselect.trigger('change');
                });
            }
        }
    });

    // determine text for connect/disconnect button by querying scanner over websocket
    scanner = new StableWebSocket({
        name: 'scanner',
        uri: scanneruri,
        open_callback: function() {scanner_websocket_open = true; send_raceid(scanner)},
        close_callback: function() {
            scanner_connected = false;
            scanner_status = scanner_status_prev = 'disconnected';
            scanner_client_port = null;
            scanner_stopping = false;
            scd.prop('disabled', false).text('Connect').removeClass('client-reconnecting');
            client_not_running(scanner_websocket_open, $('#scanner-alert-banner'),
                'Scanner client is not running -- scans are not being received');
        },
        recv_msg_callback: function(msg) {
            let rsp = JSON.parse(msg);
            // console.log(`scanner: received ${msg}`);
            scanner_connected = rsp.connected;
            scanner_status = client_status(rsp);
            scanner_client_port = rsp.port;
            if (!is_retrying(scanner_status)) scanner_stopping = false;
            scd.prop('disabled', scanner_stopping);
            if (scanner_status == 'connected') {
                scd.text('Disconnect');
            } else if (scanner_stopping) {
                scd.text('Stopping...');
            } else if (scanner_switches_port()) {
                scd.text('Connect');
            } else if (scanner_status == 'connecting') {
                scd.text('Stop Connecting');
            } else if (scanner_status == 'reconnecting') {
                scd.text('Stop Reconnecting');
            } else {
                scd.text('Connect');
            }
            scd.toggleClass('client-reconnecting', scanner_status == 'reconnecting');

            // a dropped scanner is silent -- scans just stop arriving -- so escalate with a
            // banner and a beep on the transition into reconnecting (not on every poll)
            if (scanner_status == 'reconnecting' && scanner_status_prev != 'reconnecting') {
                client_alert_beep();
            }
            update_alert_banner($('#scanner-alert-banner'), scanner_status == 'reconnecting' ?
                'Scanner: connection lost, reconnecting -- scans are not being received' : null);
            scanner_status_prev = scanner_status;
        }
    });

    // determine text for connect/disconnect button by querying trident over websocket
    trident = new StableWebSocket({
        name: 'trident',
        uri: tridenturi,
        open_callback: function() {trident_websocket_open = true; send_raceid(trident)},
        close_callback: function() {
            trident_connected = false;
            trident_client_status = trident_status = trident_status_prev = 'disconnected';
            trident_stopping = false;
            tcd.prop('disabled', false).text('Connect').removeClass('client-reconnecting');
            $("#chipreader-alert-A").attr('style', 'color: lightgrey;');
            client_not_running(trident_websocket_open, $('#chipreader-alert-banner'),
                'Chip reader client is not running -- chip reads are not being received');
        },
        recv_msg_callback: function(msg) {
            let rsp = JSON.parse(msg);
            // console.log(`trident: received ${msg}`);
            trident_connected = rsp.connected;
            trident_client_status = client_status(rsp);
            if (!is_retrying(trident_client_status)) trident_stopping = false;
            tcd.prop('disabled', trident_stopping);
            if (trident_client_status == 'connected') {
                tcd.text('Disconnect');
            } else if (trident_stopping) {
                tcd.text('Stopping...');
            } else if (trident_client_status == 'connecting') {
                tcd.text('Stop Connecting');
            } else if (trident_client_status == 'reconnecting') {
                tcd.text('Stop Reconnecting');
            } else {
                tcd.text('Connect');
            }
            tcd.toggleClass('client-reconnecting', trident_client_status == 'reconnecting');

            // detailedstatus stays 'disconnected' while the client auto-retries, so surface that separately
            trident_status = trident_client_status == 'reconnecting' ? 'reconnecting' : rsp.detailedstatus;
            tsi = $("#chipreader-alert-A")
            if (trident_status == 'connected') {
                tsi.attr('style', 'color: limegreen;');
            } else if (trident_status == 'disconnected') {
                tsi.attr('style', 'color: lightgrey;');
            } else if (trident_status == 'no-response') {
                tsi.attr('style', 'color: red;');
            } else if (trident_status == 'network-unreachable') {
                tsi.attr('style', 'color: yellow;');
            } else if (trident_status == 'reconnecting') {
                tsi.attr('style', 'color: orange;');
            }

            // escalate network-unreachable / no-response / reconnecting beyond the small status
            // dot -- easy to miss during a live race -- with a banner and a beep
            // on the transition into a degraded state (not on every poll)
            if (CHIPREADER_ALERTS[trident_status] && !CHIPREADER_ALERTS[trident_status_prev]) {
                client_alert_beep();
            }
            update_alert_banner($('#chipreader-alert-banner'), CHIPREADER_ALERTS[trident_status]);
            trident_status_prev = trident_status;
        }
    });

    // keep the connect/disconnect buttons updated
    ccinterval = setInterval(checkConnected, CHECK_CONNECTED_WAIT, tm_reader);
    scanner_ccinterval = setInterval(checkConnected, CHECK_CONNECTED_WAIT, scanner);
    trident_ccinterval = setInterval(checkConnected, CHECK_CONNECTED_WAIT, trident);

    // pick up race.start_time if it gets auto-set from the first live Trident GUNTIME marker
    start_time_interval = setInterval(refresh_start_time, CHECK_CONNECTED_WAIT);

    // when websockets first open, setParams
    checkInitialized();

    // ask tm reader what are the connected comports
    get_comports();
});

// show a hard-to-miss client connectivity banner (see client-alert-banner in style.css) with text, or hide it if no text
function update_alert_banner(banner, text) {
    if (text) {
        banner.text(text).show();
    } else {
        banner.hide();
    }
}

// a client's WebSocket closed: the client process isn't running (service stopped or crashed), so nothing
// answers is_connected and the page would otherwise keep showing its last status. Alert (banner, and a beep
// the first time) only if the client was running earlier on this page -- one that never ran may not be
// installed. Called again on each failed reopen attempt; the client's next status reply replaces the banner.
function client_not_running(was_open, banner, text) {
    if (!was_open) return;
    if (!banner.is(':visible') || banner.text() != text) {
        client_alert_beep();
    }
    update_alert_banner(banner, text);
}

// status from a client's is_connected response; older clients only report connected
function client_status(rsp) {
    return rsp.status || (rsp.connected ? 'connected' : 'disconnected');
}

// true if the client is running but not connected, i.e., a first attempt or auto-retrying
function is_retrying(status) {
    return status == 'connecting' || status == 'reconnecting';
}

// true if clicking Connect while the scanner client is connecting/reconnecting would switch it to a
// newly selected port, rather than the click stopping the retries
function scanner_switches_port() {
    return (scanner_status == 'connecting' || scanner_status == 'reconnecting')
        && scannerport != null && scanner_client_port != null && scannerport != scanner_client_port;
}

// audible alert when a client transitions into a degraded state
function client_alert_beep() {
    try {
        let ctx = new (window.AudioContext || window.webkitAudioContext)();
        let osc = ctx.createOscillator();
        let gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.frequency.value = 880;
        gain.gain.value = 0.2;
        osc.start();
        osc.stop(ctx.currentTime + 0.3);
    } catch (e) {
        // audio not available in this browser/context, ignore
    }
}

// check whether connected to time machine periodically
function checkConnected(asyncprocess) {
    // message is sent if websocket state is OPEN, else throws exception
    try {
        let msg = JSON.stringify({opcode: 'is_connected'});
        // console.log(`sending ${msg}`);
        asyncprocess.send(msg);      
    }
    catch(e) {
        // do nothing, will try again later
    }
}

// when all websockets first open at startup, setParams()
function checkInitialized() {
    if (tm_websocket_open && scanner_websocket_open && trident_websocket_open) {
        setParams();
    } else {
        setTimeout(checkInitialized, CHECK_INITIALIZED_WAIT)
    }
}

function get_comports() {
    try {
        $.getJSON('/_getbluetoothdevices', function(data) {
            try {
                tm_reader.send(JSON.stringify({opcode: 'get_comports', 'bluetoothdevices': data}));
            } catch(e) {
                setTimeout(get_comports, GET_COMPORTS_WAIT);
            }
        });
    } catch(e) {
        setTimeout(get_comports, GET_COMPORTS_WAIT);
    }
}
/**
 * TODO: move to loutilities
 * 
 * open a persistent websocket
 * 
 * @param {object} options_config - configuration for websocket
 * @param {string} options_config.name - name of socket, must be unique on page
 * @param {string} options_config.uri - uri to open
 * @param {function} options_config.open_callback() - function to call when websocket is opened
 * @param {function} options_config.close_callback() - function to call when websocket is closed
 * @param {function} options_config.recv_msg_callback(msg) - function to call when message is received
 * @param {int} options_config.check_connected_wait - time in msec before checking if connected
 * @param {int} options_config.ping_interval - time in msec between pings
 * @param {int} options_config.reopen_socket_wait - time in msec to wait after failure to try reopening
 * @returns StableWebSocket()
 */
class StableWebSocket {
    websocket = null;
    check_timeout = null;
    open_timeout = null;
    ping_timeout = null;
    last_recv_time = null;
    last_ping_time = null;

    constructor(options_config) {
        let defaultoptions = {
            name: 'socket',
            uri: '',
            open_callback: function() {},
            close_callback: function() {},
            recv_msg_callback: function(msg) {},
            check_connected_wait: 3000,
            ping_interval: 30000,
            reopen_socket_wait: 5000,
            log_data: false,
        }
        let options = {
            ...defaultoptions, 
            ...options_config
        };

        this.name = options.name;
        this.uri = options.uri;
        this.check_connected_wait = options.check_connected_wait;
        this.open_callback = options.open_callback;
        this.close_callback = options.close_callback;
        this.recv_msg_callback = options.recv_msg_callback;
        this.ping_interval = options.ping_interval;
        this.reopen_socket_wait = options.reopen_socket_wait;
        this.log_data = options.log_data;

        this.#open_socket(this);
    }

    #open_socket(that) {
        console.log(`${that.name}: attempting to create new WebSocket instance`);
        that.open_timeout = null;
        that.last_ping_time = null;
        if (that.check_timeout != null) {
            clearTimeout(that.check_timeout);
        }
        if (that.ping_timeout != null) {
            clearTimeout(that.ping_timeout);
        }
        that.check_timeout = setTimeout(that.#check_socket, that.check_connected_wait, that);
        that.websocket = new WebSocket(that.uri);

        that.websocket.onopen = (event) => {
            console.log(`${that.name}: websocket open`);
            that.last_recv_time = Date.now();
            that.open_callback();
            // start ping process
            that.ping_timeout = setTimeout(that.#ping_socket, that.ping_interval, that);
        }

        that.websocket.onclose = (event) => {
            that.websocket = null;
            that.close_callback();
            console.log(`${that.name}: websocket closed, reopening: ${event.code}, ${event.reason}, clean=${event.wasClean}`)
            // assume the server is restarting. Wait a little while before trying to reopen
            if (that.open_timeout != null) {
                clearTimeout(that.open_timeout);
            }
            that.open_timeout = setTimeout(that.#open_socket, that.reopen_socket_wait, that);
        }

        that.websocket.onmessage = (event) => {
            that.last_recv_time = Date.now();
            if (that.log_data) console.log(`${that.name}: received ${event.data}`);
            let msg = JSON.parse(event.data);
            if (msg.opcode != 'pong') {
                that.recv_msg_callback(event.data);
            }
        }
    
        that.websocket.onerror = (event) => {
            console.log(`${that.name}: error detected: ${event.message}`)
        }    
    }

    #check_socket(that) {
        if (that.websocket != null && (that.websocket.readyState === WebSocket.CONNECTING || that.websocket.readyState === WebSocket.OPEN)) {
            // looking good
        } else {
            // failed -- try again in a little bit`
            console.log(`${that.name}: failed to create WebSocket instance`);
            if (that.open_timeout != null) {
                clearTimeout(that.open_timeout);
            }
            that.open_timeout = setTimeout(that.#open_socket, that.reopen_socket_wait, that);
        }    
    }

    send(msg) {
        var that = this;
        if (that.websocket && that.websocket.readyState === WebSocket.OPEN) {
            that.websocket.send(msg);
        } else {
            throw new Error(`${that.name}: websocket not open, can't send ${msg}`)
        }
    }

    /**
     * ping a websocket, else browser closes with 1006 error due to inactivity.
     * also detects zombie connections (readyState OPEN but messages not flowing).
     * @param {WebSocket} websocket
     */
    #ping_socket(that) {
        // zombie detection: if a previous ping went unanswered (nothing received since),
        // the connection is dead despite appearing OPEN — force close to trigger reconnect
        if (that.last_ping_time !== null && that.last_recv_time < that.last_ping_time) {
            console.log(`${that.name}: zombie socket detected (no response since last ping), forcing close`);
            that.websocket.close();
            return;
        }
        try {
            let msg = JSON.stringify({opcode: 'ping'});
            that.send(msg);
            that.last_ping_time = Date.now();
        } catch(e) {
            // websocket not open; reconnect logic will handle it
            return;
        }
        that.ping_timeout = setTimeout(that.#ping_socket, that.ping_interval, that);
    }
}

function cdbuttonclick() {
    var msg;
    if (connected) {
        try {
            msg = JSON.stringify({opcode: 'close'});
            tm_reader.send(msg);
        } catch(e) {
            alert('Cannot disconnect: reader client not reachable');
        }
    } else if (port != null) {
        try {
            msg = JSON.stringify({opcode: 'open', port: port, raceid: raceid, loggingpath: ''});
            tm_reader.send(msg);
        } catch(e) {
            alert('Cannot connect: reader client not reachable');
        }
    } else {
        alert('set port first');
    }
}

function scanner_cdbuttonclick() {
    var msg;
    // close also stops the client's auto-retry loop (#151), unless Connect would switch ports
    if (scanner_connected || (is_retrying(scanner_status) && !scanner_switches_port())) {
        try {
            msg = JSON.stringify({opcode: 'close'});
            scanner.send(msg);
            if (!scanner_connected) {
                scanner_stopping = true;
                scd.text('Stopping...').prop('disabled', true);
            }
        } catch(e) {
            alert('Cannot disconnect: scanner client not reachable');
        }
    } else if (scannerport != null) {
        try {
            msg = JSON.stringify({opcode: 'open', port: scannerport, raceid: raceid, loggingpath: ''});
            scanner.send(msg);
        } catch(e) {
            alert('Cannot connect: scanner client not reachable');
        }
    } else {
        alert('set port first');
    }
}

// #82 needs work here and elsewhere
function trident_cdbuttonclick() {
    var msg;
    // close also stops the client's auto-retry loop (#151)
    if (trident_connected || is_retrying(trident_client_status)) {
        try {
            msg = JSON.stringify({opcode: 'close'});
            trident.send(msg);
            if (!trident_connected) {
                trident_stopping = true;
                tcd.text('Stopping...').prop('disabled', true);
            }
        } catch(e) {
            alert('Cannot disconnect: chip reader client not reachable');
        }
    } else {
        try {
            msg = JSON.stringify({opcode: 'open', ipaddr: $(this).attr('ipaddr'), fport: $(this).attr('fport'), raceid: raceid, loggingpath: ''});
            trident.send(msg);
        } catch(e) {
            alert('Cannot connect: chip reader client not reachable');
        }
    }
}


// send the current raceid to a client process, if known; if its websocket isn't open, the client
// gets the raceid when the websocket reopens (open_callback), or from its next 'open' opcode (#147)
function send_raceid(asyncprocess) {
    if (raceid == undefined) return;
    try {
        asyncprocess.send(JSON.stringify({opcode: 'raceid', raceid: raceid}));
    } catch(e) {
        console.warn(`${asyncprocess.name}: raceid ${raceid} not sent, will resend when websocket reopens`);
    }
}

// setParams
function setParams() {
    // set up for table redraw
    let resturl = window.location.pathname + '/rest';

    // critical region with update interval (afterdatatables.js)
    results_cookie_mutex.promise()
        .then(function(mutex) {
            mutex.lock();

            // did raceid change?
            let last_raceid = raceid;
            console.log(`last_raceid = ${last_raceid}`);

            // we'll be sending these to the server
            raceid = $('#race').val();
            port = $('#port').val();
            scannerport = $('#scannerport').val();
            logdir = $('#logdir').val();
            let data = {
                port: port, 
                scannerport: scannerport,
                raceid: raceid, 
                logdir: logdir
            }

            // trigger a csv file rewrite if the raceid changed
            if (raceid != last_raceid) {
                // if not the initial case, confirm with user
                if (last_raceid == undefined) {
                    confirmed = true;
                } else {
                    confirmed = confirm('Race update will overwrite the csv file\nPress OK or Cancel');
                }

                // initial case or user confirmation causes rewrite of file based on new raceid
                if (confirmed) {
                    data.race_changed = true;
                
                // otherwise revert the change
                } else {
                    raceid = last_raceid;
                    $('#race').select2('val', last_raceid);
                    data.raceid = last_raceid;
                }
            }

            // send latest raceid to reader, scanner, and trident processes -- a client that's down
            // mustn't block /_setparams; it catches up on reconnect via send_raceid() in open_callback
            send_raceid(tm_reader);
            send_raceid(scanner);
            send_raceid(trident);

            return $.ajax( {
                url: '/_setparams',
                type: 'post',
                dataType: 'json',
                data: data,
            } )
        })
        .then(function (json) {
            if (json.status == 'success') {
                refresh_table_data(_dt_table, resturl);
                if (json.start_time !== undefined && document.activeElement !== $('#start-time')[0]) {
                    $('#start-time').val(json.start_time);
                }
            }
            else {
                alert(json.error);
            }
            results_cookie_mutex.unlock();
        })
        .catch(function(err) {
            results_cookie_mutex.unlock();
            throw err;
        });
}

// update race.start_time from the Start Time field in the filter bar
function set_start_time_click() {
    let value = $('#start-time').val();
    $.ajax({
        url: '/_setracestarttime',
        type: 'post',
        dataType: 'json',
        data: {raceid: raceid, start_time: value},
        success: function(json) {
            if (json.status == 'success') {
                $('#start-time').val(json.start_time);
            } else {
                alert(json.error);
            }
        }
    });
}

// poll race.start_time so an auto-set from the first live Trident GUNTIME marker shows up
// without a page reload; skip while the operator is actively editing the field
function refresh_start_time() {
    if (!raceid) return;
    if (document.activeElement === $('#start-time')[0]) return;

    $.getJSON('/_getracestarttime', {raceid: raceid}, function(json) {
        $('#start-time').val(json.start_time);
    });
}

function results_clear_all() {
    let nrows = _dt_table.rows().count();
    let noun = nrows === 1 ? 'result' : 'results';
    if (!confirm(`Clear all ${nrows} test ${noun} for this race? Use Undo Clear to restore.`)) {
        return;
    }

    let resturl = window.location.pathname + '/rest';

    $.ajax({
        url: '/_clearresults',
        type: 'post',
        contentType: 'application/json',
        dataType: 'json',
        data: JSON.stringify({raceid: raceid}),
        success: function(json) {
            if (json.status == 'success') {
                $('#undo-clear-button').show();
                refresh_table_data(_dt_table, resturl);
            } else {
                alert(json.error);
            }
        }
    });
}

function results_undo_clear() {
    let resturl = window.location.pathname + '/rest';

    $.ajax({
        url: '/_undoclearresults',
        type: 'post',
        contentType: 'application/json',
        dataType: 'json',
        data: JSON.stringify({raceid: raceid}),
        success: function(json) {
            if (json.status == 'success') {
                $('#undo-clear-button').hide();
                refresh_table_data(_dt_table, resturl);
            } else {
                alert(json.error);
            }
        }
    });
}

// careful, this is specific to normal mode, the function for simulation mode is in resultssim.js
// the only difference is the ajax url
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