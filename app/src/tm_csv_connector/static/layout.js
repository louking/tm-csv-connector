$( function() {
    // smartmenus initialization
    $( "#navigation>ul").addClass("sm sm-blue");
    $( "#navigation>ul" ).smartmenus({
			subMenusSubOffsetX: 1,
			subMenusSubOffsetY: -8
    });

    // disable click on smartmenus submenu tab
    $( ".navbar a.has-submenu" ).click(function(e) {
        e.preventDefault();
    });

    // all navbar links which are not on this site (i.e., don't start with '/') open in new tab
    $( '.navbar a' ).not('[href^="/"]').attr('target', '_blank');

    buttons = $('.ui-button');
    buttons.button();    
});

