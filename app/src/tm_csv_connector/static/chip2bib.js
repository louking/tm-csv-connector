var chip2bib_import_saeditor = new SaEditor({
    title: 'Import Chip Mapping',
    fields: [
                {name: 'file', data: 'file', label: 'Import File', type: 'upload',
                 display: function(data) {
                    return chip2bib_import_saeditor.saeditor.file('data', data).filename
                 },
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

});

// need to create this function because of some funkiness of how eval works from the python interface
var chip2bib_import = function(url) {
    return chip2bib_import_saeditor.edit_button_hook(url);
}

