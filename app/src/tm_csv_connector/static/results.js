// global #connect-disconnect, #scanner-connect-disconnect buttons
var cd, scd;

// global websockets
var tm_reader; // process which interacts directly with time machine
var scanner;   // process which interacts directly with scanner
const serveruri = 'ws://tm.localhost:8080/tm_reader';
const readeruri = 'ws://tm.localhost:8081/';
const scanneruri = 'ws://tm.localhost:8082/';
// track checkConnected interval
var ccinterval, scanner_ccinterval;

// remember if connected
var connected, scanner_connected;

// form parameters
var raceid, port, scannerport, logdir;

// constants
const PING_INTERVAL = 30000;
const CHECK_CONNECTED_WAIT = 3000;
const REOPEN_SOCKET_WAIT = 5000;
const CHECK_TABLE_UPDATE = 1000;

// save last draw time
var last_draw;

$( function() {
    cd = $('#connect-disconnect');
    cd.on('click', cdbuttonclick);

    scd = $('#scanner-connect-disconnect');
    scd.on('click', scanner_cdbuttonclick);

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

    // determine text for button by querying tm-reader-client over websocket
    tm_reader = new StableWebSocket({
        name: 'reader',
        uri: readeruri,
        open_callback: setParams,
        recv_msg_callback: function(msg) {
            let rsp = JSON.parse(msg);
            // console.log(`reader: received ${msg}`);
            connected = rsp.connected;
            if (rsp.connected) {
                cd.text('Disconnect');
            } else {
                cd.text('Connect');
            }    
        }
    });
    // determine text for button by querying tm-reader-client over websocket
    scanner = new StableWebSocket({
        name: 'scanner',
        uri: scanneruri,
        open_callback: setParams,
        recv_msg_callback: function(msg) {
            let rsp = JSON.parse(msg);
            // console.log(`scanner: received ${msg}`);
            scanner_connected = rsp.connected;
            if (rsp.connected) {
                scd.text('Disconnect');
                $('.scanned_bibno_field, .bibalert_field').show();
            } else {
                scd.text('Connect');
                $('.scanned_bibno_field, .bibalert_field').hide();
            }    
        }
    });

    // keep the connect/disconnect buttons updated
    ccinterval = setInterval(checkConnected, CHECK_CONNECTED_WAIT, tm_reader);
    scanner_ccinterval = setInterval(checkConnected, CHECK_CONNECTED_WAIT, scanner);
});

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
     * ping a websocket, else browser closes with 1006 error due to inactivity
     * @param {WebSocket} websocket 
     */
    #ping_socket(that) {
        let msg = JSON.stringify({opcode: 'ping'});
        that.send(msg);
        that.ping_timeout = setTimeout(that.#ping_socket, that.ping_interval, that);
    }
}

function cdbuttonclick() {
    var msg;
    if (port != null) {
        if (!connected) {
            msg = JSON.stringify({opcode: 'open', port: port, raceid: raceid, loggingpath: ''});
            tm_reader.send(msg);
        } else {
            msg = JSON.stringify({opcode: 'close'});
            tm_reader.send(msg);
        }
    } else {
        alert('set port first');
    }
}

function scanner_cdbuttonclick() {
    var msg;
    if (scannerport != null) {
        if (!scanner_connected) {
            msg = JSON.stringify({opcode: 'open', port: scannerport, raceid: raceid, loggingpath: ''});
            scanner.send(msg);
        } else {
            msg = JSON.stringify({opcode: 'close'});
            scanner.send(msg);
        }
    } else {
        alert('set port first');
    }
}


// setParams
function setParams() {
    // set up for table redraw
    let resturl = window.location.pathname + '/rest';

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

    // send latest raceid to reader and scanner processes
    msg = JSON.stringify({opcode: 'raceid', raceid: raceid});
    tm_reader.send(msg);
    scanner.send(msg);

    $.ajax( {
        url: '/_setparams',
        type: 'post',
        dataType: 'json',
        data: data,
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