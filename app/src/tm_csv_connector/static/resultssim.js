/**
 * @file resultssim.js
 * @brief JavaScript for the simulation mode of the results page.
 * @details This file contains functions to handle the simulation mode of the results page,
 *          including starting, pausing, stopping the simulation, and changing the simulation speed.
 *          It also handles the initialization of the simulation parameters and the interaction with the backend.
 */

// simulation mode state and functions
// onclick event handler which calls these functions, and attributes
// set in python home.get_results_filters_sim

// steps to be executed in the simulation; last time
// TODO: should we be using sessionStorage for this?
let simsteps = []; 
let lasttime = 0;

// interval object for simulation updates
let sim_interval = null;

// constants
const CHECK_TABLE_UPDATE = 1000;
const SIMULATION_UPDATE = 250; // milliseconds, how often to update the simulation

// simulation mode: executed when play/pause button is clicked
function startPauseSimulation() {
    let simulation_state = $('#simulation-state').text();
    if (simulation_state == 'stopped') {
        // create simulationrun row; get the label and value; get the simulation steps
        $.ajax( $('#simulation-run').attr('url'), {
            method: 'post',
            data: {simulation_id: $('#sim').val() },
            dataType: 'json',
            success: function ( json ) {
                if (json.status == 'success') {
                    // set new simulation-run select option
                    $('#simulation-run').empty();
                    for (let i = 0; i < json.options.length; i++) {
                        let option = new Option(json.options[i].label, json.options[i].value);
                        $('#simulation-run').append(option);
                    }
                    // first option is latest (just created), so select it
                    $('#simulation-run').val(json.options[0].value).trigger('change');

                    // remember simulation steps, prepare for running
                    simsteps = json.simsteps;
                    if (simsteps.length > 0) {
                        lasttime = simsteps[0].time-1; // last time is one less than the first step time
                    }

                    // now we're running
                    startSimulation();
                } else {
                    alert(`simulation-run post error: ${json.error}`);
                }
            }
        } );

    } else if (simulation_state == 'paused') {
        // now we're running
        startSimulation();
    
    } else if (simulation_state == 'running') {
        $('#simulation-state').text('paused');
        $('#start-pause-simulation').attr('title', 'resume simulation');

        startSimulationUI();
    } else if (simulation_state == 'finished') {
        alert('Simulation is finished, please stop it before starting again.');
    }
}

// simulation mode: executed when start/pause button is clicked if simulation is not stopped
function startSimulation() {
    $('#simulation-state').text('running');
    $('#start-pause-simulation').attr('title', 'pause simulation');
    $('#pause-icon').css('display', 'inline-block');
    $('#play-icon').css('display', 'none');
    $('#stop-simulation').button('enable').removeClass('ui-state-disabled');
    $('#sim').prop('disabled', true).addClass('ui-state-disabled');
    $('#simulation-run').prop('disabled', true).addClass('ui-state-disabled');

    sim_interval = setInterval( function() {
        let simulationrun_id = $('#simulation-run').val();
        lasttime += getSimulationSpeed() * SIMULATION_UPDATE / 1000; // update last time based on speed
        console.log(`step_simulation: simulationrun_id ${simulationrun_id}, lasttime ${lasttime}`);
        while (simsteps.length > 0 && simsteps[0].time <= lasttime) {
            let step = simsteps.shift();
            console.log(`step_simulation: step ${step.time} for simulationrun_id ${simulationrun_id}`);
            // send the step to the backend
            $.ajax( {
                url: '/admin/_simstep/rest',
                type: 'post',
                dataType: 'json',
                data: {
                    simulationrun_id: simulationrun_id,
                    step: step
                },
                success: function ( json ) {
                    if (json.status == 'success') {
                        // update the last time
                        lasttime = step.time;
                    } else {
                        alert(json.error);
                    }
                }
            } );
        }
        if (simsteps.length == 0) {
            // no steps, nothing to do
            console.log(`step_simulation: no more steps for simulationrun_id ${simulationrun_id}`);

            clearInterval(sim_interval);
            $('#simulation-state').text('finished');
            $('#start-pause-simulation').prop('disabled', true).addClass('ui-state-disabled');

            // TODO: indicate that the running simulation has finished
            // NOTE: not calling stopSimulation() here because we don't want to automatically tally the results
        }
    }, SIMULATION_UPDATE );

}

