var chip2bib_import_saeditor = new SaEditor({
    title: 'Import Chip Mapping',
    fields: [
                {name: 'race', data: 'race', label: 'Race', type: 'select2', className: 'field_req full block',
                 fieldInfo: 'bib/chip assignments are by race',
                },
                {name: 'file', data: 'file', label: 'Import File', type: 'upload',
                 display: function(data) {
                    return chip2bib_import_saeditor.saeditor.file('data', data).filename
                 },
                 fieldInfo: 'csv file must have two columns with headings of chip, bib',
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
var chip2bib_import = function(url) {
    return chip2bib_import_saeditor.edit_button_hook(url);
}

