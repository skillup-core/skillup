// Groups: list, create, detail (members, join requests, settings).

// ============================================================================
// State
// ============================================================================
var _groupsView = 'list';   // 'list' | 'detail' | 'new'
var _groupsTab = 'my';      // 'my' | 'browse'
var _currentGroup = null;   // group object from get_group
var _currentGroupMembers = [];
var _currentGroupIsAdmin = false;

// ============================================================================
// Entry point: called when settings page opens (or refreshes)
// ============================================================================
async function loadGroups() {
    _groupsView = 'list';
    _currentGroup = null;
    await _renderGroupList();
}

function _switchGroupTab(tab) {
    _groupsTab = tab;
    _renderGroupList();
}

// ============================================================================
// List view (tabbed: My Groups | Browse)
// ============================================================================
async function _renderGroupList() {
    var container = document.getElementById('groups-container');
    if (!container) return;
    var L = i18n[currentLanguage];

    // Tab bar + New Group button
    var tabMy = _groupsTab === 'my';
    var tabBaseStyle = 'background:none;border:none;border-radius:0;padding:6px 14px;font-size:13px;cursor:pointer;margin-bottom:-1px;';
    var activeStyle = 'border-bottom:2px solid var(--accent-color,#4a90e2);color:var(--text-primary);font-weight:600;';
    var inactiveStyle = 'border-bottom:2px solid transparent;color:var(--text-secondary);';
    var html = '<div style="display:flex;align-items:flex-end;margin-bottom:12px;border-bottom:1px solid var(--border-color);">'
        + '<button class="btn" style="' + tabBaseStyle + (tabMy ? activeStyle : inactiveStyle)
        + '" onclick="_switchGroupTab(\'my\')">' + L['settings.group_tab_my'] + '</button>'
        + '<button class="btn" style="' + tabBaseStyle + (!tabMy ? activeStyle : inactiveStyle)
        + '" onclick="_switchGroupTab(\'browse\')">' + L['settings.group_tab_browse'] + '</button>'
        + '<div style="flex:1;"></div>'
        + '<button class="btn btn-primary" style="font-size:13px;padding:5px 12px;margin-bottom:4px;" '
        + 'onclick="showNewGroupForm()">' + L['settings.group_new'] + '</button>'
        + '</div>'
        + '<div id="groups-tab-content"></div>';

    container.innerHTML = html;

    if (tabMy) {
        await _renderMyGroupsTab();
    } else {
        await _renderBrowseTab();
    }
}

async function _renderMyGroupsTab() {
    var el = document.getElementById('groups-tab-content');
    if (!el) return;
    var L = i18n[currentLanguage];

    var data = await apiCall('list_groups');
    var groups = (data && data.groups) ? data.groups : [];

    if (groups.length === 0) {
        el.innerHTML = '<div style="color:var(--text-secondary);font-size:13px;padding:8px 0;">'
            + L['settings.groups_desc'] + '</div>';
        return;
    }

    var html = '';
    groups.forEach(function(g) {
        html += _groupListItemHtml(g, true);
    });
    el.innerHTML = html;
    _loadGroupListImages(groups, el);
}

var _browseAllGroups = [];

async function _renderBrowseTab() {
    var el = document.getElementById('groups-tab-content');
    if (!el) return;
    var L = i18n[currentLanguage];

    var data = await apiCall('browse_groups');
    _browseAllGroups = (data && data.groups) ? data.groups : [];

    el.innerHTML = '<input type="text" id="browse-search" class="form-control" '
        + 'style="width:100%;padding:6px 10px;font-size:14px;margin-bottom:8px;" '
        + 'placeholder="' + L['settings.group_search_placeholder'] + '" autocomplete="off">'
        + '<div id="browse-results"></div>';

    document.getElementById('browse-search').addEventListener('input', _filterBrowseGroups);
    _filterBrowseGroups();
}

function _filterBrowseGroups() {
    var input = document.getElementById('browse-search');
    var results = document.getElementById('browse-results');
    if (!input || !results) return;
    var L = i18n[currentLanguage];

    var q = input.value.trim().toLowerCase();
    if (!q) {
        results.innerHTML = '';
        return;
    }

    var filtered = _browseAllGroups.filter(function(g) {
        return g.name.toLowerCase().indexOf(q) !== -1
            || (g.description && g.description.toLowerCase().indexOf(q) !== -1);
    });

    if (filtered.length === 0) {
        results.innerHTML = '<div style="color:var(--text-secondary);font-size:13px;padding:8px 0;">'
            + L['settings.group_search_no_results'] + '</div>';
        return;
    }

    var html = '';
    filtered.forEach(function(g) { html += _groupBrowseItemHtml(g); });
    results.innerHTML = html;
    _loadGroupListImages(filtered, results);
}

