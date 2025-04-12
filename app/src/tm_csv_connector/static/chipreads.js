var chipreads_import_saeditor = new SaEditor({
    title: 'Import Chipreads',
    fields: [
            {name: 'race', data: 'race', label: 'Race', type: 'select2', className: 'field_req full block',
                fieldInfo: 'chip reads are stored by race',
            },
           {name: 'file', data: 'file', label: 'Import File', type: 'upload',
                 display: function(data) {
                    return chipreads_import_saeditor.saeditor.file('data', data).filename
                 },
                 fieldInfo: 'log file must be raw or filtered <a href=https://www.manula.com/manuals/tridentrfid/timemachine/1/en/topic/tag-data-message-format target=_blank>Trident read file</a>',
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
                $.getJSON("/_getraces", {},
                    function(data) {
                        $.each(data, function(i, e) {
                            options.push(e);
                        });
                    }
                ).done(function() {
                    that.saeditor.field('race').update(options);
                });            
            });
    },

});

// need to create this function because of some funkiness of how eval works from the python interface
var chipreads_import = function(url) {
    return chipreads_import_saeditor.edit_button_hook(url);
}

