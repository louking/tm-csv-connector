// Simulation Events view
var simulationevents_import_saeditor = new SaEditor({
    title: 'Import Simulation Events',
    fields: [
             {name: 'simulation', data: 'simulation', label: 'Simulation', type: 'select2', className: 'field_req full block',
                 fieldInfo: 'simulation events are stored by simulation',
             },
             {name: 'start_time', data: 'start_time', label: 'Start Time', type: 'datetime', className: 'field_req full block',
                format: 'HH:mm:ss.SSS',
                fieldInfo: 'required for log file input, time race started',
             },
             {name: 'file', data: 'file', label: 'Import File', type: 'upload',
                 display: function(data) {
                     return simulationevents_import_saeditor.saeditor.file('data', data).filename
                 },
                 fieldInfo: 'csv file must contain columns time, etype, and bibno; txt file for tmtility log file',
                 className: 'field_req full block'},
             {name: 'force', data: 'force', 'type': 'hidden'},
            ],
    buttons: [
                'Import',
                {
                    text: 'Cancel',
                    action: function() {
                        this.close();
                    }
                }
            ],

    form_values: function(json) {
        return {}
    },

    after_init: function() {
        var sae = this;
        sae.saeditor
            .on('initEdit', function(e, node, data, items, type){
                sae.saeditor.field('force').set('false');
            });
        
        sae.saeditor
            .on('open', function() {
                var options = [];
                $.getJSON("/admin/_getsimulations", {},
                    function(data) {
                        $.each(data, function(i, e) {
                            options.push(e);
                        });
                    }
                ).done(function() {
                    sae.saeditor.field('simulation').update(options);
                });            
            });

        var submit_data;
        sae.saeditor
            .on('preSubmit', function(e, data, action) {
                submit_data = sae.saeditor.get();
            });
        
        sae.saeditor
            .on('submitSuccess', function(e, json, data, action) {
                var that = this;
                if (json.cause) {
                    // if overwrite requested, force the overwrite
                    if (json.confirm) {
                        $("<div>"+json.cause+"</div>").dialog({
                            dialogClass: 'no-titlebar',
                            height: "auto",
                            modal: true,
                            buttons: [
                                {   text:  'Cancel',
                                    click: function() {
                                        $( this ).dialog('destroy');
                                    }
                                },{ text:  'Overwrite',
                                    click: function(){
                                        $( this ).dialog('destroy');
                                        // no editing id, and don't show immediately, reset to what was submitted
                                        sae.saeditor.edit(null, false);
                                        sae.saeditor.set(submit_data);
                                        // now force the update
                                        sae.saeditor.field('force').set('true')
                                        sae.saeditor.submit();
                                    }
                                }
                            ],
                        });
                    
                    } else {
                        $("<div>Error Occurred: "+json.cause+"</div>").dialog({
                            dialogClass: 'no-titlebar',
                            height: "auto",
                            buttons: [
                                {   text:  'OK',
                                    click: function(){
                                        $( this ).dialog('destroy');
                                    }
                                }
                            ],
                        });
                    };

                } else {
                    sae.saeditor.field('force').set('false');
                    // show new data
                    refresh_table_data(_dt_table, '/admin/simulationevents/rest')
                }
            });
    },

});

// need to create this function because of some funkiness of how eval works from the python interface
var simulationevents_import = function(url) {
    return simulationevents_import_saeditor.edit_button_hook(url);
}

// Simulation Vector view
var simulationvector_import_saeditor = new SaEditor({
    title: 'Import Simulation Vector',
    fields: [
             {name: 'simulation', data: 'simulation', label: 'Simulation', type: 'select2', className: 'field_req full block',
                 fieldInfo: 'simulation vector entries are stored by simulation',
             },
             {name: 'file', data: 'file', label: 'Import File', type: 'upload',
                 display: function(data) {
                     return simulationvector_import_saeditor.saeditor.file('data', data).filename
                 },
                 fieldInfo: 'csv file must contain columns order, time, and bibno',
                 className: 'field_req full block'},
            ],
    buttons: [
                'Import',
                {
                    text: 'Cancel',
                    action: function() {
                        this.close();
                    }
                }
            ],

    form_values: function(json) {
        return {}
    },

    after_init: function() {
        var that = this;
        that.saeditor
            .on('open', function() {
                var options = [];
                $.getJSON("/admin/_getsimulations", {},
                    function(data) {
                        $.each(data, function(i, e) {
                            options.push(e);
                        });
                    }
                ).done(function() {
                    that.saeditor.field('simulation').update(options);
                });            
            });
    },

});

// need to create this function because of some funkiness of how eval works from the python interface
var simulationvector_import = function(url) {
    return simulationvector_import_saeditor.edit_button_hook(url);
}