function _groupPolicyLabel(g) {
    var L = i18n[currentLanguage];
    if (g.all_user) return L['settings.group_join_policy_all_user'];
    var p = (g.config && g.config.join_policy) ? g.config.join_policy : 'free';
    if (p === 'approve') return L['settings.group_join_policy_approve'];
    return L['settings.group_join_policy_free'];
}

function _groupListItemHtml(g, clickable) {
    var L = i18n[currentLanguage];
    return '<div class="group-list-item"'
        + (clickable ? ' onclick="showGroupDetail(\'' + g.id + '\')"' : '')
        + ' style="display:flex;align-items:center;padding:10px 0;border-bottom:1px solid var(--border-color);'
        + (clickable ? 'cursor:pointer;' : '') + '">'
        + '<div style="width:36px;height:36px;border-radius:50%;overflow:hidden;background:var(--bg-tertiary);'
        + 'display:flex;align-items:center;justify-content:center;margin-right:10px;flex-shrink:0;">'
        + '<img src="/common/resource/img/default-avatar.svg" alt="" '
        + 'style="width:100%;height:100%;object-fit:cover;" data-group-img="' + g.id + '">'
        + '</div>'
        + '<div style="flex:1;min-width:0;">'
        + '<div style="font-size:14px;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'
        + _escHtml(g.name) + '</div>'
        + '<div style="font-size:11px;color:var(--text-secondary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'
        + (g.description ? _escHtml(g.description) : _groupPolicyLabel(g)) + '</div>'
        + '</div>'
        + '<svg viewBox="0 0 24 24" style="width:16px;height:16px;flex-shrink:0;fill:var(--text-secondary);">'
        + '<path d="M10 6L8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z"/></svg>'
        + '</div>';
}

function _groupBrowseItemHtml(g) {
    var L = i18n[currentLanguage];
    var badge = '';
    var joinBtn = '';
    if (g.is_member) {
        badge = '<span style="font-size:11px;color:var(--text-secondary);margin-right:8px;">'
            + L['settings.group_member'] + '</span>';
        joinBtn = badge;
    } else if (g.request_pending) {
        joinBtn = '<span style="font-size:11px;color:var(--text-secondary);margin-right:8px;">'
            + L['settings.group_requested'] + '</span>';
    } else {
        joinBtn = '<button class="btn btn-primary" style="font-size:11px;padding:3px 10px;" '
            + 'onclick="groupJoin(\'' + _escAttr(g.id) + '\')">' + L['settings.group_join'] + '</button>';
    }
    return '<div style="display:flex;align-items:center;padding:10px 0;border-bottom:1px solid var(--border-color);">'
        + '<div style="width:36px;height:36px;border-radius:50%;overflow:hidden;background:var(--bg-tertiary);'
        + 'display:flex;align-items:center;justify-content:center;margin-right:10px;flex-shrink:0;">'
        + '<img src="/common/resource/img/default-avatar.svg" alt="" '
        + 'style="width:100%;height:100%;object-fit:cover;" data-group-img="' + g.id + '">'
        + '</div>'
        + '<div style="flex:1;min-width:0;">'
        + '<div style="font-size:14px;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'
        + _escHtml(g.name) + '</div>'
        + '<div style="font-size:11px;color:var(--text-secondary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'
        + (g.description ? _escHtml(g.description) : _groupPolicyLabel(g)) + '</div>'
        + '</div>'
        + joinBtn
        + '</div>';
}

async function _loadGroupListImages(groups, parent) {
    var root = parent || document;
    for (var i = 0; i < groups.length; i++) {
        var g = groups[i];
        if (!g.has_image) continue;
        try {
            var res = await apiCall('get_group_image', { group_id: g.id, size: 'small' });
            if (res && res.data_uri) {
                var imgs = root.querySelectorAll('[data-group-img="' + g.id + '"]');
                imgs.forEach(function(img) { img.src = res.data_uri; });
            }
        } catch (e) {}
    }
}

async function groupJoin(groupId) {
    var L = i18n[currentLanguage];
    var confirmed = await showConfirmDialog(
        L['settings.group_join_confirm_title'],
        L['settings.group_join_confirm_text'],
        {}
    );
    if (!confirmed) return;
    var res = await apiCall('group_request_join', { group_id: groupId });
    if (res && res.success) {
        if (res.pending) {
            showMessageBox({ title: '', text: L['settings.group_join_request_sent'] });
        }
        await _renderBrowseTab();
    } else {
        showMessageBox({ title: '', text: (res && res.error) || 'Error' });
    }
}

