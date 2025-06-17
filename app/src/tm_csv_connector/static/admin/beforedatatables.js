// Simulation Events view
var simulationevents_import_saeditor = new SaEditor({
    title: 'Import Simulation Events',
    fields: [
             {name: 'simulation', data: 'simulation', label: 'Simulation', type: 'select2', className: 'field_req full block',
                 fieldInfo: 'simulation events are stored by simulation',
             },
             {name: 'file', data: 'file', label: 'Import File', type: 'upload',
                 display: function(data) {
                     return simulationevents_import_saeditor.saeditor.file('data', data).filename
                 },
                 fieldInfo: 'csv file must contain columns time, etype, and bibno',
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

