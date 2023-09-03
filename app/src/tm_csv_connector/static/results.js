// global #connect-disconnect button
var cd;

// global websockets
var tm_reader; // process which interacts directly with time machine
const serveruri = 'ws://tm.localhost:8080/tm_reader';
const readeruri = 'ws://tm.localhost:8081/';
// track checkConnected interval
var ccinterval;

// remember if connected
var connected;

// form parameters
var raceid, port, outputdir, logdir;

// constants
const PING_INTERVAL = 30000;
const CHECK_CONNECTED_WAIT = 3000;
const REOPEN_SOCKET_WAIT = 5000;

$( function() {
    cd = $('#connect-disconnect');
    cd.button();
    cd.on('click', cdbuttonclick);

    $('#race').select2({
        placeholder: 'select a race',
        width: "style",
    });
    $('#port').select2({
        placeholder: 'select a port',
        width: "style",
    });

    // determine text for button by querying tm-reader-client over websocket
    tm_reader = new StableWebSocket({
        name: 'reader',
        uri: readeruri,
        open_callback: setParams,
        recv_msg_callback: function(msg) {
            rsp = JSON.parse(msg);
            // console.log(`reader: received ${msg}`);
            connected = rsp.connected;
            if (rsp.connected) {
                cd.text('Disconnect');
            } else {
                cd.text('Connect');
            }    
        }
    });
    ccinterval = setInterval(checkConnected, CHECK_CONNECTED_WAIT);
});

// check whether connected to time machine periodically
function checkConnected() {
    // message is sent if websocket state is OPEN, else throws exception
    try {
        var msg = JSON.stringify({opcode: 'is_connected'});
        // console.log(`sending ${msg}`);
        tm_reader.send(msg);      
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

// setParams
function setParams() {
    // set up for table redraw
    resturl = window.location.pathname + '/rest';

    // query and set age grade
    raceid = $('#race').val();
    port = $('#port').val();
    outputdir = $('#outputdir').val();
    logdir = $('#logdir').val();

    // send latest raceid to reader process
    msg = JSON.stringify({opcode: 'raceid', raceid: raceid});
    tm_reader.send(msg);

    $.ajax( {
        // application specific: my application has different urls for different methods
        url: '/_setparams',
        type: 'post',
        dataType: 'json',
        data: {
            port: port, 
            raceid: raceid, 
            outputdir: outputdir, 
            logdir: logdir
        },
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
  