// ============================================================================
// New group dialog
// ============================================================================
function showNewGroupForm() {
    var L = i18n[currentLanguage];

    var overlay = document.createElement('div');
    overlay.id = 'new-group-overlay';
    overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;'
        + 'background:rgba(0,0,0,0.5);z-index:10700;display:flex;'
        + 'align-items:center;justify-content:center;';

    var box = document.createElement('div');
    box.style.cssText = 'background:var(--bg-secondary);border:1px solid var(--border-color);'
        + 'border-radius:8px;padding:24px;min-width:320px;max-width:420px;width:100%;';
    box.innerHTML =
        '<div style="font-size:15px;font-weight:600;color:var(--text-primary);margin-bottom:16px;">'
        + L['settings.group_new'] + '</div>'
        + '<div style="margin-bottom:10px;">'
        + '<div style="font-size:12px;color:var(--text-secondary);margin-bottom:4px;">' + L['settings.group_name'] + '</div>'
        + '<input type="text" id="ng-name" class="form-control" '
        + 'style="width:100%;padding:6px 10px;font-size:14px;" '
        + 'placeholder="' + L['settings.group_name_placeholder'] + '">'
        + '</div>'
        + '<div style="margin-bottom:10px;">'
        + '<div style="font-size:12px;color:var(--text-secondary);margin-bottom:4px;">' + L['settings.group_description'] + '</div>'
        + '<input type="text" id="ng-description" class="form-control" '
        + 'style="width:100%;padding:6px 10px;font-size:14px;" maxlength="150" '
        + 'placeholder="' + L['settings.group_description_placeholder'] + '">'
        + '</div>'
        + '<div style="margin-bottom:20px;">'
        + '<div style="font-size:12px;color:var(--text-secondary);margin-bottom:4px;">' + L['settings.group_join_policy'] + '</div>'
        + '<select id="ng-policy" class="settings-select" style="font-size:13px;width:100%;">'
        + '<option value="free">' + L['settings.group_join_policy_free'] + '</option>'
        + '<option value="approve">' + L['settings.group_join_policy_approve'] + '</option>'
        + '<option value="all_user">' + L['settings.group_join_policy_all_user'] + '</option>'
        + '</select>'
        + '</div>'
        + '<div style="display:flex;justify-content:flex-end;">'
        + '<button id="ng-cancel" class="btn btn-secondary" style="font-size:13px;padding:6px 14px;margin-right:8px;">'
        + L['dialog.cancel'] + '</button>'
        + '<button id="ng-create" class="btn btn-primary" style="font-size:13px;padding:6px 16px;">'
        + L['settings.group_create'] + '</button>'
        + '</div>';

    overlay.appendChild(box);
    document.body.appendChild(overlay);

    var nameEl = box.querySelector('#ng-name');
    setTimeout(function() { nameEl.focus(); }, 50);

    var closeOverlay = function() { document.body.removeChild(overlay); };

    overlay.addEventListener('click', function(e) { if (e.target === overlay) closeOverlay(); });

    box.querySelector('#ng-cancel').addEventListener('click', closeOverlay);

    box.querySelector('#ng-create').addEventListener('click', function() {
        _submitNewGroupDialog(overlay, box);
    });

    box.querySelector('#ng-name').addEventListener('keydown', function(e) {
        if (e.key === 'Enter') { e.preventDefault(); _submitNewGroupDialog(overlay, box); }
        else if (e.key === 'Escape') { e.preventDefault(); closeOverlay(); }
    });
}

async function _submitNewGroupDialog(overlay, box) {
    var nameEl = box.querySelector('#ng-name');
    var descEl = box.querySelector('#ng-description');
    var policyEl = box.querySelector('#ng-policy');
    var name = nameEl ? nameEl.value.trim() : '';
    if (!name) { if (nameEl) nameEl.focus(); return; }

    var createBtn = box.querySelector('#ng-create');
    if (createBtn) createBtn.disabled = true;

    var policyVal = policyEl ? policyEl.value : 'free';
    var allUser = policyVal === 'all_user';
    var joinPolicy = allUser ? 'free' : policyVal;

    var res = await apiCall('create_group', {
        name: name,
        description: descEl ? descEl.value.trim() : '',
        all_user: allUser,
        join_policy: joinPolicy
    });

    if (res && res.success) {
        document.body.removeChild(overlay);
        _groupsTab = 'my';
        await _renderGroupList();
    } else {
        if (createBtn) createBtn.disabled = false;
        var L = i18n[currentLanguage];
        showMessageBox({ title: '', text: (res && res.error) || 'Error' });
    }
}

// ============================================================================
// Group detail dialog
// ============================================================================
var _groupDetailOverlay = null;

