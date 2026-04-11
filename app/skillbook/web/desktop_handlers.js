// desktop_handlers.js — skillbook app-specific desktop message handlers
// Loaded by desktop.html when skillbook is launched via desktopBus
(function() {
    desktopBus.on('skillbookDialogOpen', function(data, event) {
        desktopBus.installIframeTabTrap(event.source);
    });

    desktopBus.on('skillbookDialogClose', function(data, event) {
        desktopBus.removeIframeTabTrap();
    });
})();