// simulation mode: executed when simulation is stopped / paused
// updates the UI buttons and stops the step interval
function stopSimulationUI() {
    $('#pause-icon').css('display', 'none');
    $('#play-icon').css('display', 'inline-block');
    $('#stop-simulation').button('disable').addClass('ui-state-disabled');
    $('#sim').prop('disabled', false).removeClass('ui-state-disabled');
    $('#simulation-run').prop('disabled', false).removeClass('ui-state-disabled');

    if (sim_interval) {
        clearInterval(sim_interval);
        sim_interval = null;
    }
}

// simulation mode: executed when stop button is clicked
function stopSimulation() {
    $('#simulation-state').text('stopped');
    $('#start-pause-simulation').attr('title', 'start simulation');
    $('#start-pause-simulation').prop('disabled', false).removeClass('ui-state-disabled');

    stopSimulationUI();

    // tally results for the simulation run
    // TODO: this should be done in the backend
}

// simulation mode: executed when speed is changed
// simulation speed multiplier: 1 is normal speed, 2 is double speed, 0.5 is half speed, etc.
function getSimulationSpeed() {
    let simulation_speed_text = $('#simulation-speed').text();
    let simulation_speed = simulation_speed_text.substring(0, simulation_speed_text.length - 1); // remove 'x' at the end
    simulation_speed = parseFloat(simulation_speed);
    return simulation_speed;
}
function setSimulationSpeed(speed) {
    $('#simulation-speed').text(`${speed}x`);   // add 'x' at the end for display
}
    
function slowSimulation() {
    let simulation_speed = getSimulationSpeed();
    simulation_speed /= 2;
    if (simulation_speed < 0.125) {
        simulation_speed = 0.125; // minimum speed
    }
    setSimulationSpeed(simulation_speed);
}
function speedSimulation() {
    let simulation_speed = getSimulationSpeed();
    simulation_speed *= 2;
    if (simulation_speed > 8) {
        simulation_speed = 8; // maximum speed
    }
    setSimulationSpeed(simulation_speed);
}

$( function() {
    // set up for simulation changes
    $('#sim').select2({
        placeholder: 'select a simulation',
        width: "style",
    });

    $('#sim').on('change', function() {
    });

    $('#simulation-run').select2({
        width: "style",
    });

    $('#simulation-run').on('change', function() {
        // when the simulation run changes, set the parameters on the backend
        setParams();
    });

    // initialize parameters on backend
    setParams();

    // initialize button states (https://stackoverflow.com/a/44973368/799921)
    $('#stop-simulation').button('disable').addClass('ui-state-disabled');
    $('#sim').prop('disabled', false).removeClass('ui-state-disabled');
    $('#simulation-run').prop('disabled', false).removeClass('ui-state-disabled');
});

function setParams() {
    // set up for table redraw
    let resturl = window.location.pathname + '/rest';

    /*
    // did simulationrun_id change?
    let last_simulationrun_id = simulationrun_id;
    console.log(`last_simulationrun_id = ${last_simulationrun_id}`);
    */

    // we'll be sending these to the server
    simulationrun_id = $('#simulation-run').val();
    let logdir = $('#logdir').val();
    let data = {
        simulationrun_id: simulationrun_id, 
        logdir: logdir
    }

    /*
    // TODO: should this all be for simulation_id, not simulationrun_id?
    // trigger a simulation results rewrite if the simulationrun_id changed
    if (simulationrun_id != last_simulationrun_id) {
        // if not the initial case, confirm with user
        if (last_simulationrun_id == undefined) {
            confirmed = true;
        } else {
            confirmed = confirm('Simulation update will overwrite the simulation results\nPress OK or Cancel');
        }

        // initial case or user confirmation causes rewrite of file based on new raceid
        if (confirmed) {
            data.race_changed = true;
        
        // otherwise revert the change
        } else {
            simulationrun_id = last_simulationrun_id;
            $('#simulation-run').select2('val', last_simulationrun_id);
            data.simulationrun_id = last_simulationrun_id;
        }
    }
    */

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

// careful, this is specific to simulation mode, the function for normal mode is in results.js
// the only difference is the ajax url
function scan_action(e, options) {
    e.stopPropagation();
    console.log(`scanaction()`);

    // set up for table redraw
    let resturl = window.location.pathname + '/rest';

    $.ajax( {
        url: '/admin/_simscanaction',
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