async function showGroupDetail(groupId) {
    // If overlay already exists (re-render from action), reuse it
    var existing = _groupDetailOverlay;
    var body = existing ? existing.querySelector('#group-detail-body') : null;
    if (body) {
        body.innerHTML = '<div style="color:var(--text-secondary);font-size:13px;padding:8px 0;">Loading...</div>';
    } else {
        // Create overlay
        var overlay = document.createElement('div');
        overlay.id = 'group-detail-overlay';
        overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;'
            + 'background:rgba(0,0,0,0.5);z-index:10700;display:flex;'
            + 'align-items:center;justify-content:center;';

        var box = document.createElement('div');
        box.style.cssText = 'background:var(--bg-secondary);border:1px solid var(--border-color);'
            + 'border-radius:8px;padding:24px;min-width:340px;max-width:480px;width:100%;'
            + 'max-height:80vh;overflow-y:auto;position:relative;';

        // Close button (top-right X)
        var closeBtn = document.createElement('button');
        closeBtn.className = 'btn';
        closeBtn.style.cssText = 'position:absolute;top:10px;right:12px;background:none;border:none;'
            + 'font-size:18px;line-height:1;color:var(--text-secondary);cursor:pointer;padding:2px 6px;';
        closeBtn.innerHTML = '&times;';
        closeBtn.onclick = function() { _closeGroupDetailDialog(); };

        var bodyDiv = document.createElement('div');
        bodyDiv.id = 'group-detail-body';
        bodyDiv.innerHTML = '<div style="color:var(--text-secondary);font-size:13px;padding:8px 0;">Loading...</div>';

        box.appendChild(closeBtn);
        box.appendChild(bodyDiv);
        overlay.appendChild(box);
        document.body.appendChild(overlay);
        _groupDetailOverlay = overlay;
        body = bodyDiv;

        // Close on backdrop click
        overlay.addEventListener('click', function(e) {
            if (e.target === overlay) _closeGroupDetailDialog();
        });
        // Close on Escape
        overlay._keyHandler = function(e) {
            if (e.key === 'Escape') _closeGroupDetailDialog();
        };
        document.addEventListener('keydown', overlay._keyHandler);
    }

    var res = await apiCall('get_group', { group_id: groupId });
    if (!res || !res.success) {
        _closeGroupDetailDialog();
        return;
    }

    _currentGroup = res.group;
    _currentGroupMembers = res.members || [];
    _currentGroupIsAdmin = _currentGroupMembers.some(function(m) {
        return m.is_admin && m.user_id === _getCurrentUserId();
    });

    _renderGroupDetail();
}

function _closeGroupDetailDialog() {
    if (_groupDetailOverlay) {
        if (_groupDetailOverlay._keyHandler) {
            document.removeEventListener('keydown', _groupDetailOverlay._keyHandler);
        }
        if (_groupDetailOverlay.parentNode) {
            _groupDetailOverlay.parentNode.removeChild(_groupDetailOverlay);
        }
        _groupDetailOverlay = null;
    }
    _currentGroup = null;
    _currentGroupMembers = [];
    _currentGroupIsAdmin = false;
}

function _getCurrentUserId() {
    var el = document.getElementById('account-id-display');
    return el ? el.textContent.trim() : '';
}

