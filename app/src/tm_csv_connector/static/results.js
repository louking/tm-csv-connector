// global #connect-disconnect button
var cd;

// global websockets
var tm_reader, // process which interacts directly with time machine
    tm_server; // web server
const serveruri = 'ws://tm.localhost:8080/tm_reader';
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

    // determine text for button by querying tm-reader-client over websocket
    tm_reader = new WebSocket('ws://localhost:8081');
    ccinterval = setInterval(checkConnected, CHECK_CONNECTED_WAIT);

    // set button text based on connection status
    tm_reader.onmessage = (event) => {
        rsp = JSON.parse(event.data);
        // console.log(`received ${event.data}`);
        connected = rsp.connected;
        if (rsp.connected) {
            cd.text('Disconnect');
        } else {
            cd.text('Connect');
        }
    } 

    open_server();
});

// check whether connected periodically
function checkConnected() {
    // only send message if websockets state is OPEN
    if (tm_reader.readyState === 1) {
        var msg = JSON.stringify({opcode: 'is_connected'});
        // console.log(`sending ${msg}`);
        tm_reader.send(msg);    
    }
}

function open_server() {
    tm_server = open_socket('server', serveruri, open_server, check_server, CHECK_CONNECTED_WAIT, PING_INTERVAL, REOPEN_SOCKET_WAIT);
    // console.log('attempting to create new WebSocket instance for server');
    // setTimeout(check_server, CHECK_CONNECTED_WAIT);
    // tm_server = new WebSocket(serveruri);

    // tm_server.onopen = (event) => {
    //     console.log('tm server websocket open');
    //     // start ping process
    //     setTimeout(ping_socket, PING_INTERVAL, tm_server);
    // }

    // tm_server.onclose = (event) => {
    //     console.log(`tm server websocket closed, reopening: ${event.code}, ${event.reason}, clean=${event.wasClean}`)
    //     tm_server = null;
    //     // assume the server is restarting. Wait a little while before trying to reopen
    //     setTimeout(open_server, REOPEN_SOCKET_WAIT);
    // }
    
    // tm_server.onmessage = (event) => {
    //     console.log(`received ${event.data}`)
    // }

    // tm_server.onerror = (event) => {
    //     console.log(`tm server error detected: ${event}`)
    // }
}

function check_server() {
    check_timeout = null;
    if (tm_server != null && (tm_server.readyState === WebSocket.CONNECTING || tm_server.readyState === WebSocket.OPEN)) {
        // looking good
    } else {
        // failed -- try again in a little bit
        console.log('failed to create WebSocket instance for server');
        if (open_timeout != null) {
            clearTimeout(open_timeout);
        }
        open_timeout = setTimeout(open_server, REOPEN_SOCKET_WAIT);
    }    
}

/**
 * storage for WebSockets, by name
 */
var _websockets = {};

/**
 * get websocket by name
 * 
 * @param {string} name 
 * @returns WebSocket
 */
function ws(name) {
    if (name in _websockets) {
        return _websockets[name];
    } else {
        return null
    }
}

/**
 * open a persistent websocket
 * 
 * @param {string} name - name of socket, must be unique on page
 * @param {string} uri - uri to open
 * @param {*} open_function 
 * @param {*} check_function 
 * @param {int} check_connected_wait - time in msec before checking if connected
 * @param {int} ping_interval - time in msec between pings
 * @param {int} reopen_socket_wait - time in msec to wait after failure to try reopening
 * @returns WebSocket()
 */
var check_timeout = null;
var open_timeout = null;
function open_socket(name, uri, open_function, check_function, check_connected_wait, ping_interval, reopen_socket_wait) {
    console.log(`${name}: attempting to create new WebSocket instance`);
    open_timeout = null;
    if (check_timeout != null) {
        clearTimeout(check_timeout);
    }
    check_timeout = setTimeout(check_function, check_connected_wait);
    websocket = new WebSocket(uri);

    websocket.onopen = (event) => {
        console.log(`${name} websocket open`);
        // start ping process
        setTimeout(ping_socket, ping_interval, websocket);
    }

    websocket.onclose = (event) => {
        console.log(`${name}: websocket closed, reopening: ${event.code}, ${event.reason}, clean=${event.wasClean}`)
        // assume the server is restarting. Wait a little while before trying to reopen
        if (open_timeout != null) {
            clearTimeout(open_timeout);
        }
        open_timeout = setTimeout(open_function, reopen_socket_wait);
    }
    
    websocket.onmessage = (event) => {
        console.log(`${name}: received ${event.data}`)
    }

    websocket.onerror = (event) => {
        console.log(`${name}: error detected: ${event}`)
    }

    return websocket;
}

// this needs to be part of a class with class variable websocket because websocket can't be an argument
// as this function is referenced before the websocket is created
function check_socket(name, websocket, open_function, reopen_socket_wait) {
    if (websocket != null && (websocket.readyState === WebSocket.CONNECTING || websocket.readyState === WebSocket.OPEN)) {
        // looking good
    } else {
        // failed -- try again in a little bit`
        console.log(`${name} failed to create WebSocket instance`);
        if (open_timeout != null) {
            clearTimeout(open_timeout);
        }
        open_timeout = setTimeout(open_function, reopen_socket_wait);
    }    
}

/**
 * ping a websocket, else browser closes with 1006 error due to inactivity
 * @param {WebSocket} websocket 
 */
function ping_socket(websocket) {
    msg = JSON.stringify({opcode: 'ping'});
    if (websocket.readyState === WebSocket.OPEN) {
        websocket.send(msg);
        setTimeout(ping_socket, PING_INTERVAL, websocket);
    }
}

function cdbuttonclick() {
    var msg;
    if (tm_reader.readyState === WebSocket.OPEN) {
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
    } else {
        alert('reader service not ready');
    }
}

// setParams
function setParams() {
    // query and set age grade
    raceid = $('#race').val();
    port = $('#port').val();
    outputdir = $('#outputdir').val();
    logdir = $('#logdir').val();

    msg = JSON.stringify({opcode: 'params', port: port, raceid: raceid, outputdir: outputdir, logdir: logdir});
    if (tm_reader.readyState === WebSocket.OPEN) {
        tm_server.send(msg);
    } else {
        console.log(`tm server websocket not connected, can't send ${msg}`);
    }
  }
  