function afterdatatables() {
    console.log('afterdatatables()');

    // handle group substitution before submitting
    register_group_for_editor('interest', '#metanav-select-interest', editor);
    // required for serverside -> register_group_for_datatable() is in beforedatatables.js
}