function _renderGroupDetail() {
    var overlay = _groupDetailOverlay;
    var body = overlay ? overlay.querySelector('#group-detail-body') : null;
    if (!body || !_currentGroup) return;
    var L = i18n[currentLanguage];
    var g = _currentGroup;
    var isAdmin = _currentGroupIsAdmin;
    var currentUserId = _getCurrentUserId();

    var html = '';

    // ---- Group name heading ----
    html += '<div style="font-size:15px;font-weight:600;color:var(--text-primary);margin-bottom:16px;padding-right:24px;">'
        + _escHtml(g.name) + '</div>';

    // ---- Group settings (admin only) ----
    if (isAdmin) {
        html += '<div style="margin-bottom:16px;">';
        // Name
        html += '<div style="margin-bottom:10px;">'
            + '<div style="font-size:12px;color:var(--text-secondary);margin-bottom:4px;">' + L['settings.group_name'] + '</div>'
            + '<input type="text" id="group-edit-name" class="form-control" '
            + 'style="width:100%;padding:6px 10px;font-size:14px;" value="' + _escHtml(g.name) + '">'
            + '</div>';
        // Description
        html += '<div style="margin-bottom:10px;">'
            + '<div style="font-size:12px;color:var(--text-secondary);margin-bottom:4px;">' + L['settings.group_description'] + '</div>'
            + '<input type="text" id="group-edit-description" class="form-control" '
            + 'style="width:100%;padding:6px 10px;font-size:14px;" maxlength="150" '
            + 'value="' + _escHtml(g.description || '') + '" '
            + 'placeholder="' + L['settings.group_description_placeholder'] + '">'
            + '</div>';
        // Join policy (unified: free / approve / all_user)
        var uiPolicy = g.all_user ? 'all_user' : ((g.config && g.config.join_policy) ? g.config.join_policy : 'free');
        html += '<div style="margin-bottom:4px;">'
            + '<div style="font-size:12px;color:var(--text-secondary);margin-bottom:4px;">' + L['settings.group_join_policy'] + '</div>'
            + '<select id="group-edit-policy" class="settings-select" style="font-size:13px;width:100%;">'
            + '<option value="free"' + (uiPolicy === 'free' ? ' selected' : '') + '>'
            + L['settings.group_join_policy_free'] + '</option>'
            + '<option value="approve"' + (uiPolicy === 'approve' ? ' selected' : '') + '>'
            + L['settings.group_join_policy_approve'] + '</option>'
            + '<option value="all_user"' + (uiPolicy === 'all_user' ? ' selected' : '') + '>'
            + L['settings.group_join_policy_all_user'] + '</option>'
            + '</select>'
            + '</div>';
        html += '</div>';
    }

    // ---- Join requests (admin only, approve policy) ----
    var policy2 = g.all_user ? 'all_user' : ((g.config && g.config.join_policy) ? g.config.join_policy : 'free');
    if (isAdmin && policy2 === 'approve') {
        html += '<div style="margin-bottom:16px;">'
            + '<div style="font-size:13px;font-weight:600;color:var(--accent-text);margin-bottom:8px;">'
            + L['settings.group_join_requests'] + '</div>'
            + '<div id="group-join-requests-list"></div>'
            + '</div>';
    }

    // ---- Members ----
    html += '<div style="font-size:13px;font-weight:600;color:var(--accent-text);margin-bottom:8px;">'
        + L['settings.group_members'] + '</div>';
    html += '<div id="group-members-list"></div>';

    // ---- Add member (admin only) ----
    if (isAdmin) {
        html += '<div style="position:relative;margin-top:10px;">'
            + '<input type="text" id="group-new-member-id" class="form-control" '
            + 'style="width:100%;padding:6px 10px;font-size:13px;" '
            + 'placeholder="' + L['settings.group_add_member_placeholder'] + '" autocomplete="off">'
            + '<div id="group-member-ac" style="display:none;position:absolute;left:0;right:0;top:100%;'
            + 'background:var(--bg-secondary);border:1px solid var(--border-color);border-radius:4px;'
            + 'z-index:10900;max-height:180px;overflow-y:auto;box-shadow:0 4px 12px rgba(0,0,0,0.15);"></div>'
            + '</div>';
    }

    // ---- Save / Leave / Delete ----
    html += '<div style="margin-top:20px;display:flex;justify-content:flex-end;">';
    var isMember = _currentGroupMembers.some(function(m) { return m.user_id === currentUserId; });
    if (isAdmin) {
        html += '<button class="btn btn-secondary" style="font-size:13px;padding:6px 14px;margin-right:8px;color:var(--error);" '
            + 'onclick="groupDelete()">' + L['settings.group_delete'] + '</button>';
    }
    if (isMember && !g.all_user) {
        html += '<button class="btn btn-secondary" style="font-size:13px;padding:6px 14px;margin-right:8px;" '
            + 'onclick="groupLeave()">' + L['settings.group_leave'] + '</button>';
    }
    if (isAdmin) {
        html += '<button class="btn btn-primary" style="font-size:13px;padding:6px 14px;" '
            + 'onclick="saveGroupSettings()">' + L['settings.group_save'] + '</button>';
    }
    html += '</div>';

    body.innerHTML = html;

    _renderMembersList();
    if (isAdmin && policy2 === 'approve') {
        _renderJoinRequestsList();
    }

    if (isAdmin) {
        _initMemberAutocomplete();
    }

    // Load group image if present (scoped to overlay to avoid matching list items)
    if (g.has_image) {
        apiCall('get_group_image', { group_id: g.id, size: 'small' }).then(function(res) {
            if (res && res.data_uri && overlay.parentNode) {
                var imgs = overlay.querySelectorAll('[data-group-img="' + g.id + '"]');
                imgs.forEach(function(img) { img.src = res.data_uri; });
            }
        });
    }
}

function _renderMembersList() {
    var overlay = _groupDetailOverlay;
    var root = overlay || document;
    var el = root.querySelector('#group-members-list');
    if (!el) return;
    var L = i18n[currentLanguage];
    var currentUserId = _getCurrentUserId();
    var isAdmin = _currentGroupIsAdmin;

    if (_currentGroupMembers.length === 0) {
        el.innerHTML = '<div style="color:var(--text-secondary);font-size:12px;padding:4px 0;">-</div>';
        return;
    }

    var html = '';
    _currentGroupMembers.forEach(function(m) {
        var avatarSrc = m.avatar_small
            ? ('data:' + m.avatar_mime + ';base64,' + m.avatar_small)
            : '/common/resource/img/default-avatar.svg';
        html += '<div style="display:flex;align-items:center;padding:7px 0;border-bottom:1px solid var(--border-color);">'
            + '<img src="' + avatarSrc + '" alt="" '
            + 'style="width:28px;height:28px;border-radius:50%;object-fit:cover;margin-right:8px;flex-shrink:0;">'
            + '<div style="flex:1;min-width:0;">'
            + '<span style="font-size:13px;">' + _escHtml(m.display_name) + '</span>'
            + (m.user_id !== m.display_name
                ? ' <span style="font-size:11px;color:var(--text-secondary);">(' + _escHtml(m.user_id) + ')</span>'
                : '')
            + (m.is_admin
                ? ' <span style="font-size:10px;background:var(--accent-color,#4a90e2);color:#fff;'
                  + 'border-radius:3px;padding:1px 5px;margin-left:4px;">'
                  + L['settings.group_admin_badge'] + '</span>'
                : '')
            + '</div>';

        if (isAdmin && m.user_id !== currentUserId) {
            if (m.is_admin) {
                html += '<button class="btn btn-secondary" style="font-size:11px;padding:3px 8px;margin-right:4px;" '
                    + 'onclick="groupRevokeAdmin(\'' + _escAttr(m.user_id) + '\')">'
                    + L['settings.group_revoke_admin'] + '</button>';
            } else {
                html += '<button class="btn btn-secondary" style="font-size:11px;padding:3px 8px;margin-right:4px;" '
                    + 'onclick="groupGrantAdmin(\'' + _escAttr(m.user_id) + '\')">'
                    + L['settings.group_grant_admin'] + '</button>';
                if (!_currentGroup.all_user) {
                    html += '<button class="btn btn-secondary" style="font-size:11px;padding:3px 8px;color:var(--error);" '
                        + 'onclick="groupRemoveMember(\'' + _escAttr(m.user_id) + '\')">'
                        + L['settings.group_remove_member'] + '</button>';
                }
            }
        }

        html += '</div>';
    });
    el.innerHTML = html;
}

