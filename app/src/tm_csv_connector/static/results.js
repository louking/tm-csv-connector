// global #connect-disconnect button
var cd;

// global websocket
var ws;

// track checkConnected interval
var ccinterval;

// remember if connected
var connected;

// form parameters
var port, outputdir, logdir;

$( function() {
    cd = $('#connect-disconnect');
    cd.button();
    cd.on('click', cdbuttonclick);

    // determine text for button by querying tm-reader-client over websocket
    ws = new WebSocket('ws://localhost:8081');
    ccinterval = setInterval(checkConnected, 500);

    // set button text based on connection status
    ws.onmessage = (event) => {
        rsp = JSON.parse(event.data);
        // console.log(`received ${event.data}`);
        connected = rsp.connected;
        if (rsp.connected) {
            cd.text('Disconnect');
        } else {
            cd.text('Connect');
        }
    } 
});

// check whether connected periodically
function checkConnected() {
    // only send message if websockets state is OPEN
    if (ws.readyState === 1) {
        var msg = JSON.stringify({opcode: 'is_connected'});
        // console.log(`sending ${msg}`);
        ws.send(msg);    
    }
}

function cdbuttonclick() {
    var msg;
    if (ws.readyState === 1) {
        if (port != null) {
            if (!connected) {
                msg = JSON.stringify({opcode: 'open', port: port, loggingpath: ''});
                ws.send(msg);
            } else {
                msg = JSON.stringify({opcode: 'close'});
                ws.send(msg);
            }
        } else {
            alert('set port first');
        }
    } else {
        alert('reader service not ready');
    }
}

/**
 * ref https://www.w3schools.com/js/js_cookies.asp
 * 
 * @param {string} cname - name of cookie
 * @returns cookie value or ""
 */
function getCookie(cname) {
    let name = cname + "=";
    let decodedCookie = decodeURIComponent(document.cookie);
    let ca = decodedCookie.split(';');
    for(let i = 0; i <ca.length; i++) {
      let c = ca[i];
      while (c.charAt(0) == ' ') {
        c = c.substring(1);
      }
      if (c.indexOf(name) == 0) {
        return c.substring(name.length, c.length);
      }
    }
    return "";
  }

// setParams
function setParams() {
    // query and set age grade
    port     = $('#port').val();
    var outputdir = $('#outputdir').val();
  
    document.cookie = `port=${port};path=/`
    document.cookie = `outputdir=${outputdir};path=/`
  }
  