// desktop_handlers.js — skillbot app-specific desktop message handlers
// Loaded by desktop.html when skillbot is launched via desktopBus
(function() {
    desktopBus.on('skillbotModalOpen', function(data, event) {
        desktopBus.installIframeTabTrap(event.source);
    });

    desktopBus.on('skillbotModalClose', function(data, event) {
        desktopBus.removeIframeTabTrap();
    });
})();
