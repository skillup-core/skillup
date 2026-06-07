// desktop_handlers.js — skilltalk app-specific desktop message handlers
// Loaded by desktop.html when skilltalk is launched via desktopBus
(function() {
    desktopBus.on('skilltalkModalOpen', function(data, event) {
        desktopBus.installIframeTabTrap(event.source);
    });

    desktopBus.on('skilltalkModalClose', function(data, event) {
        desktopBus.removeIframeTabTrap();
    });

    desktopBus.on('skilltalkSettingsModalOpen', function(data, event) {
        desktopBus.installIframeTabTrap(event.source);
    });

    desktopBus.on('skilltalkSettingsModalClose', function(data, event) {
        desktopBus.removeIframeTabTrap();
    });
})();
