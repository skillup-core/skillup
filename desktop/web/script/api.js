// REST API helper: all Python backend calls go through here.

async function apiCall(action, data) {
    data = data || {};
    try {
        var response = await fetch('/api/' + action, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        return await response.json();
    } catch (error) {
        console.error('API error (' + action + '):', error);
        return null;
    }
}