async function _renderJoinRequestsList() {
    var overlay = _groupDetailOverlay;
    var root = overlay || document;
    var el = root.querySelector('#group-join-requests-list');
    if (!el || !_currentGroup) return;
    var L = i18n[currentLanguage];

    var res = await apiCall('group_list_requests', { group_id: _currentGroup.id });
    var reqs = (res && res.requests) ? res.requests : [];

    if (reqs.length === 0) {
        el.innerHTML = '<div style="color:var(--text-secondary);font-size:12px;padding:4px 0;">'
            + L['settings.group_no_requests'] + '</div>';
        return;
    }

    var html = '';
    reqs.forEach(function(r) {
        var avatarSrc = r.avatar_small
            ? ('data:' + r.avatar_mime + ';base64,' + r.avatar_small)
            : '/common/resource/img/default-avatar.svg';
        html += '<div style="display:flex;align-items:center;padding:7px 0;border-bottom:1px solid var(--border-color);">'
            + '<img src="' + avatarSrc + '" alt="" '
            + 'style="width:28px;height:28px;border-radius:50%;object-fit:cover;margin-right:8px;flex-shrink:0;">'
            + '<div style="flex:1;min-width:0;font-size:13px;">' + _escHtml(r.display_name)
            + (r.user_id !== r.display_name
                ? ' <span style="font-size:11px;color:var(--text-secondary);">(' + _escHtml(r.user_id) + ')</span>'
                : '')
            + '</div>'
            + '<button class="btn btn-primary" style="font-size:11px;padding:3px 8px;margin-right:4px;" '
            + 'onclick="groupApproveRequest(\'' + _escAttr(r.user_id) + '\')">'
            + L['settings.group_approve'] + '</button>'
            + '<button class="btn btn-secondary" style="font-size:11px;padding:3px 8px;" '
            + 'onclick="groupRejectRequest(\'' + _escAttr(r.user_id) + '\')">'
            + L['settings.group_reject'] + '</button>'
            + '</div>';
    });
    el.innerHTML = html;
}

// ============================================================================
// Group actions
// ============================================================================
async function saveGroupSettings() {
    if (!_currentGroup) return;
    var root = _groupDetailOverlay || document;
    var nameEl = root.querySelector('#group-edit-name');
    var descEl = root.querySelector('#group-edit-description');
    var policyEl = root.querySelector('#group-edit-policy');
    var name = nameEl ? nameEl.value.trim() : null;
    if (!name) { if (nameEl) nameEl.focus(); return; }
    var policyVal = policyEl ? policyEl.value : null;
    var allUser = policyVal === 'all_user';
    var joinPolicy = (policyVal && !allUser) ? policyVal : null;
    var res = await apiCall('update_group', {
        group_id: _currentGroup.id,
        name: name,
        description: descEl ? descEl.value.trim() : null,
        all_user: allUser,
        join_policy: joinPolicy
    });
    if (res && res.success) {
        await showGroupDetail(_currentGroup.id);
        showToast(i18n[currentLanguage]['settings.account_name_saved']);
    } else {
        showMessageBox({ title: '', text: (res && res.error) || 'Error' });
    }
}

async function groupDelete() {
    if (!_currentGroup) return;
    var L = i18n[currentLanguage];
    var confirmed = await showConfirmDialog(
        L['settings.group_delete_confirm_title'],
        L['settings.group_delete_confirm_text'],
        { yesStyle: 'danger' }
    );
    if (!confirmed) return;
    var res = await apiCall('delete_group', { group_id: _currentGroup.id });
    if (res && res.success) {
        _closeGroupDetailDialog();
        await _renderGroupList();
    } else {
        showMessageBox({ title: '', text: (res && res.error) || 'Error' });
    }
}

