"""
Base Application Class for Skillup Framework

Provides common functionality and interface for all Skillup applications.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, Callable, TYPE_CHECKING
import threading

if TYPE_CHECKING:
    from lib.webui import WebUIEngine
    from lib.appmgr import AppContext


class BaseAppState:
    """
    Built-in state management with thread-safety and auto-notification.

    Apps can use this directly or subclass for custom behavior.
    Provides thread-safe state storage with automatic UI notifications.
    """

    def __init__(self, app: 'BaseApp'):
        """
        Initialize app state.

        Args:
            app: Parent BaseApp instance (for notifications)
        """
        self.app = app
        self.lock = threading.Lock()
        self.condition = threading.Condition(self.lock)
        self._data = {}

    def get(self, key: str, default=None) -> Any:
        """
        Thread-safe get.

        Args:
            key: State key
            default: Default value if key not found

        Returns:
            Value for key or default
        """
        with self.lock:
            return self._data.get(key, default)

    def set(self, key: str, value: Any, notify: bool = True):
        """
        Thread-safe set with optional notification.

        Args:
            key: State key
            value: State value
            notify: If True, triggers UI notification via callJS
        """
        with self.condition:
            self._data[key] = value
            self.condition.notify_all()

        if notify and self.app:
            self.app.notify_state_change('state_update', {key: value})

    def update(self, updates: dict, notify: bool = True):
        """
        Thread-safe batch update.

        Args:
            updates: Dictionary of key-value pairs
            notify: If True, triggers UI notification via callJS
        """
        with self.condition:
            self._data.update(updates)
            self.condition.notify_all()

        if notify and self.app:
            self.app.notify_state_change('state_update', updates)

    def get_all(self) -> dict:
        """
        Get thread-safe copy of all state data.

        Returns:
            Dictionary copy of all state
        """
        with self.lock:
            return dict(self._data)

    def wait_for_change(self, timeout: float = 30.0) -> bool:
        """
        Wait for state change with timeout.

        Args:
            timeout: Maximum wait time in seconds

        Returns:
            True if notified, False if timeout
        """
        with self.condition:
            return self.condition.wait(timeout=timeout)


class BaseApp(ABC):
    """
    Abstract base class for all Skillup applications.

    All apps should inherit from this class and implement required methods.

    Method Categories:
        - REQUIRED: Must be implemented by subclasses (marked with @abstractmethod)
        - OPTIONAL OVERRIDE: Can be overridden for custom behavior (has default implementation)
        - ADVANCED OVERRIDE: Can be overridden for advanced use cases (most apps don't need to)
        - HELPER: Use these methods, do not override them

    Attributes:
        engine: WebUI engine (None in CLI mode)
        context: App execution context
        _handlers: Dictionary of handlers for desktop mode
        _state: Lazy-initialized state object
        _state_callbacks: List of state change callbacks
    """

    def __init__(self, engine: Optional['WebUIEngine'], context: 'AppContext'):
        """
        Initialize the application.

        Args:
            engine: WebUI engine (None in CLI mode)
            context: App execution context
        """
        self.engine = engine
        self.context = context
        self._handlers: Dict[str, Callable] = {}
        self._state = None  # Lazy initialization
        self._state_callbacks = []

    # ========================================================================
    # REQUIRED METHODS - Must be implemented by subclasses
    # ========================================================================

    @abstractmethod
    def on_run_cli(self, args: List[str]) -> int:
        """
        [REQUIRED] CLI mode execution handler.

        Called when the app is executed in CLI mode.
        Every app must implement this method.

        Args:
            args: Command line arguments

        Returns:
            Exit code (0 = success, non-zero = error)
        """
        pass

    # ========================================================================
    # OPTIONAL OVERRIDE - Can be overridden for custom behavior
    # ========================================================================

    def create_state(self) -> BaseAppState:
        """
        [OPTIONAL OVERRIDE] Create state object.

        Override to provide custom state class:
            def create_state(self):
                return MyCustomState(self)

        Returns:
            BaseAppState or custom state object
        """
        return BaseAppState(self)

    def on_run_desktop_initialize(self) -> int:
        """
        [OPTIONAL OVERRIDE] Desktop mode initialization hook.

        Called in subprocess when desktop mode starts, after the app instance
        is created but before the JSON-RPC loop begins.

        Override this method to perform desktop-specific initialization such as:
        - Registering handlers via register_handlers()
        - Loading configuration
        - Initializing databases
        - Setting up background tasks

        Returns:
            Exit code (0 = success, non-zero = error to abort subprocess)
        """
        # Default: no initialization needed
        return 0

    def get_menu_items(self) -> List[Dict[str, str]]:
        """
        [OPTIONAL OVERRIDE] Get menu items for desktop sidebar.

        Override this method to provide custom menu items.

        Returns:
            List of menu item dictionaries with 'id' and 'name' keys
        """
        return []

    def on_menu_click(self, menu_id: str):
        """
        [OPTIONAL OVERRIDE] Handle menu click event in desktop mode.

        Override this method to handle menu interactions.

        Args:
            menu_id: ID of the clicked menu item
        """
        pass

    def on_close(self):
        """
        [OPTIONAL OVERRIDE] Cleanup hook called when app is closed.

        Called when the app is closed in desktop mode (user clicks "Exit App").
        Override this method to perform cleanup such as:
        - Cancelling background threads
        - Resetting state
        - Closing database connections
        - Saving unsaved data

        Note: This is only called in desktop mode when the app is explicitly closed.
        It is NOT called during normal process termination.
        """
        pass

    # ========================================================================
    # ADVANCED OVERRIDE - Only override if you need custom logic
    # ========================================================================

    def on_handler(self, handler_name: str, data: dict, language: str = 'en') -> dict:
        """
        [ADVANCED OVERRIDE] Handle callPython handlers from JavaScript.

        This is the main entry point for all JavaScript -> Python communication.
        By default, it dispatches to registered handlers.

        **For most apps:** Do NOT override this method. Instead, use register_handlers()
        in on_run_desktop_initialize() to register individual handlers.

        **Override only if you need:**
        - Dynamic handler routing (e.g., pattern matching on handler names)
        - Common pre-processing or post-processing for all handlers
        - Custom authentication, logging, or error handling logic

        Args:
            handler_name: Handler name (e.g., 'verify', 'get_status')
            data: Request data from JavaScript
            language: Current UI language ('en', 'ko', etc.)

        Returns:
            Response dictionary to send back to JavaScript

        Example of advanced override:
            def on_handler(self, handler_name, data, language):
                # Add common pre-processing
                self.log_request(handler_name, data)

                # Call parent's default dispatcher
                result = super().on_handler(handler_name, data, language)

                # Add common post-processing
                self.log_response(handler_name, result)
                return result
        """
        if handler_name in self._handlers:
            handler = self._handlers[handler_name]
            try:
                return handler(data, language)
            except Exception as e:
                return {'success': False, 'error': f'Handler error: {str(e)}'}
        else:
            return {'success': False, 'error': f'Unknown handler: {handler_name}'}

    # ========================================================================
    # HELPER METHODS - Use these, do not override
    # ========================================================================

    @property
    def state(self) -> BaseAppState:
        """
        [HELPER] Get state object (lazy initialization).

        Apps can access state directly:
            self.state.set('progress', 50)
            value = self.state.get('status')

        For custom state classes, override create_state().

        Returns:
            BaseAppState or custom state object
        """
        if self._state is None:
            self._state = self.create_state()
        return self._state

    def notify_state_change(self, event_name: str, data: dict):
        """
        [HELPER] Notify state change to UI and callbacks.

        Sends update to JavaScript via engine.callJS().
        Also triggers any registered state callbacks.

        Args:
            event_name: Event identifier (e.g., 'state_update', 'progress_changed')
            data: Event data to send to UI
        """
        # Call registered callbacks
        for callback in self._state_callbacks:
            try:
                callback(event_name, data)
            except Exception:
                pass

        # Send to JavaScript via engine
        if self.engine:
            self.engine.callJS(event_name, data)

    def register_state_callback(self, callback: Callable[[str, dict], None]):
        """
        [HELPER] Register callback for state change events.

        Useful for testing or logging state changes.

        Args:
            callback: Function(event_name, data) to call on state changes
        """
        self._state_callbacks.append(callback)

    def register_handlers(self, handlers: Dict[str, Callable[[dict, str], dict]]):
        """
        [HELPER] Register handlers for desktop mode.

        Call this in on_run_desktop_initialize() to register handlers.

        Args:
            handlers: Dictionary of handler name -> handler function

        Example:
            def on_run_desktop_initialize(self):
                self.register_handlers({
                    'get_data': self._handle_get_data,
                    'save_data': self._handle_save_data
                })
                return 0
        """
        self._handlers.update(handlers)

    def load_config(self, defaults: Dict[str, Any]) -> Dict[str, Any]:
        """
        [HELPER] Load application configuration.

        Args:
            defaults: Default configuration values

        Returns:
            Configuration dictionary
        """
        from lib.config import load_config
        return load_config(self.context.config_path, defaults, app_id=self.context.app_id)

    def save_config(self, config: Dict[str, Any]):
        """
        [HELPER] Save application configuration.

        Args:
            config: Configuration dictionary to save
        """
        from lib.config import save_config
        save_config(self.context.config_path, config)

    def get_data_dir(self) -> str:
        """
        [HELPER] Get the app's persistent data directory.

        Returns the path to the data directory for this app:
            ~/.config/skillup/app/{id_name}-{id}/data/

        The directory is created automatically if it does not exist.
        Use this directory to store persistent app data such as history,
        cache files, or user-generated content.

        Returns:
            Absolute path to the app's data directory
        """
        from lib.config import get_app_data_path
        # Derive app_id and app_id_name from config_path
        # config_path is: .../app/{id_name}-{id}/config.ini
        import os
        config_dir = os.path.dirname(self.context.config_path)
        dir_name = os.path.basename(config_dir)  # e.g. "skillbook-b00k5k1l"
        if '-' in dir_name:
            parts = dir_name.rsplit('-', 1)
            app_id_name, app_id = parts[0], parts[1]
        else:
            app_id_name, app_id = None, dir_name
        return get_app_data_path(app_id, app_id_name)

    def callJS(self, action: str, data: Any):
        """
        [HELPER] Send message to JavaScript (callJS).

        Use this to send notifications or updates from Python to JavaScript.

        Args:
            action: Action name (JavaScript function to call)
            data: Data to send
        """
        if self.engine:
            self.engine.callJS(action, data)
