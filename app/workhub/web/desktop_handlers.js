// desktop_handlers.js - workhub app-specific desktop message handlers
(function() {
    desktopBus.on('workhubDialogOpen', function(data, event) {
        desktopBus.installIframeTabTrap(event.source);
    });

    desktopBus.on('workhubDialogClose', function(data, event) {
        desktopBus.removeIframeTabTrap();
    });
})();