async function groupLeave() {
    if (!_currentGroup) return;
    var L = i18n[currentLanguage];
    var confirmed = await showConfirmDialog(
        L['settings.group_leave_confirm_title'],
        L['settings.group_leave_confirm_text'],
        {}
    );
    if (!confirmed) return;
    var res = await apiCall('group_remove_member', {
        group_id: _currentGroup.id
        // user_id omitted -> current user (server defaults to current_user)
    });
    if (res && res.success) {
        _closeGroupDetailDialog();
        await _renderGroupList();
    } else {
        var msg = (res && res.error === 'last_admin')
            ? L['settings.group_last_admin_error']
            : ((res && res.error) || 'Error');
        showMessageBox({ title: '', text: msg });
    }
}

function _initMemberAutocomplete() {
    var overlay = _groupDetailOverlay;
    var root = overlay || document;
    var input = root.querySelector('#group-new-member-id');
    var ac = root.querySelector('#group-member-ac');
    if (!input || !ac) return;

    var _acTimer = null;

    function hideAc() {
        ac.style.display = 'none';
        ac.innerHTML = '';
    }

    function showAcResults(users) {
        if (!users || users.length === 0) { hideAc(); return; }
        var html = '';
        users.forEach(function(u) {
            var label = _escHtml(u.id);
            if (u.name && u.name !== u.id) label += ' <span style="color:var(--text-secondary);font-size:11px;">(' + _escHtml(u.name) + ')</span>';
            html += '<div class="ac-item" data-id="' + _escAttr(u.id) + '" '
                + 'style="padding:7px 10px;font-size:13px;cursor:pointer;border-bottom:1px solid var(--border-color);">'
                + label + '</div>';
        });
        ac.innerHTML = html;
        ac.style.display = 'block';

        ac.querySelectorAll('.ac-item').forEach(function(item) {
            item.addEventListener('mousedown', function(e) {
                e.preventDefault();
                input.value = item.getAttribute('data-id');
                hideAc();
            });
            item.addEventListener('mouseover', function() {
                ac.querySelectorAll('.ac-item').forEach(function(i) { i.style.background = ''; });
                item.style.background = 'var(--bg-hover, rgba(0,0,0,0.07))';
            });
            item.addEventListener('mouseout', function() {
                item.style.background = '';
            });
        });
    }

    input.addEventListener('input', function() {
        clearTimeout(_acTimer);
        var q = input.value.trim();
        if (!q) { hideAc(); return; }
        _acTimer = setTimeout(async function() {
            var res = await apiCall('search_users', { query: q });
            if (input.value.trim() !== q) return; // stale
            showAcResults(res && res.users);
        }, 180);
    });

    input.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            e.stopPropagation();
            var active = ac.querySelector('.ac-item[data-active]');
            if (active) {
                input.value = active.getAttribute('data-id');
            }
            hideAc();
            groupAddMember();
            return;
        }
        if (ac.style.display === 'none') return;
        var items = ac.querySelectorAll('.ac-item');
        var active = ac.querySelector('.ac-item[data-active]');
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            var next = active ? active.nextElementSibling : items[0];
            if (active) { active.removeAttribute('data-active'); active.style.background = ''; }
            if (next) { next.setAttribute('data-active', '1'); next.style.background = 'var(--bg-hover, rgba(0,0,0,0.07))'; }
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            var prev = active ? active.previousElementSibling : items[items.length - 1];
            if (active) { active.removeAttribute('data-active'); active.style.background = ''; }
            if (prev) { prev.setAttribute('data-active', '1'); prev.style.background = 'var(--bg-hover, rgba(0,0,0,0.07))'; }
        } else if (e.key === 'Escape') {
            hideAc();
        }
    });

    input.addEventListener('blur', function() {
        setTimeout(hideAc, 150);
    });
}

async function groupAddMember() {
    if (!_currentGroup) return;
    var root = _groupDetailOverlay || document;
    var el = root.querySelector('#group-new-member-id');
    if (!el) return;
    var userId = el.value.trim();
    if (!userId) { el.focus(); return; }
    var res = await apiCall('group_add_member', {
        group_id: _currentGroup.id,
        user_id: userId
    });
    if (res && res.success) {
        el.value = '';
        await showGroupDetail(_currentGroup.id);
    } else {
        showMessageBox({ title: '', text: (res && res.error) || 'Error' });
    }
}

async function groupRemoveMember(userId) {
    if (!_currentGroup) return;
    var L = i18n[currentLanguage];
    var confirmed = await showConfirmDialog(
        L['settings.group_remove_member_confirm_title'],
        L['settings.group_remove_member_confirm_text'],
        { yesStyle: 'danger' }
    );
    if (!confirmed) return;
    var res = await apiCall('group_remove_member', {
        group_id: _currentGroup.id,
        user_id: userId
    });
    if (res && res.success) {
        await showGroupDetail(_currentGroup.id);
    } else {
        var L = i18n[currentLanguage];
        var msg = (res && res.error === 'last_admin')
            ? L['settings.group_last_admin_error']
            : ((res && res.error) || 'Error');
        showMessageBox({ title: '', text: msg });
    }
}

async function groupGrantAdmin(userId) {
    if (!_currentGroup) return;
    var res = await apiCall('group_grant_admin', {
        group_id: _currentGroup.id,
        user_id: userId
    });
    if (res && res.success) {
        await showGroupDetail(_currentGroup.id);
    } else {
        showMessageBox({ title: '', text: (res && res.error) || 'Error' });
    }
}

async function groupRevokeAdmin(userId) {
    if (!_currentGroup) return;
    var res = await apiCall('group_revoke_admin', {
        group_id: _currentGroup.id,
        user_id: userId
    });
    if (res && res.success) {
        await showGroupDetail(_currentGroup.id);
    } else {
        var L = i18n[currentLanguage];
        var msg = (res && res.error === 'last_admin')
            ? L['settings.group_last_admin_error']
            : ((res && res.error) || 'Error');
        showMessageBox({ title: '', text: msg });
    }
}

async function groupApproveRequest(userId) {
    if (!_currentGroup) return;
    var res = await apiCall('group_approve_request', {
        group_id: _currentGroup.id,
        user_id: userId
    });
    if (res && res.success) {
        await showGroupDetail(_currentGroup.id);
    } else {
        showMessageBox({ title: '', text: (res && res.error) || 'Error' });
    }
}

async function groupRejectRequest(userId) {
    if (!_currentGroup) return;
    var res = await apiCall('group_reject_request', {
        group_id: _currentGroup.id,
        user_id: userId
    });
    if (res && res.success) {
        await _renderJoinRequestsList();
    } else {
        showMessageBox({ title: '', text: (res && res.error) || 'Error' });
    }
}

// ============================================================================
// Startup: show pending join request notification
// ============================================================================
function showGroupJoinRequests(data) {
    var requests = data.requests || [];
    if (requests.length === 0) return;

    var L = i18n[currentLanguage];
    var lines = requests.map(function(r) {
        return _escHtml(r.display_name)
            + (r.user_id !== r.display_name ? ' (' + _escHtml(r.user_id) + ')' : '')
            + ' → ' + _escHtml(r.group_name);
    });

    var text = L['settings.group_startup_requests_text']
        + '<ul style="margin:8px 0 0 0;padding-left:18px;">'
        + lines.map(function(l) { return '<li style="font-size:12px;margin-bottom:2px;">' + l + '</li>'; }).join('')
        + '</ul>';

    // Use showMessageBox with custom HTML body via innerHTML trick:
    // Build a simple inline dialog since msgbox only supports plain text.
    _showGroupRequestsDialog(L['settings.group_startup_requests_title'], text,
        L['settings.group_startup_requests_action']);
}

function _showGroupRequestsDialog(title, bodyHtml, actionLabel) {
    var L = i18n[currentLanguage];
    var overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;'
        + 'background:rgba(0,0,0,0.5);z-index:10700;display:flex;'
        + 'align-items:center;justify-content:center;';

    var box = document.createElement('div');
    box.style.cssText = 'background:var(--bg-secondary);border:1px solid var(--border-color);'
        + 'border-radius:8px;padding:24px;min-width:320px;max-width:440px;';
    box.innerHTML = '<div style="font-size:15px;font-weight:600;color:var(--text-primary);margin-bottom:12px;">'
        + _escHtml(title) + '</div>'
        + '<div style="font-size:13px;color:var(--text-secondary);margin-bottom:20px;line-height:1.5;">'
        + bodyHtml + '</div>'
        + '<div style="display:flex;justify-content:flex-end;">'
        + '<button id="grp-req-cancel" class="btn btn-secondary" style="font-size:13px;padding:6px 14px;margin-right:8px;">'
        + L['dialog.cancel'] + '</button>'
        + '<button id="grp-req-ok" class="btn btn-primary" style="font-size:13px;padding:6px 14px;">'
        + _escHtml(actionLabel) + '</button>'
        + '</div>';

    overlay.appendChild(box);
    document.body.appendChild(overlay);

    document.getElementById('grp-req-cancel').onclick = function() {
        document.body.removeChild(overlay);
    };
    document.getElementById('grp-req-ok').onclick = function() {
        document.body.removeChild(overlay);
        showPage('settings');
        // Scroll to groups section after a brief delay
        setTimeout(function() {
            var el = document.getElementById('settings-groups-section');
            if (el) el.scrollIntoView({ behavior: 'smooth' });
            loadGroups();
        }, 150);
    };
}

// ============================================================================
// Utilities
// ============================================================================
function _escHtml(s) {
    if (!s) return '';
    return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function _escAttr(s) {
    if (!s) return '';
    return String(s).replace(/'/g, '&#39;').replace(/"/g, '&quot;');
}
