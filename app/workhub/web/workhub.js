/* WorkHub UI logic */
(function () {
    'use strict';

    // -----------------------------------------------------------------------
    // i18n
    // -----------------------------------------------------------------------
    var currentLanguage = 'en';

    var i18n = {
        en: {
            newDoc: 'New',
            tmplNote: 'Note',
            tmplCommand: 'Command Note',
            tmplTodo: 'TODO',
            tmplChecklist: 'Checklist',
            filterAll: 'All',
            visMe: 'Private',
            visGroup: 'Group',
            visAll: 'Public',
            colTitle: 'Title',
            noDoc: 'No documents.',
            searchPlaceholder: 'Search or type / for commands...',
            docIdLabel: 'Shortcut',
            docNotFound: 'Document not found.',
            myDocs: 'My documents',
            send: 'Send',
            searchResult: 'Results: "{q}"',
            closeSearch: 'X Close',
            noSearchResult: 'No results found.',
            noDocYet: 'No documents yet.',
            untitled: '(untitled)',
            backToList: 'Back',
            author: 'Author: ',
            share: 'Share',
            delete: 'Delete',
            visibilityLabel: 'Visibility',
            selectGroup: 'Select Group',
            shareTitle: 'Share Settings',
            cancel: 'Cancel',
            confirm: 'OK',
            titlePlaceholder: 'Title',
            noteBodyPlaceholder: 'Enter content...',
            commandLabel: 'Command:',
            commandPlaceholder: 'Enter command...',
            copy: 'Copy',
            copied: 'Copied.',
            linkDoc: 'Link',
            linkDialogTitle: 'Document Links',
            linkedDocs: 'Linked Documents',
            noLinkedDocs: 'No linked documents.',
            addLink: 'Add Link',
            recentDocs: 'Recent Documents',
            docIdInputPlaceholder: 'Enter document ID and press Enter',
            linkSelf: 'Cannot link to yourself.',
            linkAlready: 'Already linked.',
            linkNotFound: 'Document not found.',
            linkForbidden: 'No permission for this document.',
            linkFail: 'Failed to link.',
            run: 'Run',
            runNoTerminal: 'No terminal emulator found.',
            runVarPrompt: 'Enter value for ${var}:',
            runVarConfirm: 'Run',
            runVarCancel: 'Cancel',
            descLabel: 'Description:',
            descPlaceholder: 'Command description...',
            addItem: '+ Add item',
            todoItemPlaceholder: 'Enter item...',
            addStep: '+ Add step',
            resetAll: 'Reset all',
            stepPlaceholder: 'Enter step...',
            tagPlaceholder: 'Tag...',
            tags: 'Tags',
            forbidden: 'No permission for this document.',
            docDeleted: 'Document has been deleted.',
            backBtn: 'Back to list',
            conflictTitle: '{editor} edited this document.',
            conflictTitleUnknown: 'Someone edited this document.',
            conflictMsg: 'Load latest version?',
            editedToast: '{editor} edited this document.',
            editedToastUnknown: 'This document was updated.',
            itemDeleteConfirm: 'Delete this item?',
            deleteConfirmTitle: 'Delete this document?',
            onlyOwnerDelete: 'Only the owner can delete.',
            historyLatest: 'Latest',
            historyLoadFail: 'Failed to load history.',
            noHistory: 'No saved history.',
            historyView: 'View',
            historyCompareCurrent: 'Compare with Current',
            historyComparePrev: 'Compare with Previous',
            diffExit: 'Exit Diff',
            diffCurrent: 'Current',
            historyApply: 'Apply',
            historyApplyConfirm: 'Overwrite with this history?',
            historyTitle: 'History',
            close: 'Close',
            justNow: 'just now',
            minutesAgo: '{n}m ago',
            hoursAgo: '{n}h ago',
            actionHistoryTitle: 'Action History',
            actionHistoryEmpty: 'No action history.',
            actionCreate: 'Created',
            actionEdit: 'Edited',
            actionDelete: 'Deleted',
            actionCopy: 'Copied',
            actionLinkAdd: 'Link added',
            actionLinkRemove: 'Link removed',
            actionTag: 'Tags updated',
            actionShare: 'Sharing changed',
            actionDiff: 'diff',
            actionHistoryToday: 'Today',
            actionHistoryYesterday: 'Yesterday',
            actionHistoryDaysAgo: '{n} days ago',
        },
        ko: {
            newDoc: '새 작업',
            tmplNote: '메모',
            tmplCommand: '커맨드 노트',
            tmplTodo: 'TODO',
            tmplChecklist: '체크리스트',
            filterAll: '모두',
            visMe: '비공개',
            visGroup: '그룹공유',
            visAll: '전체공유',
            colTitle: '제목',
            noDoc: '문서가 없습니다.',
            searchPlaceholder: '검색하거나 /로 명령하세요...',
            docIdLabel: '바로가기',
            docNotFound: '문서를 찾을 수 없습니다.',
            myDocs: '내 문서',
            send: '전송',
            searchResult: '검색 결과: "{q}"',
            closeSearch: 'X 닫기',
            noSearchResult: '검색 결과가 없습니다.',
            noDocYet: '아직 작성된 문서가 없습니다.',
            untitled: '(제목 없음)',
            backToList: '목록으로',
            author: '작성자: ',
            share: '공유',
            delete: '삭제',
            visibilityLabel: '공개 범위',
            selectGroup: '그룹 선택',
            shareTitle: '공유 설정',
            cancel: '취소',
            confirm: '확인',
            titlePlaceholder: '제목',
            noteBodyPlaceholder: '내용을 입력하세요...',
            commandLabel: '커맨드:',
            commandPlaceholder: '명령어 입력...',
            copy: '복사',
            copied: '복사되었습니다.',
            run: '실행',
            runNoTerminal: '터미널 에뮬레이터를 찾을 수 없습니다.',
            runVarPrompt: '${var} 값을 입력하세요:',
            runVarConfirm: '실행',
            runVarCancel: '취소',
            descLabel: '설명:',
            descPlaceholder: '커맨드 설명...',
            addItem: '+ 항목 추가',
            todoItemPlaceholder: '항목 입력...',
            addStep: '+ 단계 추가',
            resetAll: '전체 초기화',
            stepPlaceholder: '단계 설명...',
            tagPlaceholder: '태그...',
            tags: '태그',
            forbidden: '이 문서에 대한 접근 권한이 없습니다.',
            docDeleted: '문서가 삭제되었습니다.',
            backBtn: '목록으로',
            conflictTitle: '{editor}이(가) 이 문서를 수정했습니다.',
            conflictTitleUnknown: '다른 사람이 이 문서를 수정했습니다.',
            conflictMsg: '최신 내용을 불러오겠습니까?',
            editedToast: '{editor}이(가) 문서를 수정했습니다.',
            editedToastUnknown: '문서가 수정되었습니다.',
            itemDeleteConfirm: '이 항목을 삭제하시겠습니까?',
            deleteConfirmTitle: '이 문서를 삭제하시겠습니까?',
            onlyOwnerDelete: '본인 문서만 삭제할 수 있습니다.',
            historyLatest: '최신',
            historyLoadFail: '히스토리를 불러올 수 없습니다.',
            noHistory: '저장된 히스토리가 없습니다.',
            historyView: '보기',
            historyCompareCurrent: '현재와 비교',
            historyComparePrev: '직전과 비교',
            diffExit: 'diff 종료',
            diffCurrent: '현재',
            historyApply: '반영',
            historyApplyConfirm: '이 히스토리 내용으로 덮어쓰겠습니까?',
            historyTitle: '히스토리',
            close: '닫기',
            copyDoc: '복사',
            copyDocConfirm: '이 문서를 복사하겠습니까?',
            copyDocFail: '문서 복사에 실패했습니다.',
            linkDoc: '연결',
            linkDialogTitle: '문서 연결',
            linkedDocs: '연결된 문서',
            noLinkedDocs: '연결된 문서가 없습니다.',
            addLink: '연결 추가',
            recentDocs: '최근 문서',
            docIdInputPlaceholder: '문서 ID 입력 후 Enter',
            linkSelf: '자신의 문서는 연결할 수 없습니다.',
            linkAlready: '이미 연결된 문서입니다.',
            linkNotFound: '문서를 찾을 수 없습니다.',
            linkForbidden: '접근 권한이 없는 문서입니다.',
            linkFail: '연결에 실패했습니다.',
            justNow: '방금 전',
            minutesAgo: '{n}분 전',
            hoursAgo: '{n}시간 전',
            actionHistoryTitle: '작업 히스토리',
            actionHistoryEmpty: '작업 이력이 없습니다.',
            actionCreate: '생성',
            actionEdit: '수정',
            actionDelete: '삭제',
            actionCopy: '복사',
            actionLinkAdd: '연결 추가',
            actionLinkRemove: '연결 해제',
            actionTag: '태그 수정',
            actionShare: '공유 변경',
            actionDiff: 'diff',
            actionHistoryToday: '오늘',
            actionHistoryYesterday: '어제',
            actionHistoryDaysAgo: '{n}일 전',
        },
    };

    function t(key) {
        return (i18n[currentLanguage] || i18n.en)[key] || key;
    }

    function getFilterOptions() {
        return [
            { value: '',           label: t('filterAll') },
            { value: 'note',       label: t('tmplNote') },
            { value: 'command',    label: t('tmplCommand') },
            { value: 'todo',       label: t('tmplTodo') },
            { value: 'checklist',  label: t('tmplChecklist') },
        ];
    }

    // -----------------------------------------------------------------------
    // State
    // -----------------------------------------------------------------------
    var state = {
        view: 'list',
        currentId: null,
        currentTemplate: 'note',
        isDirty: false,
        dirtyTitle: false,
        dirtyBody: false,
        dirtyTags: false,
        baseTitle: '',
        baseBody: '',
        baseTags: '',
        hasInserted: false,
        createInFlight: false,
        saveDebounce: null,
        searchQuery: '',
        isSearchMode: false,
        filterTemplate: '',
        listItems: [],
        // user/share state
        currentVersion: 1,
        currentOwnerId: '',
        currentVisibility: 'all',
        currentGroupId: null,
        ownerWriteOnly: 1,
        isOwner: true,
        isNewDraft: false,
        currentUserId: '',
        currentUserGroups: [],   // [{id, name}, ...]
        // notify polling
        pollTimer: null,
        pollMtime: 0,
        pollConflictShown: false,
        pollGen: 0,
        // history
        bodyAtOpen: null,
        lastEditedAt: null,
        historySaved: false,
        historyMode: false,
        historyViewId: null,
        historyPreBody: null,
        historyPreTitle: null,
        historyPreTags: null,
        // diff mode
        diffMode: false,
        diffOldBody: null,
        diffNewBody: null,
        diffOldLabel: '',
        diffNewLabel: '',
        diffOldTitle: null,
        diffNewTitle: null,
        diffPreBody: null,
        diffPreTitle: null,
        diffPreTags: null,
        // header
        headerExpanded: false,
        // 2.5차: mention map {id -> {display_name, avatar_small, avatar_mime}}
        mentionMap: {},
        // 2.5차: doc link map {id -> {title, template}}
        docLinkMap: {},
        // search input history (persisted to config)
        searchHistory: [],
        // sticky (pinned) document IDs (persisted to config)
        stickyIds: [],
    };

    var PIN_ICON_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 17v5"/><path d="M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1z"/></svg>';
    var CHEVRON_LEFT_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" width="14" height="14"><polyline points="15 18 9 12 15 6"/></svg>';
    var CHEVRON_RIGHT_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" width="14" height="14"><polyline points="9 18 15 12 9 6"/></svg>';
    var SHARE_ICON_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>';
    var DELETE_ICON_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>';
    var CLOCK_ICON_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15 15"/></svg>';
    var COPY_DOC_ICON_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
    var LINK_ICON_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>';

    // -----------------------------------------------------------------------
    // Bootstrap
    // -----------------------------------------------------------------------
    function bootstrap() {
        if (window.callPythonReady) {
            init();
        } else {
            window.addEventListener('callPythonReady', init, { once: true });
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bootstrap);
    } else {
        bootstrap();
    }

    document.addEventListener('visibilitychange', function () {
        if (document.visibilityState === 'hidden' && state.view === 'edit') {
            saveHistoryOnLeave();
        }
    });

    function focusSearchInput() {
        var inp = document.getElementById('wh-search-input');
        if (inp) inp.focus();
    }

    window.skillupRequestFocus = focusSearchInput;

    window.addEventListener('message', function (e) {
        if (e.data && e.data.action === 'requestFocus') {
            focusSearchInput();
            return;
        }
        if (e.data && e.data.type === 'appWillClose' && state.view === 'edit') {
            if (!state.currentId || !state.hasInserted) return;
            var body = collectBody();
            if (body === '' || body === state.bodyAtOpen) return;
            var guid = window.skillupAppGuid;
            if (!guid) return;
            // flush save: isNewDraft 해제, 최종 공유 설정으로 저장
            state.isNewDraft = false;
            e.source.postMessage({
                type: 'appWillCloseSave',
                guid: guid,
                action: 'work_save',
                payload: {
                    id: state.currentId,
                    title: collectTitle(),
                    body: body,
                    skip_body: true,
                    tags: collectTags(),
                    visibility: state.currentVisibility,
                    group_id: state.currentGroupId,
                    owner_write_only: state.ownerWriteOnly,
                    version: state.currentVersion,
                    history_body: body,
                    history_title: collectTitle(),
                }
            }, '*');
        }
    });

    function init() {
        renderApp();
        focusSearchInput();
        callPython('search_history_load', {}).then(function (res) {
            if (res && res.success && Array.isArray(res.items)) {
                state.searchHistory = res.items;
            }
        });
        var stickyPromise = callPython('sticky_load', {}).then(function (res) {
            if (res && res.success && Array.isArray(res.items)) {
                state.stickyIds = res.items;
            }
        });
        callPython('user_info', {}).then(function (res) {
            if (res && res.success) {
                state.currentUserId = res.user_id;
                state.currentUserGroups = res.groups || [];
            }
            stickyPromise.then(loadList);
        });
        callPython('account_list', {}).then(function (res) {
            if (!res || !res.success) return;
            var map = {};
            (res.accounts || []).forEach(function (a) {
                map[a.id] = { display_name: a.display_name, avatar_small: a.avatar_small, avatar_mime: a.avatar_mime };
            });
            state.mentionMap = map;
        });
    }

    // -----------------------------------------------------------------------
    // Render skeleton
    // -----------------------------------------------------------------------
    function renderApp() {
        document.body.innerHTML = '';
        var layout = el('div', { id: 'wh-layout', className: 'wh-layout' });

        var listView = el('div', { id: 'wh-list-view' });
        listView.appendChild(buildListHeader());
        listView.appendChild(buildColumnHeader());
        listView.appendChild(el('div', { id: 'wh-list', className: 'wh-list' }));
        listView.appendChild(buildSearchBar());

        var editView = el('div', { id: 'wh-edit-view' });
        editView.style.display = 'none';
        editView.appendChild(el('div', { id: 'wh-edit-header', className: 'wh-edit-header' }));
        editView.appendChild(el('div', { id: 'wh-edit-body', className: 'wh-edit-body' }));

        layout.appendChild(listView);
        layout.appendChild(editView);
        document.body.appendChild(layout);
    }

    function buildListHeader() {
        var header = el('div', { className: 'wh-header' });
        var label = el('h6');
        label.textContent = t('newDoc');
        header.appendChild(label);

        var btnRow = el('div', { className: 'wh-template-btns' });
        [['note', t('tmplNote')], ['command', t('tmplCommand')], ['todo', t('tmplTodo')], ['checklist', t('tmplChecklist')]].forEach(function (pair) {
            var btn = el('button', { className: 'btn btn-outline-secondary btn-sm wh-tmpl-btn' });
            btn.appendChild(makeIcon(pair[0], 16));
            var labelEl = el('span');
            labelEl.textContent = pair[1];
            btn.appendChild(labelEl);
            btn.addEventListener('click', function () { startNewDoc(pair[0]); });
            btnRow.appendChild(btn);
        });
        header.appendChild(btnRow);
        return header;
    }

    function buildColumnHeader() {
        var bar = el('div', { className: 'wh-col-header', id: 'wh-col-header' });
        bar.appendChild(buildColumnHeaderContent());
        return bar;
    }

    function buildColumnHeaderContent() {
        var frag = document.createDocumentFragment();

        var trigger = el('button', { className: 'wh-filter-trigger', id: 'wh-filter-trigger' });
        renderFilterTrigger(trigger, state.filterTemplate);
        trigger.addEventListener('click', function (e) {
            e.stopPropagation();
            toggleFilterMenu();
        });
        frag.appendChild(trigger);

        var titleCol = el('div', { className: 'wh-col-title-label' });
        titleCol.textContent = t('colTitle');
        frag.appendChild(titleCol);

        return frag;
    }

    function renderFilterTrigger(btn, value) {
        btn.innerHTML = '';
        var opts = getFilterOptions();
        var opt = opts.find(function (o) { return o.value === value; }) || opts[0];
        btn.appendChild(makeIcon(opt.value, 28));
    }

    function toggleFilterMenu() {
        var existing = document.getElementById('wh-filter-menu');
        if (existing) { existing.remove(); return; }

        var trigger = document.getElementById('wh-filter-trigger');
        var menu = el('div', { className: 'wh-filter-menu', id: 'wh-filter-menu' });

        getFilterOptions().forEach(function (opt) {
            var item = el('button', { className: 'wh-filter-item wh-tmpl-btn' + (opt.value === state.filterTemplate ? ' active' : '') });
            item.appendChild(makeIcon(opt.value, 16));
            var lbl = el('span');
            lbl.textContent = opt.label;
            item.appendChild(lbl);
            item.addEventListener('click', function () {
                state.filterTemplate = opt.value;
                renderFilterTrigger(trigger, opt.value);
                menu.remove();
                applyFilter();
            });
            menu.appendChild(item);
        });

        var rect = trigger.getBoundingClientRect();
        menu.style.top = rect.bottom + 'px';
        menu.style.left = rect.left + 'px';
        document.body.appendChild(menu);

        function onOutside(e) {
            if (!menu.contains(e.target) && e.target !== trigger) {
                menu.remove();
                document.removeEventListener('click', onOutside);
            }
        }
        setTimeout(function () { document.addEventListener('click', onOutside); }, 0);
    }

    function applyFilter() {
        var items = state.listItems;
        if (state.filterTemplate) {
            items = items.filter(function (it) { return it.template === state.filterTemplate; });
        }
        items = sortStickyFirst(items);
        var listEl = document.getElementById('wh-list');
        listEl.innerHTML = '';
        if (!items || items.length === 0) {
            var empty = el('div', { className: 'wh-empty' });
            empty.textContent = t('noDoc');
            listEl.appendChild(empty);
            return;
        }
        items.forEach(function (item) { listEl.appendChild(buildListItem(item)); });
    }

    var SLASH_COMMANDS = [
        { cmd: 'go',      hint: '<id>', desc: { en: 'Jump to document by ID', ko: '문서 ID로 바로가기' } },
        { cmd: 'my',      hint: '',     desc: { en: 'Show my documents',       ko: '내 문서 보기' } },
        { cmd: 'history', hint: '',     desc: { en: 'Show action history',     ko: '작업 이력 보기' } },
    ];

    function buildSearchBar() {
        var bar = el('div', { className: 'wh-search-bar', id: 'wh-search-bar' });
        var inputWrap = el('div', { className: 'wh-search-input-wrap' });
        var input = el('input', { type: 'text', placeholder: t('searchPlaceholder'), id: 'wh-search-input' });
        var dropdown = el('div', { className: 'wh-cmd-dropdown', id: 'wh-cmd-dropdown' });
        dropdown.style.display = 'none';

        var selectedIdx = -1;

        // input history (backed by state.searchHistory, persisted to config)
        var historyIdx = -1;
        var historyDraft = '';

        function getMatchedCmds(val) {
            if (!val.startsWith('/')) return [];
            var typed = val.slice(1).toLowerCase();
            return SLASH_COMMANDS.filter(function (c) {
                return c.cmd.indexOf(typed) === 0;
            });
        }

        function renderDropdown(matches) {
            dropdown.innerHTML = '';
            selectedIdx = -1;
            if (matches.length === 0) {
                dropdown.style.display = 'none';
                return;
            }
            matches.forEach(function (c, i) {
                var row = el('div', { className: 'wh-cmd-row' });
                row.dataset.idx = i;
                var cmdSpan = el('span', { className: 'wh-cmd-name' });
                cmdSpan.textContent = '/' + c.cmd;
                var hintSpan = el('span', { className: 'wh-cmd-hint' });
                hintSpan.textContent = c.hint;
                var descSpan = el('span', { className: 'wh-cmd-desc' });
                descSpan.textContent = c.desc[currentLanguage] || c.desc.en;
                row.appendChild(cmdSpan);
                row.appendChild(hintSpan);
                row.appendChild(descSpan);
                row.addEventListener('mousedown', function (e) {
                    e.preventDefault();
                    applyCommand(c);
                });
                dropdown.appendChild(row);
            });
            dropdown.style.display = 'block';
        }

        function applyCommand(c) {
            input.value = '/' + c.cmd + ' ';
            dropdown.style.display = 'none';
            selectedIdx = -1;
            input.focus();
        }

        function highlightRow(idx) {
            var rows = dropdown.querySelectorAll('.wh-cmd-row');
            rows.forEach(function (r, i) {
                if (i === idx) r.classList.add('wh-cmd-row--active');
                else r.classList.remove('wh-cmd-row--active');
            });
        }

        input.addEventListener('input', function () {
            var matches = getMatchedCmds(input.value);
            renderDropdown(matches);
        });

        input.addEventListener('keydown', function (e) {
            var isOpen = dropdown.style.display !== 'none';
            if (isOpen) {
                var rows = dropdown.querySelectorAll('.wh-cmd-row');
                if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    selectedIdx = (selectedIdx + 1) % rows.length;
                    highlightRow(selectedIdx);
                    return;
                }
                if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    selectedIdx = (selectedIdx - 1 + rows.length) % rows.length;
                    highlightRow(selectedIdx);
                    return;
                }
                if (e.key === 'Tab' || (e.key === 'Enter' && selectedIdx >= 0)) {
                    e.preventDefault();
                    var matches = getMatchedCmds(input.value);
                    var target = selectedIdx >= 0 ? matches[selectedIdx] : matches[0];
                    if (target) applyCommand(target);
                    return;
                }
                if (e.key === 'Escape') {
                    dropdown.style.display = 'none';
                    selectedIdx = -1;
                    return;
                }
            }
            if (!isOpen) {
                if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    if (state.searchHistory.length === 0) return;
                    if (historyIdx === -1) {
                        historyDraft = input.value;
                        historyIdx = state.searchHistory.length - 1;
                    } else if (historyIdx > 0) {
                        historyIdx--;
                    }
                    input.value = state.searchHistory[historyIdx];
                    return;
                }
                if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    if (historyIdx === -1) return;
                    if (historyIdx < state.searchHistory.length - 1) {
                        historyIdx++;
                        input.value = state.searchHistory[historyIdx];
                    } else {
                        historyIdx = -1;
                        input.value = historyDraft;
                    }
                    return;
                }
            }
            if (e.key === 'Enter') {
                if (input.value.trim()) {
                    var v = input.value;
                    if (state.searchHistory.length === 0 || state.searchHistory[state.searchHistory.length - 1] !== v) {
                        state.searchHistory.push(v);
                        if (state.searchHistory.length > 64) state.searchHistory.shift();
                        callPython('search_history_save', { items: state.searchHistory });
                    }
                    historyIdx = -1;
                    historyDraft = '';
                }
                doSearch();
            }
        });

        input.addEventListener('blur', function () {
            dropdown.style.display = 'none';
            selectedIdx = -1;
        });

        document.addEventListener('click', function (e) {
            var wrap = document.getElementById('wh-cmd-dropdown');
            var inp = document.getElementById('wh-search-input');
            if (!wrap || !inp) return;
            if (!wrap.contains(e.target) && e.target !== inp) {
                wrap.style.display = 'none';
                selectedIdx = -1;
            }
        });

        inputWrap.appendChild(input);
        inputWrap.appendChild(dropdown);

        var btn = el('button', { className: 'btn btn-sm btn-primary' });
        btn.textContent = t('send');
        btn.addEventListener('click', doSearch);
        bar.appendChild(inputWrap);
        bar.appendChild(btn);
        return bar;
    }

    // -----------------------------------------------------------------------
    // Sticky helpers
    // -----------------------------------------------------------------------
    function isSticky(id) {
        return state.stickyIds.indexOf(id) !== -1;
    }

    function sortStickyFirst(items) {
        return items.slice().sort(function (a, b) {
            var pa = isSticky(a.id) ? 0 : 1;
            var pb = isSticky(b.id) ? 0 : 1;
            return pa - pb;
        });
    }

    function toggleSticky(id) {
        var idx = state.stickyIds.indexOf(id);
        if (idx !== -1) {
            state.stickyIds.splice(idx, 1);
        } else {
            state.stickyIds.push(id);
        }
        callPython('sticky_save', { items: state.stickyIds });
    }

    // -----------------------------------------------------------------------
    // List view
    // -----------------------------------------------------------------------
    function loadList() {
        callPython('work_list', {}).then(function (res) {
            if (!res || !res.success) return;
            if (res.current_user_id) state.currentUserId = res.current_user_id;
            state.listItems = res.items || [];
            renderList(res.items, false, '');
        });
    }

    function renderList(items, isSearch, query, sortSticky) {
        var listEl = document.getElementById('wh-list');
        var colHeader = document.getElementById('wh-col-header');

        if (isSearch) {
            colHeader.innerHTML = '';
            var span = el('span', { className: 'wh-search-result-label' });
            span.textContent = t('searchResult').replace('{q}', query);
            var closeBtn = el('button', { className: 'btn btn-sm btn-outline-secondary' });
            closeBtn.textContent = t('closeSearch');
            closeBtn.addEventListener('click', clearSearch);
            colHeader.appendChild(span);
            colHeader.appendChild(closeBtn);
        } else {
            colHeader.innerHTML = '';
            colHeader.appendChild(buildColumnHeaderContent());
        }

        var filtered = items;
        if (!isSearch && state.filterTemplate) {
            filtered = items.filter(function (it) { return it.template === state.filterTemplate; });
        }
        if (!isSearch || sortSticky) {
            filtered = sortStickyFirst(filtered);
        }

        listEl.innerHTML = '';
        if (!filtered || filtered.length === 0) {
            var empty = el('div', { className: 'wh-empty' });
            empty.textContent = isSearch ? t('noSearchResult') : t('noDocYet');
            listEl.appendChild(empty);
            return;
        }

        filtered.forEach(function (item) {
            listEl.appendChild(buildListItem(item));
        });
    }

    // SVG icon for "all types" — 2x2 grid of small squares
    var ICON_ALL = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>';

    var TEMPLATE_SVG = {
        note: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="16" rx="2"/><line x1="8" y1="9" x2="16" y2="9"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="13" y2="17"/></svg>',
        command: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="6,9 11,12 6,15"/><line x1="13" y1="15" x2="18" y2="15"/></svg>',
        todo: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="7" height="7" rx="1" stroke-width="1.2"/><polyline points="5.5,7.5 7,9 9.5,6"/><line x1="14" y1="7" x2="20" y2="7"/><rect x="4" y="13" width="7" height="7" rx="1" stroke-width="1.2"/><line x1="14" y1="16" x2="20" y2="16"/></svg>',
        checklist: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="4,12 8,16 14,8"/><line x1="17" y1="12" x2="21" y2="12"/></svg>',
    };

    function makeIcon(template, size) {
        var svgStr = template === '' ? ICON_ALL : (TEMPLATE_SVG[template] || TEMPLATE_SVG.note);
        var cls = template === '' ? 'wh-type-icon wh-type-icon--all' : 'wh-type-icon wh-type-icon--' + template;
        var span = el('span', { className: cls });
        span.style.width = size + 'px';
        span.style.height = size + 'px';
        span.innerHTML = svgStr.replace('<svg ', '<svg width="' + size + '" height="' + size + '" ');
        return span;
    }

    function buildListItem(item) {
        var row = el('div', { className: 'wh-list-item' + (isSticky(item.id) ? ' wh-list-item--sticky' : '') });

        row.appendChild(makeIcon(item.template, 28));

        if (!item.is_owner && item.owner_display_name) {
            var authorChip = el('span', { className: 'wh-list-author' });
            if (item.owner_avatar_small) {
                var img = el('img');
                img.src = 'data:' + (item.owner_avatar_mime || 'image/jpeg') + ';base64,' + item.owner_avatar_small;
                img.style.cssText = 'width:16px;height:16px;border-radius:50%;vertical-align:middle;margin-right:3px;';
                authorChip.appendChild(img);
            }
            var nameEl = el('span');
            nameEl.textContent = item.owner_display_name;
            authorChip.appendChild(nameEl);
            row.appendChild(authorChip);
        }

        var title = el('div', { className: 'wh-list-title' });
        title.textContent = item.title || t('untitled');
        row.appendChild(title);

        var meta = el('div', { className: 'wh-list-meta' });

        var tagsWrap = el('div', { className: 'wh-list-tags' });
        if (item.tags) {
            item.tags.split(',').forEach(function (tg) {
                tg = tg.trim();
                if (!tg) return;
                var tag = el('span', { className: 'wh-tag' });
                tag.textContent = '#' + tg;
                tag.addEventListener('click', function (e) {
                    e.stopPropagation();
                    addTagToSearch(tg);
                });
                tagsWrap.appendChild(tag);
            });
        }
        meta.appendChild(tagsWrap);

        var date = el('div', { className: 'wh-list-date' });
        date.textContent = fmtDate(item.updated_at);
        meta.appendChild(date);

        row.appendChild(meta);

        var pinBtn = el('button', { className: 'wh-pin-btn' + (isSticky(item.id) ? ' wh-pin-btn--active' : '') });
        pinBtn.innerHTML = PIN_ICON_SVG;
        pinBtn.addEventListener('click', function (e) {
            e.stopPropagation();
            toggleSticky(item.id);
            var pinned = isSticky(item.id);
            if (pinned) {
                pinBtn.classList.add('wh-pin-btn--active');
            } else {
                pinBtn.classList.remove('wh-pin-btn--active');
            }
            if (!state.isSearchMode) {
                renderList(state.listItems, false, '');
            }
        });
        row.appendChild(pinBtn);
        row.addEventListener('click', function () { openDoc(item.id); });
        return row;
    }

    // -----------------------------------------------------------------------
    // Edit view
    // -----------------------------------------------------------------------
    function startNewDoc(template) {
        state.currentId = null;
        state.currentTemplate = template;
        state.currentVersion = 1;
        state.currentOwnerId = state.currentUserId;
        state.currentVisibility = 'all';
        state.currentGroupId = null;
        state.ownerWriteOnly = 1;
        state.isOwner = true;
        state.isNewDraft = false;
        state.isDirty = false;
        state.dirtyTitle = false;
        state.dirtyBody = false;
        state.dirtyTags = false;
        state.baseTitle = '';
        state.baseBody = '';
        state.baseTags = '';
        state.hasInserted = false;
        state.createInFlight = false;
        state.bodyAtOpen = null;
        state.lastEditedAt = null;
        state.historySaved = false;
        state.historyMode = false;
        state.historyViewId = null;
        state.historyPreBody = null;
        state.historyPreTitle = null;
        state.historyPreTags = null;
        state.diffMode = false;
        state.diffOldBody = null;
        state.diffNewBody = null;
        state.diffOldLabel = '';
        state.diffNewLabel = '';
        state.diffOldTitle = null;
        state.diffNewTitle = null;
        state.diffPreBody = null;
        state.diffPreTitle = null;
        state.diffPreTags = null;
        showEditView({ id: null, title: '', template: template, body: defaultBody(template), tags: '' });
    }

    function openDoc(id, opts) {
        callPython('work_get', { id: id }).then(function (res) {
            if (!res || !res.success) {
                if (res && res.error === 'not_found') { handleDeleted(); return; }
                if (res && res.error === 'forbidden') {
                    showToast(t('forbidden'));
                    backToList();
                }
                return;
            }
            var item = res.item;
            state.currentId = item.id;
            state.currentTemplate = item.template;
            state.currentVersion = item.version || 1;
            state.currentOwnerId = item.owner_id || '';
            state.currentVisibility = item.visibility || 'me';
            state.currentGroupId = item.group_id || null;
            state.ownerWriteOnly = (item.owner_write_only !== undefined) ? item.owner_write_only : 1;
            state.isOwner = !!item.is_owner;
            state.isNewDraft = false;
            state.isDirty = false;
            state.dirtyTitle = false;
            state.dirtyBody = false;
            state.dirtyTags = false;
            state.baseTitle = item.title || '';
            state.baseBody = item.body || '';
            state.baseTags = item.tags || '';
            state.hasInserted = true;
            if (!(opts && opts.isPollRefresh)) {
                state.bodyAtOpen = item.body || '';
                state.lastEditedAt = null;
                state.historySaved = false;
                state.historyMode = false;
                state.historyViewId = null;
                state.historyPreBody = null;
                state.historyPreTitle = null;
                state.historyPreTags = null;
                state.diffMode = false;
                state.diffOldBody = null;
                state.diffNewBody = null;
                state.diffOldLabel = '';
                state.diffNewLabel = '';
                state.diffOldTitle = null;
                state.diffNewTitle = null;
                state.diffPreBody = null;
                state.diffPreTitle = null;
                state.diffPreTags = null;
            }
            showEditView(item, opts);
            startPoll(item.id);
            if (opts && typeof opts.afterOpen === 'function') {
                opts.afterOpen(item);
            }
        });
    }

    function defaultBody(template) {
        if (template === 'note') return JSON.stringify({ text: '' });
        if (template === 'command') return JSON.stringify({ command: '', description: '' });
        if (template === 'todo') return JSON.stringify({ items: [] });
        if (template === 'checklist') return JSON.stringify({ items: [] });
        return '';
    }

    function showEditView(item, opts) {
        state.view = 'edit';
        document.getElementById('wh-list-view').style.display = 'none';
        var editView = document.getElementById('wh-edit-view');
        editView.style.display = 'flex';
        editView.style.flexDirection = 'column';
        editView.style.flex = '1';
        editView.style.overflow = 'hidden';

        var header = document.getElementById('wh-edit-header');
        header.innerHTML = '';

        var backBtn = el('button', { className: 'wh-back-btn' });
        backBtn.innerHTML = CHEVRON_LEFT_SVG + t('backToList');
        backBtn.addEventListener('click', backToList);
        header.appendChild(backBtn);

        if (!state.diffMode) {
            // Toggle button (always visible, right after back button)
            header.appendChild(buildHeaderToggleBtn());
            // Collapsible group: tags, copy, link, delete
            header.appendChild(buildTagsBtn(item.tags || ''));
            if (item.id) {
                header.appendChild(buildCopyDocBtn());
                header.appendChild(buildLinkDocBtn());
                callPython('link_list', { id: item.id }).then(function (res) {
                    if (res && res.success) updateLinkBtnBadge((res.items || []).length);
                });
                if (state.isOwner) {
                    header.appendChild(buildDeleteBtn());
                }
            }
        }

        if (state.isOwner) {
            header.appendChild(buildVisibilityBtn());
        } else if (item.id) {
            var authorEl = el('span', { className: 'wh-author-label' });
            authorEl.textContent = t('author') + (item.owner_display_name || state.currentOwnerId);
            header.appendChild(authorEl);
        }
        if (state.diffMode) {
            header.appendChild(buildDiffExitBtn());
        } else if (item.id) {
            header.appendChild(buildHistoryBtn());
        }

        // Template label at the far right
        var tmplLabel = el('span', { className: 'wh-template-label' });
        tmplLabel.appendChild(makeIcon(item.template, 14));
        var tmplText = el('span');
        tmplText.textContent = t('tmpl' + item.template.charAt(0).toUpperCase() + item.template.slice(1)) || item.template;
        tmplLabel.appendChild(tmplText);
        header.appendChild(tmplLabel);

        // Apply initial collapsed state
        if (!state.headerExpanded) {
            header.classList.add('wh-edit-header--collapsed');
        }

        var body = document.getElementById('wh-edit-body');
        body.innerHTML = '';
        if (state.diffMode) {
            body.style.overflowY = 'hidden';
            body.style.display = 'flex';
            body.style.flexDirection = 'column';
            buildDiffBody(body, state.diffOldBody, state.diffNewBody, state.currentTemplate, state.diffOldLabel, state.diffNewLabel);
        } else {
            body.style.overflowY = '';
            body.style.display = '';
            body.style.flexDirection = '';
            body.style.padding = '';
            var effectiveOpts = opts || {};
            if (!effectiveOpts.readonlyMode && !state.isOwner && state.ownerWriteOnly === 1) {
                effectiveOpts = Object.assign({}, effectiveOpts, { readonlyMode: true });
            }
            buildEditBody(body, item, effectiveOpts);
        }
    }

    // -----------------------------------------------------------------------
    // Tags toggle button
    // -----------------------------------------------------------------------
    function buildTagsBtn(tagsStr) {
        var tagCount = tagsStr ? tagsStr.split(',').map(function (s) { return s.trim(); }).filter(Boolean).length : 0;
        var btn = el('button', { className: 'wh-tags-btn wh-collapsible-btn', id: 'wh-tags-btn' });
        btn.appendChild(buildTagsBtnInner(tagCount));
        btn.addEventListener('click', function (e) {
            e.stopPropagation();
            toggleTagsRow();
        });
        return btn;
    }

    function buildTagsBtnInner(tagCount) {
        var frag = document.createDocumentFragment();
        var iconSpan = el('span', { className: 'wh-tags-btn-icon' });
        iconSpan.textContent = '#';
        var textSpan = el('span');
        textSpan.textContent = t('tags');
        frag.appendChild(iconSpan);
        frag.appendChild(textSpan);
        if (tagCount > 0) {
            var dot = el('span', { className: 'wh-tags-btn-dot' });
            frag.appendChild(dot);
        }
        return frag;
    }

    function toggleTagsRow() {
        var row = document.getElementById('wh-tags-row');
        var btn = document.getElementById('wh-tags-btn');
        if (!row) return;
        var isOpen = row.style.display !== 'none';
        if (isOpen) {
            closeTagsRow();
        } else {
            row.style.display = '';
            if (btn) btn.classList.add('wh-tags-btn--open');
            var inp = document.getElementById('wh-tag-input');
            if (inp) setTimeout(function () { inp.focus(); }, 0);
            setTimeout(function () {
                document.addEventListener('mousedown', onTagsOutside);
            }, 0);
        }
    }

    function closeTagsRow() {
        var row = document.getElementById('wh-tags-row');
        var btn = document.getElementById('wh-tags-btn');
        if (row) row.style.display = 'none';
        if (btn) btn.classList.remove('wh-tags-btn--open');
        document.removeEventListener('mousedown', onTagsOutside);
    }

    function onTagsOutside(e) {
        var row = document.getElementById('wh-tags-row');
        var btn = document.getElementById('wh-tags-btn');
        if (row && row.contains(e.target)) return;
        if (btn && btn.contains(e.target)) return;
        closeTagsRow();
    }

    function updateTagsBtnBadge() {
        var btn = document.getElementById('wh-tags-btn');
        if (!btn) return;
        var tags = collectTags();
        var tagCount = tags ? tags.split(',').map(function (s) { return s.trim(); }).filter(Boolean).length : 0;
        btn.innerHTML = '';
        btn.appendChild(buildTagsBtnInner(tagCount));
    }

    // -----------------------------------------------------------------------
    // Visibility - share button + dialog
    // -----------------------------------------------------------------------
    function buildVisibilityBtn() {
        var wrap = el('div', { className: 'wh-vis-wrap', id: 'wh-vis-wrap' });
        var btn = el('button', { className: 'wh-vis-btn', id: 'wh-vis-btn' });
        var iconSpan = el('span', { className: 'wh-vis-icon' });
        iconSpan.innerHTML = SHARE_ICON_SVG;
        var textSpan = el('span');
        textSpan.textContent = t('share');
        btn.appendChild(iconSpan);
        btn.appendChild(textSpan);
        btn.addEventListener('click', function (e) {
            e.stopPropagation();
            openSharingDialog();
        });
        wrap.appendChild(btn);
        return wrap;
    }

    function buildHeaderToggleBtn() {
        var btn = el('button', { className: 'wh-header-toggle-btn', id: 'wh-header-toggle-btn' });
        btn.innerHTML = state.headerExpanded ? CHEVRON_RIGHT_SVG : CHEVRON_LEFT_SVG;
        btn.addEventListener('click', function () {
            var header = document.getElementById('wh-edit-header');
            if (!header) return;
            state.headerExpanded = !state.headerExpanded;
            if (state.headerExpanded) {
                header.classList.remove('wh-edit-header--collapsed');
                btn.innerHTML = CHEVRON_RIGHT_SVG;
            } else {
                header.classList.add('wh-edit-header--collapsed');
                btn.innerHTML = CHEVRON_LEFT_SVG;
            }
        });
        return btn;
    }

    function buildDeleteBtn() {
        var btn = el('button', { className: 'wh-delete-btn wh-collapsible-btn' });
        var iconSpan = el('span', { className: 'wh-delete-icon' });
        iconSpan.innerHTML = DELETE_ICON_SVG;
        var textSpan = el('span');
        textSpan.textContent = t('delete');
        btn.appendChild(iconSpan);
        btn.appendChild(textSpan);
        btn.addEventListener('click', deleteDoc);
        return btn;
    }

    function buildCopyDocBtn() {
        var btn = el('button', { className: 'wh-copy-doc-btn wh-collapsible-btn' });
        var iconSpan = el('span', { className: 'wh-copy-doc-icon' });
        iconSpan.innerHTML = COPY_DOC_ICON_SVG;
        var textSpan = el('span');
        textSpan.textContent = t('copyDoc');
        btn.appendChild(iconSpan);
        btn.appendChild(textSpan);
        btn.addEventListener('click', copyDoc);
        return btn;
    }

    function copyDoc() {
        if (!state.currentId) return;
        var confirmFn = (window.parent && typeof window.parent.showConfirmDialog === 'function')
            ? window.parent.showConfirmDialog : null;
        if (confirmFn) {
            confirmFn(t('copyDocConfirm'), '').then(function (ok) {
                if (ok) doCopy();
            });
        } else {
            doCopy();
        }
    }

    function doCopy() {
        callPython('work_copy', { id: state.currentId }).then(function (res) {
            if (res && res.success) {
                var item = {
                    id: res.id,
                    template: res.template,
                    title: res.title,
                    body: res.body,
                    tags: res.tags,
                    version: 1,
                    visibility: 'me',
                    group_id: null,
                    owner_write_only: 1,
                    is_owner: true,
                };
                state.isOwner = true;
                state.ownerWriteOnly = 1;
                state.currentId = res.id;
                state.currentVersion = 1;
                state.currentVisibility = 'me';
                state.currentGroupId = null;
                state.isDirty = false;
                state.isNewDraft = false;
                showEditView(item);
            } else {
                showToast(t('copyDocFail'));
            }
        });
    }

    // -----------------------------------------------------------------------
    // Document link button + dialog
    // -----------------------------------------------------------------------
    function buildLinkDocBtn() {
        var btn = el('button', { className: 'wh-link-doc-btn wh-collapsible-btn', id: 'wh-link-doc-btn' });
        var iconSpan = el('span', { className: 'wh-link-doc-icon' });
        iconSpan.innerHTML = LINK_ICON_SVG;
        var textSpan = el('span');
        textSpan.textContent = t('linkDoc');
        btn.appendChild(iconSpan);
        btn.appendChild(textSpan);
        btn.addEventListener('click', openLinkDialog);
        return btn;
    }

    function updateLinkBtnBadge(count) {
        var btn = document.getElementById('wh-link-doc-btn');
        if (!btn) return;
        var existing = btn.querySelector('.wh-tags-btn-dot');
        if (count > 0 && !existing) {
            btn.appendChild(el('span', { className: 'wh-tags-btn-dot' }));
        } else if (count === 0 && existing) {
            existing.parentNode.removeChild(existing);
        }
    }

    function openLinkDialog() {
        var modal = window.parent && window.parent.desktopModal;
        if (!modal || !state.currentId) return;

        var dlg = document.createElement('div');
        dlg.style.cssText = 'padding:4px 0;';

        // Shared inline styles (parent document; workhub.css not available)
        var sectionLabelStyle = 'font-size:12px;color:var(--text-secondary,#8b8f9b);margin-bottom:6px;font-weight:600;text-transform:uppercase;letter-spacing:0.4px;';
        var sectionStyle = 'margin-bottom:16px;';
        var tableStyle = 'width:100%;border-collapse:collapse;font-size:13px;';
        var thStyle = 'text-align:left;padding:4px 8px;color:var(--text-secondary,#8b8f9b);font-size:11px;font-weight:600;border-bottom:1px solid var(--border-color,#373c47);';
        var tdStyle = 'padding:6px 8px;border-bottom:1px solid var(--border-color,#2a2d35);vertical-align:middle;cursor:pointer;';
        var tdNoCursorStyle = 'padding:6px 8px;border-bottom:1px solid var(--border-color,#2a2d35);vertical-align:middle;';
        var noDocStyle = 'font-size:13px;color:var(--text-secondary,#8b8f9b);padding:8px 0;';
        var errStyle = 'font-size:12px;color:#e06c75;margin-top:4px;';
        var inputStyle = 'width:100%;background:var(--bg-secondary,#20242b);border:1px solid var(--border-color,#373c47);color:var(--text-primary,#eceef2);border-radius:4px;padding:5px 8px;font-size:13px;box-sizing:border-box;outline:none;';
        var removeBtnStyle = 'background:none;border:none;color:var(--text-secondary,#8b8f9b);cursor:pointer;padding:2px 6px;font-size:13px;line-height:1;';

        // Track linked IDs in dialog (to avoid duplicates and to filter recent list)
        var linkedIds = [];

        // -- Section: current linked documents --
        var linkedSection = document.createElement('div');
        linkedSection.style.cssText = sectionStyle;
        var linkedLabel = document.createElement('div');
        linkedLabel.style.cssText = sectionLabelStyle;
        linkedLabel.textContent = t('linkedDocs');
        linkedSection.appendChild(linkedLabel);

        var linkedTableWrap = document.createElement('div');
        linkedSection.appendChild(linkedTableWrap);
        dlg.appendChild(linkedSection);

        // -- Section: add link --
        var addSection = document.createElement('div');
        addSection.style.cssText = sectionStyle + 'border-top:1px solid var(--border-color,#373c47);padding-top:14px;';
        var addLabel = document.createElement('div');
        addLabel.style.cssText = sectionLabelStyle;
        addLabel.textContent = t('addLink');
        addSection.appendChild(addLabel);

        // Recent docs sub-label
        var recentLabel = document.createElement('div');
        recentLabel.style.cssText = 'font-size:12px;color:var(--text-secondary,#8b8f9b);margin-bottom:6px;';
        recentLabel.textContent = t('recentDocs');
        addSection.appendChild(recentLabel);

        var recentTableWrap = document.createElement('div');
        addSection.appendChild(recentTableWrap);

        // ID input row
        var idRow = document.createElement('div');
        idRow.style.cssText = 'margin-top:10px;';
        var idInput = document.createElement('input');
        idInput.type = 'text';
        idInput.placeholder = t('docIdInputPlaceholder');
        idInput.style.cssText = inputStyle;
        var idErr = document.createElement('div');
        idErr.style.cssText = errStyle;
        idRow.appendChild(idInput);
        idRow.appendChild(idErr);
        addSection.appendChild(idRow);
        dlg.appendChild(addSection);

        // Helper: render type icon cell
        function makeTypeCell(template) {
            var td = document.createElement('td');
            td.style.cssText = tdNoCursorStyle + 'width:32px;';
            var iconWrap = document.createElement('span');
            iconWrap.appendChild(makeIcon(template, 14));
            td.appendChild(iconWrap);
            return td;
        }

        // Helper: render author avatar cell
        function makeAvatarCell(item) {
            var td = document.createElement('td');
            td.style.cssText = tdNoCursorStyle + 'width:28px;';
            if (item.owner_avatar_small) {
                var img = document.createElement('img');
                img.src = 'data:' + (item.owner_avatar_mime || 'image/png') + ';base64,' + item.owner_avatar_small;
                img.style.cssText = 'width:20px;height:20px;border-radius:50%;object-fit:cover;';
                td.appendChild(img);
            } else if (item.owner_display_name) {
                var abbr = document.createElement('span');
                abbr.style.cssText = 'display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;border-radius:50%;background:var(--accent-color,#5aacf0);color:#fff;font-size:10px;font-weight:600;';
                abbr.textContent = (item.owner_display_name || '?')[0].toUpperCase();
                td.appendChild(abbr);
            }
            return td;
        }

        // Helper: add item to linked table
        function addToLinkedTable(item) {
            if (linkedIds.indexOf(item.id) !== -1) return;
            linkedIds.push(item.id);
            updateLinkBtnBadge(linkedIds.length);

            // Remove "no linked docs" placeholder if present
            var placeholder = linkedTableWrap.querySelector('.wh-no-linked');
            if (placeholder) placeholder.parentNode.removeChild(placeholder);

            var table = linkedTableWrap.querySelector('table');
            if (!table) {
                table = document.createElement('table');
                table.style.cssText = tableStyle;
                var thead = document.createElement('thead');
                var hr = document.createElement('tr');
                ['', '', t('colTitle'), ''].forEach(function (h) {
                    var th = document.createElement('th');
                    th.style.cssText = thStyle;
                    th.textContent = h;
                    hr.appendChild(th);
                });
                thead.appendChild(hr);
                table.appendChild(thead);
                table.appendChild(document.createElement('tbody'));
                linkedTableWrap.appendChild(table);
            }
            var tbody = table.querySelector('tbody');
            var tr = document.createElement('tr');
            tr.style.cssText = 'cursor:pointer;';

            var typeTd = makeTypeCell(item.template);
            var avatarTd = makeAvatarCell(item);

            var titleTd = document.createElement('td');
            titleTd.style.cssText = tdStyle;
            titleTd.textContent = item.title || t('untitled');

            var removeTd = document.createElement('td');
            removeTd.style.cssText = tdNoCursorStyle + 'width:32px;';
            var removeBtn = document.createElement('button');
            removeBtn.textContent = 'X';
            removeBtn.style.cssText = removeBtnStyle;
            removeBtn.setAttribute('aria-label', 'remove link');
            (function (capturedItem, capturedTr) {
                removeBtn.addEventListener('click', function (e) {
                    e.stopPropagation();
                    callPython('link_remove', { id: state.currentId, linked_id: capturedItem.id }).then(function (res) {
                        if (res && res.success) {
                            var idx = linkedIds.indexOf(capturedItem.id);
                            if (idx !== -1) linkedIds.splice(idx, 1);
                            updateLinkBtnBadge(linkedIds.length);
                            capturedTr.parentNode.removeChild(capturedTr);
                            if (tbody.rows.length === 0) {
                                table.parentNode.removeChild(table);
                                renderNoLinked();
                            }
                            refreshRecentTable();
                        }
                    });
                });
            }(item, tr));

            // Row click -> flush pending edits then navigate to document
            (function (capturedItem) {
                function navigateToLinked() {
                    modal.close();
                    if (!state.diffMode) {
                        saveHistoryOnLeave();
                        if (state.isDirty) {
                            state.isNewDraft = false;
                            immediatelySave();
                        }
                    }
                    openDoc(capturedItem.id);
                }
                titleTd.addEventListener('click', navigateToLinked);
                typeTd.style.cursor = 'pointer';
                typeTd.addEventListener('click', navigateToLinked);
                avatarTd.style.cursor = 'pointer';
                avatarTd.addEventListener('click', navigateToLinked);
            }(item));

            tr.appendChild(typeTd);
            tr.appendChild(avatarTd);
            tr.appendChild(titleTd);
            tr.appendChild(removeTd);
            tbody.appendChild(tr);
        }

        function renderNoLinked() {
            var p = document.createElement('p');
            p.className = 'wh-no-linked';
            p.style.cssText = noDocStyle;
            p.textContent = t('noLinkedDocs');
            linkedTableWrap.appendChild(p);
        }

        // Render recent docs table (filtering out self and already-linked)
        function refreshRecentTable() {
            recentTableWrap.innerHTML = '';
            var recentItems = (state.listItems || []).filter(function (it) {
                return it.id !== state.currentId && linkedIds.indexOf(it.id) === -1;
            }).slice(0, 10);

            if (recentItems.length === 0) return;

            var table = document.createElement('table');
            table.style.cssText = tableStyle;
            var tbody = document.createElement('tbody');

            recentItems.forEach(function (item) {
                var tr = document.createElement('tr');
                tr.style.cssText = 'cursor:pointer;';

                var typeTd = makeTypeCell(item.template);
                typeTd.style.cursor = 'pointer';
                var avatarTd = makeAvatarCell(item);
                avatarTd.style.cursor = 'pointer';

                var titleTd = document.createElement('td');
                titleTd.style.cssText = tdStyle;
                titleTd.textContent = item.title || t('untitled');

                function doAddRecent() {
                    callPython('link_add', { id: state.currentId, linked_id: item.id }).then(function (res) {
                        if (res && res.success) {
                            addToLinkedTable(item);
                            refreshRecentTable();
                        } else if (res && res.error === 'already_linked') {
                            addToLinkedTable(item);
                            refreshRecentTable();
                        }
                    });
                }

                tr.addEventListener('click', doAddRecent);
                tr.appendChild(typeTd);
                tr.appendChild(avatarTd);
                tr.appendChild(titleTd);
                tbody.appendChild(tr);
            });

            table.appendChild(tbody);
            recentTableWrap.appendChild(table);
        }

        // ID input -> Enter handler: resolve -> show preview -> click to commit
        var idPreviewWrap = document.createElement('div');
        idPreviewWrap.style.cssText = 'margin-top:4px;';
        idRow.parentNode.insertBefore(idPreviewWrap, idRow.nextSibling);

        idInput.addEventListener('keydown', function (e) {
            if (e.key !== 'Enter') return;
            e.preventDefault();
            idErr.textContent = '';
            idPreviewWrap.innerHTML = '';
            var raw = idInput.value.trim();
            if (!raw) return;
            var num = parseInt(raw, 10);
            if (isNaN(num) || num <= 0) {
                idErr.textContent = t('linkNotFound');
                return;
            }
            if (num === state.currentId) {
                idErr.textContent = t('linkSelf');
                return;
            }
            if (linkedIds.indexOf(num) !== -1) {
                idErr.textContent = t('linkAlready');
                return;
            }
            callPython('link_resolve', { target_id: num }).then(function (res) {
                if (!res || !res.success) {
                    var errKey = (res && res.error === 'forbidden') ? 'linkForbidden' : 'linkNotFound';
                    idErr.textContent = t(errKey);
                    return;
                }
                var target = res.item;
                // Show clickable preview row; click commits the link
                var previewRow = document.createElement('div');
                previewRow.style.cssText = 'display:flex;align-items:center;padding:6px 8px;border-radius:4px;cursor:pointer;background:var(--bg-hover,#2a2f3a);border:1px solid var(--accent-color,#5aacf0);';
                var previewIcon = document.createElement('span');
                previewIcon.style.cssText = 'margin-right:8px;flex-shrink:0;';
                previewIcon.appendChild(makeIcon(target.template, 14));
                var previewTitle = document.createElement('span');
                previewTitle.style.cssText = 'flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:13px;';
                previewTitle.textContent = target.title || t('untitled');
                var previewHint = document.createElement('span');
                previewHint.style.cssText = 'font-size:11px;color:#888;margin-left:8px;flex-shrink:0;';
                previewHint.textContent = t('addLink');
                previewRow.appendChild(previewIcon);
                previewRow.appendChild(previewTitle);
                previewRow.appendChild(previewHint);
                idPreviewWrap.appendChild(previewRow);
                previewRow.addEventListener('click', function () {
                    idPreviewWrap.innerHTML = '';
                    callPython('link_add', { id: state.currentId, linked_id: target.id }).then(function (addRes) {
                        if (addRes && (addRes.success || addRes.error === 'already_linked')) {
                            addToLinkedTable(target);
                            refreshRecentTable();
                            idInput.value = '';
                            idErr.textContent = '';
                        } else {
                            idErr.textContent = t('linkFail');
                        }
                    });
                });
            });
        });

        // Load existing links then open modal
        callPython('link_list', { id: state.currentId }).then(function (res) {
            if (res && res.success && res.items && res.items.length > 0) {
                res.items.forEach(function (item) { addToLinkedTable(item); });
            } else {
                renderNoLinked();
            }
            refreshRecentTable();
        }).catch(function () {
            renderNoLinked();
            refreshRecentTable();
        });

        modal.open({
            title: t('linkDialogTitle'),
            element: dlg,
            width: '460px',
            buttons: [
                { label: t('close'), onClick: function () { modal.close(); } },
            ],
        });
    }

    function openSharingDialog() {
        var modal = window.parent && window.parent.desktopModal;
        if (!modal) return;

        var groups = state.currentUserGroups || [];
        var selStyle = 'width:100%;background:var(--bg-secondary,#20242b);border:1px solid var(--border-color,#373c47);color:var(--text-primary,#eceef2);border-radius:4px;padding:5px 8px;font-size:13px;box-sizing:border-box;outline:none;';
        var selDisabledStyle = selStyle + 'opacity:0.4;cursor:not-allowed;';

        // Inline styles required: element is adopted into parent document where workhub.css is absent
        var dlg = document.createElement('div');
        dlg.style.cssText = 'padding:4px 0;';

        // Row 1: visibility combobox
        var visRow = document.createElement('div');
        visRow.style.cssText = 'margin-bottom:12px;';
        var visLabel = document.createElement('div');
        visLabel.style.cssText = 'font-size:12px;color:var(--text-secondary,#8b8f9b);margin-bottom:4px;';
        visLabel.textContent = t('visibilityLabel');
        var visSel = document.createElement('select');
        visSel.style.cssText = selStyle;
        [['me', t('visMe')], ['group', t('visGroup')], ['all', t('visAll')]].forEach(function (pair) {
            var opt = document.createElement('option');
            opt.value = pair[0];
            opt.textContent = pair[1];
            if (groups.length === 0 && pair[0] === 'group') opt.disabled = true;
            if (pair[0] === state.currentVisibility) opt.selected = true;
            visSel.appendChild(opt);
        });
        visRow.appendChild(visLabel);
        visRow.appendChild(visSel);
        dlg.appendChild(visRow);

        // Row 2: group selector (always visible, enabled only when visibility = group)
        var groupRow = document.createElement('div');
        groupRow.style.cssText = 'margin-bottom:4px;';
        var groupLabel = document.createElement('div');
        groupLabel.style.cssText = 'font-size:12px;color:var(--text-secondary,#8b8f9b);margin-bottom:4px;';
        groupLabel.textContent = t('selectGroup');
        var groupSel = document.createElement('select');
        var isGroupActive = (state.currentVisibility === 'group') && groups.length > 0;

        function setGroupSelActive(active) {
            groupSel.disabled = !active;
            groupSel.style.cssText = active ? selStyle : selDisabledStyle;
            groupSel.innerHTML = '';
            if (!active) {
                var emptyOpt = document.createElement('option');
                emptyOpt.value = '';
                emptyOpt.textContent = '';
                groupSel.appendChild(emptyOpt);
            } else {
                groups.forEach(function (g) {
                    var opt = document.createElement('option');
                    opt.value = g.id;
                    opt.textContent = g.name;
                    if (g.id === state.currentGroupId) opt.selected = true;
                    groupSel.appendChild(opt);
                });
            }
        }

        setGroupSelActive(isGroupActive);
        groupRow.appendChild(groupLabel);
        groupRow.appendChild(groupSel);
        dlg.appendChild(groupRow);

        // Row 3: 나만 쓰기 가능 toggle
        var ownerWriteRow = document.createElement('div');
        ownerWriteRow.style.cssText = 'margin-top:10px;display:flex;align-items:center;justify-content:space-between;';
        var ownerWriteLabel = document.createElement('span');
        ownerWriteLabel.style.cssText = 'font-size:13px;color:var(--text-primary,#eceef2);';
        ownerWriteLabel.textContent = currentLanguage === 'ko' ? '나만 쓰기 가능' : 'Only I can edit';
        var ownerWriteChk = document.createElement('input');
        ownerWriteChk.type = 'checkbox';
        ownerWriteChk.style.cssText = 'width:16px;height:16px;cursor:pointer;';

        var _isInitialRender = true;
        function applyOwnerWriteDefaults(vis) {
            if (vis === 'me') {
                ownerWriteChk.checked = true;
                ownerWriteChk.disabled = true;
                ownerWriteChk.style.opacity = '0.4';
                ownerWriteChk.style.cursor = 'not-allowed';
            } else if (vis === 'group') {
                // 초기 렌더(현재 설정)는 기존 값 유지, visibility 변경 시 OFF가 기본
                ownerWriteChk.checked = _isInitialRender ? (state.ownerWriteOnly === 1) : false;
                ownerWriteChk.disabled = false;
                ownerWriteChk.style.opacity = '';
                ownerWriteChk.style.cursor = 'pointer';
            } else {
                // all
                ownerWriteChk.checked = _isInitialRender ? (state.ownerWriteOnly === 1) : true;
                ownerWriteChk.disabled = false;
                ownerWriteChk.style.opacity = '';
                ownerWriteChk.style.cursor = 'pointer';
            }
            _isInitialRender = false;
        }

        applyOwnerWriteDefaults(state.currentVisibility);
        ownerWriteRow.appendChild(ownerWriteLabel);
        ownerWriteRow.appendChild(ownerWriteChk);
        dlg.appendChild(ownerWriteRow);

        if (state.currentId) {
            var divider = document.createElement('hr');
            divider.style.cssText = 'border:none;border-top:1px solid var(--border-color,#373c47);margin:12px 0 10px;';
            dlg.appendChild(divider);

            var docIdRow = document.createElement('div');
            docIdRow.style.cssText = 'margin-bottom:2px;';
            var docIdLabelEl = document.createElement('div');
            docIdLabelEl.style.cssText = 'font-size:12px;color:var(--text-secondary,#8b8f9b);margin-bottom:4px;';
            docIdLabelEl.textContent = t('docIdLabel');
            var docIdWrap = document.createElement('div');
            docIdWrap.style.cssText = 'display:flex;align-items:center;width:100%;box-sizing:border-box;overflow:hidden;';
            var docIdInput = document.createElement('input');
            docIdInput.type = 'text';
            docIdInput.readOnly = true;
            docIdInput.value = '/go ' + state.currentId;
            docIdInput.style.cssText = 'flex:1;min-width:0;background:var(--bg-secondary,#20242b);border:1px solid var(--border-color,#373c47);color:var(--text-primary,#eceef2);border-radius:4px;padding:4px 8px;font-size:13px;box-sizing:border-box;outline:none;cursor:default;margin-right:6px;';
            var docIdCopyBtn = document.createElement('button');
            var copyBtnBase = 'font-size:11px;padding:4px 8px;background:var(--bg-secondary,#20242b);border:1px solid var(--border-color,#373c47);color:var(--text-primary,#eceef2);border-radius:4px;cursor:pointer;white-space:nowrap;outline:none;';
            var copyBtnHover = 'font-size:11px;padding:4px 8px;background:var(--bg-hover,#2a2f3a);border:1px solid var(--border-color,#373c47);color:var(--text-primary,#eceef2);border-radius:4px;cursor:pointer;white-space:nowrap;outline:none;';
            docIdCopyBtn.style.cssText = copyBtnBase;
            docIdCopyBtn.addEventListener('mouseenter', function () { docIdCopyBtn.style.cssText = copyBtnHover; });
            docIdCopyBtn.addEventListener('mouseleave', function () { docIdCopyBtn.style.cssText = copyBtnBase; });
            docIdCopyBtn.textContent = t('copy');
            docIdCopyBtn.addEventListener('click', function () {
                var text = '/go ' + state.currentId;
                var ta = document.createElement('textarea');
                ta.value = text;
                ta.style.cssText = 'position:fixed;top:-9999px;left:-9999px;opacity:0;';
                document.body.appendChild(ta);
                ta.focus();
                ta.select();
                try { document.execCommand('copy'); } catch (e) {}
                document.body.removeChild(ta);
                docIdCopyBtn.textContent = t('copied');
                setTimeout(function () { docIdCopyBtn.textContent = t('copy'); }, 1500);
            });
            docIdWrap.appendChild(docIdInput);
            docIdWrap.appendChild(docIdCopyBtn);
            docIdRow.appendChild(docIdLabelEl);
            docIdRow.appendChild(docIdWrap);
            dlg.appendChild(docIdRow);
        }

        visSel.addEventListener('change', function () {
            setGroupSelActive((visSel.value === 'group') && groups.length > 0);
            applyOwnerWriteDefaults(visSel.value);
        });

        modal.open({
            title: t('shareTitle'),
            element: dlg,
            width: '280px',
            buttons: [
                { label: t('cancel'), onClick: function () { modal.close(); } },
                {
                    label: t('confirm'),
                    primary: true,
                    onClick: function () {
                        var newVis = visSel.value;
                        var newGroup = null;
                        if (newVis === 'group' && groups.length > 0) {
                            newGroup = groupSel.value || null;
                        }
                        var newOwnerWriteOnly = (newVis === 'me') ? 1 : (ownerWriteChk.checked ? 1 : 0);
                        state.currentVisibility = newVis;
                        state.currentGroupId = newGroup;
                        state.ownerWriteOnly = newOwnerWriteOnly;
                        modal.close();
                        onBodyChange();
                    },
                },
            ],
        });
    }

    // -----------------------------------------------------------------------
    // Edit body builders
    // -----------------------------------------------------------------------
    function buildMdControl(opts) {
        if (!opts.readonly) opts = Object.assign({ autoResize: true }, opts);
        return SkMdControl.build(opts);
    }

    function buildEditBody(container, item, opts) {
        var readonlyMode = opts && opts.readonlyMode;
        var bodyVal = (opts && opts.readonlyBody !== undefined) ? opts.readonlyBody : item.body;

        var titleInput = el('input', { type: 'text', className: 'wh-title-input', placeholder: t('titlePlaceholder') });
        if (!readonlyMode) titleInput.id = 'wh-title';
        titleInput.value = item.title || '';
        if (readonlyMode) {
            titleInput.disabled = true;
        } else {
            titleInput.addEventListener('input', onTitleChange);
            titleInput.addEventListener('blur', onFocusLost);
        }
        container.appendChild(titleInput);

        var tagsRow = buildTagsEditor(item.tags || '', readonlyMode);
        tagsRow.style.display = 'none';
        container.appendChild(tagsRow);

        var bodyItem = (bodyVal !== item.body) ? Object.assign({}, item, { body: bodyVal }) : item;
        _prefetchDocLinks(bodyVal || '', function () {
            switch (item.template) {
                case 'command':   buildCommandBody(container, bodyItem, readonlyMode); break;
                case 'todo':      buildTodoBody(container, bodyItem, readonlyMode); break;
                case 'checklist': buildChecklistBody(container, bodyItem, readonlyMode); break;
                default:          buildNoteBody(container, bodyItem, readonlyMode); break;
            }
        });

        if (!readonlyMode) {
            if (opts && opts.restoreFocusId) {
                setTimeout(function () {
                    var target = document.getElementById(opts.restoreFocusId);
                    if (target) {
                        if (target._switchToEdit) {
                            target._switchToEdit();
                        } else {
                            target.focus();
                        }
                        if (typeof opts.restoreSelStart === 'number' && typeof target.setSelectionRange === 'function') {
                            target.setSelectionRange(opts.restoreSelStart, opts.restoreSelEnd);
                        }
                    }
                }, 0);
            } else if (!(opts && opts.noFocus)) {
                setTimeout(function () { titleInput.focus(); }, 0);
            }
        }
    }

    function _mentionSearch(query, callback) {
        var q = query.toLowerCase();
        var results = [];
        Object.keys(state.mentionMap).forEach(function (id) {
            var info = state.mentionMap[id];
            var nameMatch = (info.display_name || '').toLowerCase().indexOf(q) !== -1;
            var idMatch = id.toLowerCase().indexOf(q) !== -1;
            if (nameMatch || idMatch) {
                results.push({ id: id, display_name: info.display_name, avatar_small: info.avatar_small, avatar_mime: info.avatar_mime });
            }
        });
        results.sort(function (a, b) { return (a.display_name || a.id).localeCompare(b.display_name || b.id); });
        callback(results.slice(0, 8));
    }

    function _docSearch(query, callback) {
        callPython('work_search', { query: query || '' }).then(function (res) {
            if (!res || !res.success) { callback([]); return; }
            var items = (res.items || [])
                .filter(function (it) { return it.id !== state.currentId; })
                .slice(0, 8)
                .map(function (it) { return { id: it.id, title: it.title, template: it.template }; });
            items.forEach(function (it) {
                state.docLinkMap[it.id] = { title: it.title, template: it.template };
            });
            callback(items);
        });
    }

    function _docLinkClick(docId) {
        if (!state.diffMode) {
            saveHistoryOnLeave();
            if (state.isDirty) {
                state.isNewDraft = false;
                immediatelySave();
            }
        }
        openDoc(docId);
    }

    // Extract [[id|...]] ids from text, fetch titles for uncached ones, update docLinkMap, then call cb.
    function _prefetchDocLinks(text, cb) {
        var found = [];
        var re = /\[\[(\d+)\|/g;
        var m;
        var seen = {};
        while ((m = re.exec(text)) !== null) {
            var id = parseInt(m[1], 10);
            if (!seen[id]) { seen[id] = true; found.push(id); }
        }
        if (!found.length) { cb(); return; }
        callPython('work_get_titles', { ids: found }).then(function (res) {
            if (res && res.success) {
                (res.items || []).forEach(function (it) {
                    state.docLinkMap[it.id] = { title: it.title, template: it.template };
                });
            }
            cb();
        }).catch(function () { cb(); });
    }

    function buildNoteBody(container, item, readonlyMode) {
        var initVal = '';
        try { initVal = JSON.parse(item.body || '{}').text || ''; } catch (e) { initVal = typeof item.body === 'string' ? item.body : ''; }
        if (readonlyMode) {
            container.appendChild(buildMdControl({ id: 'wh-note-body', initialValue: initVal, minHeight: '200px', readonly: true, lang: currentLanguage, mentionMap: state.mentionMap, docLinkMap: state.docLinkMap, docLinkClick: _docLinkClick }).element);
        } else {
            container.appendChild(buildMdControl({ id: 'wh-note-body', placeholder: t('noteBodyPlaceholder'), initialValue: initVal, minHeight: '200px', imagePaste: true, onChange: onBodyChange, onBlur: onFocusLost, lang: currentLanguage, mentionSearch: _mentionSearch, docSearch: _docSearch, docLinkClick: _docLinkClick, mentionMap: state.mentionMap, docLinkMap: state.docLinkMap }).element);
        }
    }

    function buildCommandBody(container, item, readonlyMode) {
        var data = {};
        try { data = JSON.parse(item.body || '{}'); } catch (e) {}

        var cmdLabel = el('div', { className: 'wh-field-label' });
        cmdLabel.textContent = t('commandLabel');
        container.appendChild(cmdLabel);

        var cmdBlock = el('div', { className: 'wh-command-block' });
        var prefix = el('span', { className: 'wh-command-prefix' });
        prefix.textContent = '$';
        var cmdWrap = el('div', { className: 'wh-command-wrap' });
        var cmdHighlight = el('div', { className: 'wh-command-highlight' });
        var cmdInput = el('input', { type: 'text', className: 'wh-command-input', id: 'wh-cmd-command', placeholder: t('commandPlaceholder') });
        cmdInput.value = data.command || '';
        if (readonlyMode) {
            cmdInput.disabled = true;
            cmdHighlight.classList.add('is-readonly');
        } else {
            cmdInput.addEventListener('input', function () { updateHighlight(cmdInput, cmdHighlight); onBodyChange(); });
            cmdInput.addEventListener('scroll', function () { cmdHighlight.scrollLeft = cmdInput.scrollLeft; });
            cmdInput.addEventListener('blur', onFocusLost);
        }
        updateHighlight(cmdInput, cmdHighlight);
        cmdWrap.appendChild(cmdHighlight);
        cmdWrap.appendChild(cmdInput);
        var varForm = null;

        function doRun(overrides) {
            var text = cmdInput.value;
            if (!text) return;
            callPython('command_run', { command: text, overrides: overrides || {} }).then(function (res) {
                if (!res) return;
                if (res.error === 'no_terminal') {
                    showToast(t('runNoTerminal'));
                } else if (res.error === 'undefined_vars' && Array.isArray(res.vars) && res.vars.length) {
                    showVarForm(res.vars);
                }
            });
        }

        function showVarForm(vars) {
            if (varForm) varForm.parentNode && varForm.parentNode.removeChild(varForm);
            varForm = el('div', { className: 'wh-var-form' });

            var inputs = {};
            vars.forEach(function (v) {
                var row = el('div', { className: 'wh-var-row' });
                var lbl = el('label', { className: 'wh-var-label' });
                lbl.textContent = t('runVarPrompt').replace('${var}', v);
                var inp = el('input', { type: 'text', className: 'wh-var-input' });
                inp.placeholder = v;
                inputs[v] = inp;
                row.appendChild(lbl);
                row.appendChild(inp);
                varForm.appendChild(row);
            });

            var btnRow = el('div', { className: 'wh-var-btn-row' });
            var confirmBtn = el('button', { className: 'btn btn-sm btn-primary' });
            confirmBtn.textContent = t('runVarConfirm');
            var cancelBtn = el('button', { className: 'btn btn-sm btn-outline-secondary' });
            cancelBtn.textContent = t('runVarCancel');

            confirmBtn.addEventListener('click', function () {
                var overrides = {};
                vars.forEach(function (v) { overrides[v] = inputs[v].value; });
                varForm.parentNode && varForm.parentNode.removeChild(varForm);
                varForm = null;
                doRun(overrides);
            });
            cancelBtn.addEventListener('click', function () {
                varForm.parentNode && varForm.parentNode.removeChild(varForm);
                varForm = null;
            });

            btnRow.appendChild(confirmBtn);
            btnRow.appendChild(cancelBtn);
            varForm.appendChild(btnRow);
            cmdBlock.parentNode.insertBefore(varForm, cmdBlock.nextSibling);
            var firstInput = varForm.querySelector('input');
            if (firstInput) firstInput.focus();
        }

        var runBtn = el('button', { className: 'btn btn-sm btn-outline-secondary' });
        runBtn.textContent = t('run');
        runBtn.addEventListener('click', function () {
            if (varForm) {
                varForm.parentNode && varForm.parentNode.removeChild(varForm);
                varForm = null;
            }
            doRun(null);
        });
        cmdBlock.appendChild(prefix);
        cmdBlock.appendChild(cmdWrap);
        cmdBlock.appendChild(runBtn);
        container.appendChild(cmdBlock);

        var descLabel = el('div', { className: 'wh-field-label' });
        descLabel.textContent = t('descLabel');
        container.appendChild(descLabel);

        if (readonlyMode) {
            container.appendChild(buildMdControl({ id: 'wh-cmd-description', initialValue: data.description || '', minHeight: '80px', readonly: true, lang: currentLanguage, mentionMap: state.mentionMap, docLinkMap: state.docLinkMap, docLinkClick: _docLinkClick }).element);
        } else {
            container.appendChild(buildMdControl({ id: 'wh-cmd-description', placeholder: t('descPlaceholder'), initialValue: data.description || '', minHeight: '80px', imagePaste: true, onChange: onBodyChange, onBlur: onFocusLost, lang: currentLanguage, mentionSearch: _mentionSearch, docSearch: _docSearch, docLinkClick: _docLinkClick, mentionMap: state.mentionMap, docLinkMap: state.docLinkMap }).element);
        }
    }

    function buildTodoBody(container, item, readonlyMode) {
        var data = { items: [] };
        try { data = JSON.parse(item.body || '{"items":[]}'); } catch (e) {}
        if (!Array.isArray(data.items)) data.items = [];

        var listEl = el('div', { id: 'wh-todo-list' });
        container.appendChild(listEl);

        data.items.forEach(function (it, idx) {
            listEl.appendChild(buildTodoItem(it, idx, readonlyMode));
        });

        if (!readonlyMode) {
            var addBtn = el('button', { className: 'btn btn-sm btn-outline-secondary' });
            addBtn.textContent = t('addItem');
            addBtn.style.marginTop = '8px';
            addBtn.addEventListener('click', function () {
                var list = document.getElementById('wh-todo-list');
                var count = list.querySelectorAll('.wh-todo-item').length;
                list.appendChild(buildTodoItem({ text: '', done: false }, count, false));
                onBodyChange();
            });
            container.appendChild(addBtn);
        }
    }

    function makeItemDelBtn(onConfirmed) {
        var btn = el('button', { className: 'wh-item-del' });
        btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M2 4h12M5 4V2h6v2M6 7v5M10 7v5M3 4l1 9a1 1 0 001 1h6a1 1 0 001-1l1-9" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>';
        btn.addEventListener('click', function () {
            var confirmFn = (window.parent && typeof window.parent.showConfirmDialog === 'function')
                ? window.parent.showConfirmDialog : null;
            if (confirmFn) {
                confirmFn(t('itemDeleteConfirm'), '', { yesStyle: 'danger' }).then(function (ok) {
                    if (ok) onConfirmed();
                });
            } else {
                onConfirmed();
            }
        });
        return btn;
    }

    function buildTodoItem(it, idx, readonlyMode) {
        var row = el('div', { className: 'wh-todo-item' });
        var cb = el('input', { type: 'checkbox' });
        cb.checked = !!it.done;
        var textInput = el('input', { type: 'text', className: 'wh-todo-text' + (it.done ? ' done' : ''), placeholder: t('todoItemPlaceholder') });
        textInput.value = it.text || '';
        if (readonlyMode) {
            cb.disabled = true;
            textInput.disabled = true;
        } else {
            cb.addEventListener('change', function () {
                textInput.classList.toggle('done', cb.checked);
                onBodyChange();
                immediatelySave();
            });
            textInput.addEventListener('input', onBodyChange);
            textInput.addEventListener('blur', onFocusLost);
            var delBtn = makeItemDelBtn(function () {
                row.remove();
                onBodyChange();
            });
            row.appendChild(cb);
            row.appendChild(textInput);
            row.appendChild(delBtn);
            return row;
        }
        row.appendChild(cb);
        row.appendChild(textInput);
        return row;
    }

    function buildChecklistBody(container, item, readonlyMode) {
        var data = { items: [] };
        try { data = JSON.parse(item.body || '{"items":[]}'); } catch (e) {}
        if (!Array.isArray(data.items)) data.items = [];

        var listEl = el('div', { id: 'wh-cl-list' });
        container.appendChild(listEl);

        data.items.forEach(function (it, idx) {
            listEl.appendChild(buildClItem(it, idx + 1, readonlyMode));
        });

        renumberCl();

        if (!readonlyMode) {
            var btns = el('div', { style: 'margin-top:8px; display:flex;' });

            var addBtn = el('button', { className: 'btn btn-sm btn-outline-secondary' });
            addBtn.textContent = t('addStep');
            addBtn.style.marginRight = '8px';
            addBtn.addEventListener('click', function () {
                var list = document.getElementById('wh-cl-list');
                var count = list.querySelectorAll('.wh-cl-item').length;
                list.appendChild(buildClItem({ text: '', done: false }, count + 1, false));
                renumberCl();
                onBodyChange();
            });

            var resetBtn = el('button', { className: 'btn btn-sm btn-outline-warning' });
            resetBtn.textContent = t('resetAll');
            resetBtn.addEventListener('click', function () {
                document.querySelectorAll('#wh-cl-list .wh-cl-check').forEach(function (cb) {
                    cb.checked = false;
                    var textEl = cb.closest('.wh-cl-item').querySelector('.wh-cl-text');
                    if (textEl) textEl.classList.remove('done');
                });
                onBodyChange();
                immediatelySave();
            });

            btns.appendChild(addBtn);
            btns.appendChild(resetBtn);
            container.appendChild(btns);
        }
    }

    function buildClItem(it, num, readonlyMode) {
        var row = el('div', { className: 'wh-cl-item' });

        var numEl = el('span', { className: 'wh-cl-num' });
        numEl.textContent = num + '.';

        var textInput = el('input', { type: 'text', className: 'wh-cl-text' + (it.done ? ' done' : ''), placeholder: t('stepPlaceholder') });
        textInput.value = it.text || '';

        var cb = el('input', { type: 'checkbox', className: 'wh-cl-check' });
        cb.checked = !!it.done;

        if (readonlyMode) {
            textInput.disabled = true;
            cb.disabled = true;
            row.appendChild(numEl);
            row.appendChild(textInput);
            row.appendChild(cb);
            return row;
        }

        row.draggable = true;
        textInput.addEventListener('input', onBodyChange);
        textInput.addEventListener('blur', onFocusLost);
        cb.addEventListener('change', function () {
            textInput.classList.toggle('done', cb.checked);
            onBodyChange();
            immediatelySave();
        });

        var delBtn = makeItemDelBtn(function () {
            row.remove();
            renumberCl();
            onBodyChange();
        });

        row.appendChild(numEl);
        row.appendChild(textInput);
        row.appendChild(cb);
        row.appendChild(delBtn);

        row.addEventListener('dragstart', function (e) {
            e.dataTransfer.effectAllowed = 'move';
            row._dragging = true;
        });
        row.addEventListener('dragend', function () {
            row._dragging = false;
            document.querySelectorAll('.wh-drag-over').forEach(function (el) { el.classList.remove('wh-drag-over'); });
            renumberCl();
            onBodyChange();
        });
        row.addEventListener('dragover', function (e) {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            row.classList.add('wh-drag-over');
        });
        row.addEventListener('dragleave', function () {
            row.classList.remove('wh-drag-over');
        });
        row.addEventListener('drop', function (e) {
            e.preventDefault();
            row.classList.remove('wh-drag-over');
            var list = document.getElementById('wh-cl-list');
            var dragged = Array.from(list.querySelectorAll('.wh-cl-item')).find(function (r) { return r._dragging; });
            if (dragged && dragged !== row) {
                list.insertBefore(dragged, row);
            }
        });

        return row;
    }

    function renumberCl() {
        var list = document.getElementById('wh-cl-list');
        if (!list) return;
        list.querySelectorAll('.wh-cl-item').forEach(function (row, idx) {
            var numEl = row.querySelector('.wh-cl-num');
            if (numEl) numEl.textContent = (idx + 1) + '.';
        });
    }

    function buildTagsEditor(tagsStr, readonlyMode) {
        var wrap = el('div', { className: 'wh-tags-row', id: 'wh-tags-row' });
        var tags = tagsStr ? tagsStr.split(',').map(function (tg) { return tg.trim(); }).filter(Boolean) : [];

        if (readonlyMode) {
            tags.forEach(function (tg) {
                var chip = el('span', { className: 'wh-tag' });
                var label = el('span');
                label.textContent = '#' + tg;
                chip.appendChild(label);
                wrap.appendChild(chip);
            });
            return wrap;
        }

        tags.forEach(function (tg) { wrap.appendChild(buildTagChip(tg)); });

        var tagInput = el('input', { type: 'text', className: 'wh-tag-input', placeholder: t('tagPlaceholder'), id: 'wh-tag-input' });
        tagInput.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                var val = tagInput.value.trim().replace(/^#/, '');
                if (val) {
                    wrap.insertBefore(buildTagChip(val), tagInput);
                    tagInput.value = '';
                    onTagsChange();
                }
            }
        });
        tagInput.addEventListener('blur', function () {
            var val = tagInput.value.trim().replace(/^#/, '');
            if (val) {
                wrap.insertBefore(buildTagChip(val), tagInput);
                tagInput.value = '';
                onTagsChange();
            }
            onFocusLost();
        });

        wrap.appendChild(tagInput);
        return wrap;
    }

    function buildTagChip(tag) {
        var chip = el('span', { className: 'wh-tag' });
        chip.setAttribute('data-tag', tag);
        var label = el('span');
        label.textContent = '#' + tag;
        var rm = el('span', { className: 'wh-tag-remove' });
        rm.textContent = ' x';
        rm.addEventListener('click', function () {
            chip.remove();
            onTagsChange();
        });
        chip.appendChild(label);
        chip.appendChild(rm);
        return chip;
    }

    // -----------------------------------------------------------------------
    // Content collection helpers
    // -----------------------------------------------------------------------
    function collectTitle() {
        var inp = document.getElementById('wh-title');
        return inp ? inp.value : '';
    }

    function collectTags() {
        var row = document.getElementById('wh-tags-row');
        if (!row) return '';
        var chips = row.querySelectorAll('.wh-tag[data-tag]');
        var tags = [];
        chips.forEach(function (c) {
            var text = c.getAttribute('data-tag');
            if (text) tags.push(text);
        });
        return tags.join(',');
    }

    function collectBody() {
        var tmpl = state.currentTemplate;
        if (tmpl === 'note') {
            var ta = document.getElementById('wh-note-body');
            var text = ta ? (ta._getValue ? ta._getValue() : ta.value) : '';
            return JSON.stringify({ text: text });
        }
        if (tmpl === 'command') {
            var cmd = document.getElementById('wh-cmd-command');
            var desc = document.getElementById('wh-cmd-description');
            return JSON.stringify({
                command: cmd ? cmd.value : '',
                description: desc ? (desc._getValue ? desc._getValue() : desc.value) : '',
            });
        }
        if (tmpl === 'todo') {
            var list = document.getElementById('wh-todo-list');
            var items = [];
            if (list) {
                list.querySelectorAll('.wh-todo-item').forEach(function (row) {
                    var cb = row.querySelector('input[type="checkbox"]');
                    var textEl = row.querySelector('.wh-todo-text');
                    items.push({ text: textEl ? textEl.value : '', done: cb ? cb.checked : false });
                });
            }
            return JSON.stringify({ items: items });
        }
        if (tmpl === 'checklist') {
            var clList = document.getElementById('wh-cl-list');
            var clItems = [];
            if (clList) {
                clList.querySelectorAll('.wh-cl-item').forEach(function (row) {
                    var cb = row.querySelector('.wh-cl-check');
                    var textEl = row.querySelector('.wh-cl-text');
                    clItems.push({ text: textEl ? textEl.value : '', done: cb ? cb.checked : false });
                });
            }
            return JSON.stringify({ items: clItems });
        }
        return '';
    }

    // -----------------------------------------------------------------------
    // Auto-save state machine
    // -----------------------------------------------------------------------
    function onTitleChange() { state.dirtyTitle = true; onContentChange(); }
    function onBodyChange()  { state.dirtyBody  = true; onContentChange(); }
    function onTagsChange()  { state.dirtyTags  = true; onContentChange(); updateTagsBtnBadge(); }

    function onContentChange() {
        state.isDirty = true;
        clearTimeout(state.saveDebounce);
        state.saveDebounce = setTimeout(immediatelySave, 1000);
    }

    function onFocusLost() {
        if (state.isDirty) immediatelySave();
    }

    function immediatelySave() {
        if (state.diffMode) return;
        clearTimeout(state.saveDebounce);
        var title = collectTitle();
        var body = collectBody();
        var tags = collectTags();

        if (!state.hasInserted) {
            if (state.createInFlight) return;
            state.createInFlight = true;
            callPython('work_create', {
                template: state.currentTemplate,
                title: title,
                body: body,
                tags: tags,
                history_body: '',
            }).then(function (res) {
                state.createInFlight = false;
                if (res && res.success) {
                    state.currentId = res.id;
                    state.currentVersion = res.version || 1;
                    state.hasInserted = true;
                    state.isNewDraft = true;
                    state.isDirty = false;
                    state.dirtyTitle = false;
                    state.dirtyBody = false;
                    state.dirtyTags = false;
                    state.baseTitle = title;
                    state.baseBody = body;
                    state.baseTags = tags;
                    if (res.updated_at) state.lastEditedAt = res.updated_at;
                    refreshHeaderBtns();
                    startPoll(res.id);
                }
            }).catch(function () { state.createInFlight = false; });
        } else if (state.currentId) {
            // isNewDraft 중간 저장은 visibility='me', group_id=null, owner_write_only=1 고정
            var saveVis = state.isNewDraft ? 'me' : state.currentVisibility;
            var saveGroup = state.isNewDraft ? null : state.currentGroupId;
            var saveOwnerWriteOnly = state.isNewDraft ? 1 : state.ownerWriteOnly;
            callPython('work_save', {
                id: state.currentId,
                title: title,
                body: body,
                skip_body: !state.dirtyBody,
                tags: tags,
                visibility: saveVis,
                group_id: saveGroup,
                owner_write_only: saveOwnerWriteOnly,
                version: state.currentVersion,
                history_body: '',
            }).then(function (res) {
                if (!res) return;
                if (res.success) {
                    state.isDirty = false;
                    state.dirtyTitle = false;
                    state.dirtyBody = false;
                    state.dirtyTags = false;
                    state.baseTitle = title;
                    state.baseBody = body;
                    state.baseTags = tags;
                    state.currentVersion = res.version;
                    if (res.updated_at) state.lastEditedAt = res.updated_at;
                    if (state.currentId) startPoll(state.currentId);
                } else if (res.error === 'conflict') {
                    handleConflict(res.server_item);
                } else if (res.error === 'forbidden') {
                    showToast(t('forbidden'));
                    setTimeout(backToList, 1500);
                } else if (res.error === 'not_found') {
                    handleDeleted();
                }
            });
        }
    }

    function refreshHeaderBtns() {
        var header = document.getElementById('wh-edit-header');
        if (!header) return;
        if (state.diffMode) {
            if (!document.getElementById('wh-diff-exit-btn')) {
                var exitBtn = buildDiffExitBtn();
                exitBtn.id = 'wh-diff-exit-btn';
                header.appendChild(exitBtn);
            }
            return;
        }
        // Ensure delete is in the collapsible group (before share/history)
        var delEl = header.querySelector('.wh-delete-btn');
        if (!delEl && state.isOwner) {
            var visWrapRef = document.getElementById('wh-vis-wrap');
            var histBtnRef = document.getElementById('wh-history-btn');
            var anchor = visWrapRef || histBtnRef || null;
            var newDel = buildDeleteBtn();
            if (anchor) {
                header.insertBefore(newDel, anchor);
            } else {
                header.appendChild(newDel);
            }
        }
        if (state.isOwner && !document.getElementById('wh-vis-wrap')) {
            header.appendChild(buildVisibilityBtn());
        }
        if (!document.getElementById('wh-history-btn')) {
            header.appendChild(buildHistoryBtn());
        }
    }

    // -----------------------------------------------------------------------
    // Notify polling
    // -----------------------------------------------------------------------
    function startPoll(workId) {
        stopPoll();
        state.pollMtime = 0;
        state.pollConflictShown = false;
        var gen = ++state.pollGen;
        callPython('work_poll', { id: workId, mtime: 0 }).then(function (res) {
            if (gen !== state.pollGen) return;
            if (res && res.success && res.mtime) state.pollMtime = res.mtime;
            state.pollTimer = setInterval(function () {
                if (!state.currentId || state.view !== 'edit') { stopPoll(); return; }
                var tickGen = state.pollGen;
                callPython('work_poll', { id: workId, mtime: state.pollMtime }).then(function (res) {
                    if (tickGen !== state.pollGen) return;
                    if (!res) return;
                    if (!res.success) {
                        if (res.error === 'not_found') {
                            handleDeleted();
                        }
                        return;
                    }
                    var newMtime = res.mtime || state.pollMtime;
                    if (res.changed && !state.pollConflictShown) {
                        if (state.historyMode || state.diffMode) {
                            // In history/diff mode: absorb change silently, reload on exit
                            state.pollMtime = newMtime;
                            return;
                        }
                        state.pollConflictShown = true;
                        var pollEditor = res.editor || null;
                        var pollAvatar = res.editor_avatar || null;
                        var pollAvatarMime = res.editor_avatar_mime || null;
                        if (state.isDirty) {
                            state.pollMtime = newMtime;
                            handleConflict(null, pollEditor);
                        } else {
                            state.pollMtime = newMtime;
                            var editorMsg = pollEditor
                                ? t('editedToast').replace('{editor}', pollEditor)
                                : t('editedToastUnknown');
                            var toastOpts = null;
                            if (pollEditor) {
                                if (pollAvatar) {
                                    toastOpts = { avatar: pollAvatar, avatarMime: pollAvatarMime };
                                } else {
                                    toastOpts = { avatarInitial: pollEditor.charAt(0).toUpperCase() };
                                }
                            }
                            showToast(editorMsg, toastOpts);
                            var pollOpts = { noFocus: true, isPollRefresh: true };
                            var active = document.activeElement;
                            var editBody = document.getElementById('wh-edit-body');
                            if (active && active !== document.body && editBody && editBody.contains(active) && active.id) {
                                pollOpts.restoreFocusId = active.id;
                                if (typeof active.selectionStart === 'number') {
                                    pollOpts.restoreSelStart = active.selectionStart;
                                    pollOpts.restoreSelEnd = active.selectionEnd;
                                }
                            }
                            openDoc(workId, pollOpts);
                        }
                    } else {
                        state.pollMtime = newMtime;
                    }
                });
            }, 500);
        });
    }

    function stopPoll() {
        if (state.pollTimer) {
            clearInterval(state.pollTimer);
            state.pollTimer = null;
        }
        state.pollConflictShown = false;
    }

    function handleDeleted() {
        stopPoll();
        var confirmFn = (window.parent && typeof window.parent.showConfirmDialog === 'function')
            ? window.parent.showConfirmDialog : null;
        if (confirmFn) {
            confirmFn(t('docDeleted'), '', { yesLabel: t('backBtn'), hideNo: true }).then(function () {
                backToList();
            });
        } else {
            backToList();
        }
    }

    function handleConflict(serverItem, editor) {
        function doMerge(srv) {
            var remoteTitleChanged = (srv.title || '') !== state.baseTitle;
            var remoteBodyChanged  = (srv.body  || '') !== state.baseBody;
            var remoteTagsChanged  = (srv.tags  || '') !== state.baseTags;

            var hasConflict = (state.dirtyTitle && remoteTitleChanged) ||
                              (state.dirtyBody  && remoteBodyChanged)  ||
                              (state.dirtyTags  && remoteTagsChanged);

            if (!hasConflict) {
                var mergedItem = Object.assign({}, srv);
                if (state.dirtyTitle) mergedItem.title = collectTitle();
                if (state.dirtyBody)  mergedItem.body  = collectBody();
                if (state.dirtyTags)  mergedItem.tags  = collectTags();

                state.currentVersion = srv.version;
                state.currentOwnerId = srv.owner_id || state.currentOwnerId;
                state.isOwner = !!srv.is_owner;
                state.baseTitle = srv.title || '';
                state.baseBody  = srv.body  || '';
                state.baseTags  = srv.tags  || '';
                if (!state.dirtyBody) {
                    state.currentVisibility = srv.visibility || state.currentVisibility;
                    state.currentGroupId    = srv.group_id   || null;
                    if (srv.owner_write_only !== undefined) state.ownerWriteOnly = srv.owner_write_only;
                }
                state.pollConflictShown = false;

                var mergeOpts = { noFocus: true };
                var active = document.activeElement;
                var editBody = document.getElementById('wh-edit-body');
                if (active && active !== document.body && editBody && editBody.contains(active) && active.id) {
                    mergeOpts.restoreFocusId = active.id;
                    if (typeof active.selectionStart === 'number') {
                        mergeOpts.restoreSelStart = active.selectionStart;
                        mergeOpts.restoreSelEnd   = active.selectionEnd;
                    }
                }
                showEditView(mergedItem, mergeOpts);
                if (state.isDirty) immediatelySave();
                return;
            }

            var conflictTitle = editor
                ? t('conflictTitle').replace('{editor}', editor)
                : t('conflictTitleUnknown');
            var confirmFn = (window.parent && typeof window.parent.showConfirmDialog === 'function')
                ? window.parent.showConfirmDialog : null;
            if (confirmFn) {
                confirmFn(conflictTitle, t('conflictMsg')).then(function (ok) {
                    if (ok) {
                        openDoc(srv.id || state.currentId);
                    } else {
                        state.pollConflictShown = false;
                    }
                });
            }
        }

        if (serverItem) {
            doMerge(serverItem);
        } else {
            if (!state.currentId) return;
            callPython('work_get', { id: state.currentId }).then(function (res) {
                if (!res || !res.success) return;
                doMerge(res.item);
            });
        }
    }

    // -----------------------------------------------------------------------
    // Navigation
    // -----------------------------------------------------------------------
    function saveHistoryOnLeave() {
        if (state.diffMode) return;
        if (!state.currentId || !state.hasInserted) return;
        var body = collectBody();
        if (body === '' || body === state.bodyAtOpen) return;
        // flush save: isNewDraft 해제, 최종 공유 설정으로 저장
        var wasNewDraft = state.isNewDraft;
        state.isNewDraft = false;
        callPython('work_save', {
            id: state.currentId,
            title: collectTitle(),
            body: body,
            skip_body: true,
            tags: collectTags(),
            visibility: state.currentVisibility,
            group_id: state.currentGroupId,
            owner_write_only: state.ownerWriteOnly,
            version: state.currentVersion,
            history_body: wasNewDraft ? '' : body,
            history_title: wasNewDraft ? '' : collectTitle(),
        });
    }

    function backToList() {
        stopPoll();
        if (!state.diffMode) {
            saveHistoryOnLeave();
            if (state.isDirty) {
                // isDirty 저장 시에도 isNewDraft 해제 (saveHistoryOnLeave 후)
                state.isNewDraft = false;
                immediatelySave();
            }
        }
        state.historyMode = false;
        state.historyViewId = null;
        state.bodyAtOpen = null;
        state.lastEditedAt = null;
        state.historySaved = false;
        state.historyPreBody = null;
        state.historyPreTitle = null;
        state.historyPreTags = null;
        state.diffMode = false;
        state.diffOldBody = null;
        state.diffNewBody = null;
        state.diffOldLabel = '';
        state.diffNewLabel = '';
        state.diffOldTitle = null;
        state.diffNewTitle = null;
        state.diffPreBody = null;
        state.diffPreTitle = null;
        state.diffPreTags = null;
        showListView();
        state.currentId = null;
        state.isDirty = false;
        state.dirtyTitle = false;
        state.dirtyBody = false;
        state.dirtyTags = false;
        state.hasInserted = false;
        if (state.isSearchMode) {
            doSearch();
        } else {
            loadList();
        }
    }

    function showListView() {
        document.getElementById('wh-list-view').style.display = '';
        document.getElementById('wh-edit-view').style.display = 'none';
        state.view = 'list';
    }

    // -----------------------------------------------------------------------
    // Delete
    // -----------------------------------------------------------------------
    function deleteDoc() {
        if (!state.currentId) { backToList(); return; }
        var confirmFn = (window.parent && typeof window.parent.showConfirmDialog === 'function')
            ? window.parent.showConfirmDialog : null;
        if (confirmFn) {
            confirmFn(t('deleteConfirmTitle'), '', { yesStyle: 'danger' }).then(function (ok) {
                if (ok) doDelete();
            });
        } else {
            doDelete();
        }
    }

    function doDelete() {
        callPython('work_delete', { id: state.currentId }).then(function (res) {
            if (res && res.success) {
                state.currentId = null;
                state.isDirty = false;
                backToList();
            } else if (res && res.error === 'forbidden') {
                showToast(t('onlyOwnerDelete'));
            }
        });
    }

    // -----------------------------------------------------------------------
    // History
    // -----------------------------------------------------------------------
    function buildHistoryBtn() {
        var btn = el('button', { className: 'wh-history-btn', id: 'wh-history-btn' });
        var iconSpan = el('span', { className: 'wh-history-icon' });
        iconSpan.innerHTML = CLOCK_ICON_SVG;
        var textSpan = el('span', { id: 'wh-history-label' });
        textSpan.textContent = state.historyMode ? ('v' + state.historyViewId) : t('historyLatest');
        btn.appendChild(iconSpan);
        btn.appendChild(textSpan);
        btn.addEventListener('click', onHistoryBtnClick);
        return btn;
    }

    function onHistoryBtnClick() {
        if (state.historyMode) {
            exitHistoryReadMode();
        } else {
            openHistoryPanel();
        }
    }

    function openHistoryPanel() {
        if (!state.currentId) return;
        var modal = window.parent && window.parent.desktopModal;
        if (!modal) return;
        callPython('history_list', { id: state.currentId }).then(function (res) {
            if (!res || !res.success) { showToast(t('historyLoadFail')); return; }
            var entries = res.entries || [];
            if (entries.length === 0) {
                showToast(t('noHistory'));
                return;
            }
            var dlg = document.createElement('div');
            dlg.style.cssText = 'max-height:360px;overflow-y:auto;';
            entries.forEach(function (entry, idx) {
                var row = document.createElement('div');
                row.style.cssText = 'display:flex;align-items:center;padding:6px 0;border-bottom:1px solid var(--border-color,#373c47);';
                var info = document.createElement('div');
                info.style.cssText = 'flex:1;display:flex;align-items:center;font-size:12px;color:var(--text-secondary,#8b8f9b);';
                if (entry.saved_by_avatar) {
                    var avatarImg = document.createElement('img');
                    avatarImg.src = 'data:' + (entry.saved_by_avatar_mime || 'image/jpeg') + ';base64,' + entry.saved_by_avatar;
                    avatarImg.style.cssText = 'width:18px;height:18px;border-radius:50%;object-fit:cover;margin-right:5px;flex-shrink:0;';
                    info.appendChild(avatarImg);
                } else if (entry.saved_by) {
                    var avatarPlaceholder = document.createElement('div');
                    avatarPlaceholder.style.cssText = 'width:18px;height:18px;border-radius:50%;background:var(--border-color,#373c47);display:flex;align-items:center;justify-content:center;font-size:9px;color:var(--text-secondary,#8b8f9b);margin-right:5px;flex-shrink:0;';
                    avatarPlaceholder.textContent = (entry.saved_by_display || entry.saved_by).charAt(0).toUpperCase();
                    info.appendChild(avatarPlaceholder);
                }
                var infoText = document.createElement('span');
                var name = entry.saved_by_display || entry.saved_by || '';
                var entryLabel = name + (name ? ' · ' : '') + fmtDate(entry.edited_at);
                infoText.textContent = entryLabel;
                info.appendChild(infoText);

                var btnStyle = 'margin-right:4px;font-size:11px;padding:2px 7px;';

                var readBtn = document.createElement('button');
                readBtn.className = 'btn btn-sm btn-secondary';
                readBtn.style.cssText = btnStyle;
                readBtn.textContent = t('historyView');

                var cmpCurrentBtn = document.createElement('button');
                cmpCurrentBtn.className = 'btn btn-sm btn-secondary';
                cmpCurrentBtn.style.cssText = btnStyle;
                cmpCurrentBtn.textContent = t('historyCompareCurrent');

                var cmpPrevBtn = document.createElement('button');
                cmpPrevBtn.className = 'btn btn-sm btn-secondary';
                cmpPrevBtn.style.cssText = btnStyle;
                cmpPrevBtn.textContent = t('historyComparePrev');
                // 가장 오래된 항목(마지막 인덱스)에서 [직전과 비교] 비활성화
                var isOldest = (idx === entries.length - 1);
                if (isOldest) {
                    cmpPrevBtn.disabled = true;
                    cmpPrevBtn.style.opacity = '0.4';
                    cmpPrevBtn.style.cursor = 'not-allowed';
                }

                var applyBtn = document.createElement('button');
                applyBtn.className = 'btn btn-sm btn-secondary';
                applyBtn.style.cssText = 'font-size:11px;padding:2px 7px;';
                applyBtn.textContent = t('historyApply');

                (function (e, eIdx, eLabel) {
                    readBtn.addEventListener('click', function () {
                        modal.close();
                        callPython('history_get', { history_id: e.id }).then(function (gr) {
                            if (!gr || !gr.success) { showToast(t('historyLoadFail')); return; }
                            enterHistoryReadMode(e.id, gr.entry.body);
                        });
                    });
                    cmpCurrentBtn.addEventListener('click', function () {
                        modal.close();
                        callPython('history_get', { history_id: e.id }).then(function (gr) {
                            if (!gr || !gr.success) { showToast(t('historyLoadFail')); return; }
                            var currentBody = state.diffMode ? state.diffPreBody : (state.historyMode ? state.historyPreBody : collectBody());
                            if (currentBody === null) currentBody = state.baseBody;
                            var currentTitle = state.diffMode ? state.diffPreTitle : (state.historyMode ? state.historyPreTitle : collectTitle());
                            if (currentTitle === null) currentTitle = state.baseTitle;
                            var oldTitle = gr.entry.title || state.baseTitle;
                            enterDiffMode(gr.entry.body, currentBody, eLabel, t('diffCurrent'), oldTitle, currentTitle);
                        });
                    });
                    cmpPrevBtn.addEventListener('click', function () {
                        if (isOldest) return;
                        modal.close();
                        var nextEntry = entries[eIdx + 1];
                        callPython('history_get', { history_id: e.id }).then(function (gr) {
                            if (!gr || !gr.success) { showToast(t('historyLoadFail')); return; }
                            var curBody = gr.entry.body;
                            var curTitle = gr.entry.title || state.baseTitle;
                            callPython('history_get', { history_id: nextEntry.id }).then(function (gr2) {
                                var nextName = nextEntry.saved_by_display || nextEntry.saved_by || '';
                                var nextLabel = nextName + (nextName ? ' · ' : '') + fmtDate(nextEntry.edited_at);
                                if (!gr2 || !gr2.success) { showToast(t('historyLoadFail')); return; }
                                var prevTitle = gr2.entry.title || state.baseTitle;
                                // OLD(더 오래된 nextEntry)=왼쪽, NEW(선택한 e)=오른쪽
                                enterDiffMode(gr2.entry.body, curBody, nextLabel, eLabel, prevTitle, curTitle);
                            });
                        });
                    });
                    applyBtn.addEventListener('click', function () {
                        modal.close();
                        var confirmFn = (window.parent && typeof window.parent.showConfirmDialog === 'function')
                            ? window.parent.showConfirmDialog : null;
                        if (confirmFn) {
                            confirmFn(t('historyApplyConfirm'), '').then(function (ok) {
                                if (ok) applyHistory(e.id);
                            });
                        } else {
                            applyHistory(e.id);
                        }
                    });
                })(entry, idx, entryLabel);

                row.appendChild(info);
                row.appendChild(readBtn);
                row.appendChild(cmpCurrentBtn);
                row.appendChild(cmpPrevBtn);
                row.appendChild(applyBtn);
                dlg.appendChild(row);
            });
            modal.open({
                title: t('historyTitle'),
                element: dlg,
                width: '560px',
                buttons: [{ label: t('close'), onClick: function () { modal.close(); } }],
            });
        });
    }

    function applyHistory(historyId) {
        callPython('history_get', { history_id: historyId }).then(function (gr) {
            if (!gr || !gr.success) { showToast(t('historyLoadFail')); return; }
            var histBody = gr.entry.body;
            var prevTitle = state.historyMode ? (state.historyPreTitle || state.baseTitle) : collectTitle();
            var prevTags  = state.historyMode ? (state.historyPreTags  || state.baseTags)  : collectTags();
            state.historyMode = false;
            state.historyViewId = null;
            state.historyPreBody = null;
            state.historyPreTitle = null;
            state.historyPreTags = null;
            var currentItem = {
                id: state.currentId,
                title: prevTitle,
                template: state.currentTemplate,
                body: histBody,
                tags: prevTags,
                is_owner: state.isOwner,
                visibility: state.currentVisibility,
                group_id: state.currentGroupId,
            };
            showEditView(currentItem, { noFocus: true });
            state.dirtyBody = true;
            state.isDirty = true;
            immediatelySave();
        });
    }

    function enterHistoryReadMode(historyId, histBody) {
        state.historyPreTitle = collectTitle();
        state.historyPreBody  = collectBody();
        state.historyPreTags  = collectTags();
        state.historyMode = true;
        state.historyViewId = historyId;
        var container = document.getElementById('wh-edit-body');
        if (!container) return;
        container.innerHTML = '';
        var readItem = {
            id: state.currentId,
            title: state.historyPreTitle,
            template: state.currentTemplate,
            body: histBody,
            tags: state.historyPreTags,
        };
        buildEditBody(container, readItem, { readonlyMode: true, readonlyBody: histBody, noFocus: true });
        var lbl = document.getElementById('wh-history-label');
        if (lbl) lbl.textContent = 'v' + historyId;
        var histBtn = document.getElementById('wh-history-btn');
        if (histBtn) { histBtn.style.background = 'var(--accent-primary)'; histBtn.style.borderColor = 'var(--accent-primary)'; histBtn.style.color = '#fff'; }
        var visBtn = document.getElementById('wh-vis-btn');
        if (visBtn) { visBtn.disabled = true; visBtn.style.opacity = '0.35'; visBtn.style.pointerEvents = 'none'; }
        var delBtn = document.querySelector('.wh-delete-btn');
        if (delBtn) { delBtn.disabled = true; delBtn.style.opacity = '0.35'; delBtn.style.pointerEvents = 'none'; }
    }

    function exitHistoryReadMode() {
        var preTitle = state.historyPreTitle !== null ? state.historyPreTitle : state.baseTitle;
        var preBody  = state.historyPreBody  !== null ? state.historyPreBody  : state.baseBody;
        var preTags  = state.historyPreTags  !== null ? state.historyPreTags  : state.baseTags;
        state.historyMode = false;
        state.historyViewId = null;
        state.historyPreBody = null;
        state.historyPreTitle = null;
        state.historyPreTags = null;
        var container = document.getElementById('wh-edit-body');
        if (!container) return;
        container.innerHTML = '';
        var restoreItem = {
            id: state.currentId,
            title: preTitle,
            template: state.currentTemplate,
            body: preBody,
            tags: preTags,
        };
        buildEditBody(container, restoreItem, { noFocus: true });
        var lbl = document.getElementById('wh-history-label');
        if (lbl) lbl.textContent = t('historyLatest');
        var histBtn = document.getElementById('wh-history-btn');
        if (histBtn) { histBtn.style.background = ''; histBtn.style.borderColor = ''; histBtn.style.color = ''; }
        var visBtn = document.getElementById('wh-vis-btn');
        if (visBtn) { visBtn.disabled = false; visBtn.style.opacity = ''; visBtn.style.pointerEvents = ''; }
        var delBtn = document.querySelector('.wh-delete-btn');
        if (delBtn) { delBtn.disabled = false; delBtn.style.opacity = ''; delBtn.style.pointerEvents = ''; }
    }

    // -----------------------------------------------------------------------
    // Diff mode
    // -----------------------------------------------------------------------
    function buildDiffExitBtn() {
        var btn = el('button', { className: 'wh-diff-exit-btn' });
        btn.textContent = t('diffExit');
        btn.addEventListener('click', exitDiffMode);
        return btn;
    }

    function enterDiffMode(oldBody, newBody, oldLabel, newLabel, oldTitle, newTitle) {
        // 읽기 모드와 상호 배타적 — pre 값을 먼저 수집한 뒤 초기화
        if (state.historyMode) {
            state.diffPreTitle = state.historyPreTitle !== null ? state.historyPreTitle : state.baseTitle;
            state.diffPreBody  = state.historyPreBody  !== null ? state.historyPreBody  : state.baseBody;
            state.diffPreTags  = state.historyPreTags  !== null ? state.historyPreTags  : state.baseTags;
            state.historyMode = false;
            state.historyViewId = null;
            state.historyPreBody = null;
            state.historyPreTitle = null;
            state.historyPreTags = null;
        } else {
            state.diffPreTitle = collectTitle();
            state.diffPreBody  = collectBody();
            state.diffPreTags  = collectTags();
        }
        state.diffMode = true;
        state.diffOldBody = oldBody;
        state.diffNewBody = newBody;
        state.diffOldLabel = oldLabel;
        state.diffNewLabel = newLabel;
        state.diffOldTitle = (oldTitle !== undefined && oldTitle !== null) ? oldTitle : null;
        state.diffNewTitle = (newTitle !== undefined && newTitle !== null) ? newTitle : null;

        var header = document.getElementById('wh-edit-header');
        if (header) {
            // diff 종료 버튼으로 교체: history/delete 버튼 숨기기
            var histBtn = document.getElementById('wh-history-btn');
            if (histBtn) histBtn.style.display = 'none';
            var delBtn = header.querySelector('.wh-delete-btn');
            if (delBtn) delBtn.style.display = 'none';
            var visBtn = document.getElementById('wh-vis-btn');
            if (visBtn) { visBtn.disabled = true; visBtn.style.opacity = '0.35'; visBtn.style.pointerEvents = 'none'; }
            if (!document.getElementById('wh-diff-exit-btn')) {
                var exitBtn = buildDiffExitBtn();
                exitBtn.id = 'wh-diff-exit-btn';
                header.appendChild(exitBtn);
            }
        }

        var container = document.getElementById('wh-edit-body');
        if (!container) return;
        container.innerHTML = '';
        container.style.overflowY = 'hidden';
        container.style.display = 'flex';
        container.style.flexDirection = 'column';
        buildDiffBody(container, oldBody, newBody, state.currentTemplate, oldLabel, newLabel);
    }

    function exitDiffMode() {
        var preTitle = state.diffPreTitle !== null ? state.diffPreTitle : state.baseTitle;
        var preBody  = state.diffPreBody  !== null ? state.diffPreBody  : state.baseBody;
        var preTags  = state.diffPreTags  !== null ? state.diffPreTags  : state.baseTags;
        state.diffMode = false;
        state.diffOldBody = null;
        state.diffNewBody = null;
        state.diffOldLabel = '';
        state.diffNewLabel = '';
        state.diffOldTitle = null;
        state.diffNewTitle = null;
        state.diffPreBody = null;
        state.diffPreTitle = null;
        state.diffPreTags = null;

        var header = document.getElementById('wh-edit-header');
        if (header) {
            var exitBtn = document.getElementById('wh-diff-exit-btn');
            if (exitBtn) exitBtn.remove();
            var histBtn = document.getElementById('wh-history-btn');
            if (histBtn) histBtn.style.display = '';
            var delBtn = header.querySelector('.wh-delete-btn');
            if (delBtn) delBtn.style.display = '';
            var visBtn = document.getElementById('wh-vis-btn');
            if (visBtn) { visBtn.disabled = false; visBtn.style.opacity = ''; visBtn.style.pointerEvents = ''; }
        }

        var container = document.getElementById('wh-edit-body');
        if (!container) return;
        container.innerHTML = '';
        container.style.padding = '';
        container.style.overflowY = '';
        container.style.display = '';
        container.style.flexDirection = '';
        var restoreItem = {
            id: state.currentId,
            title: preTitle,
            template: state.currentTemplate,
            body: preBody,
            tags: preTags,
        };
        buildEditBody(container, restoreItem, { noFocus: true });
    }

    // -----------------------------------------------------------------------
    // Diff body rendering
    // -----------------------------------------------------------------------

    var DIFF_BG = {
        changed: 'rgba(255,200,0,0.18)',
        removed: 'rgba(255,80,80,0.18)',
        added:   'rgba(80,200,80,0.18)',
    };

    var DIFF_OUTLINE = {
        removed: 'rgba(255,80,80,0.85)',
        added:   'rgba(80,200,80,0.85)',
    };

    // Tokenize text into alternating [word, sep, word, sep, ...] array.
    // Separators are whitespace runs; kept so round-trip is lossless.
    function tokenizeWords(text) {
        return text.split(/(\s+)/);
    }

    // Strip markdown syntax characters to get the visible text of a token.
    // Used to find the token in the rendered preview DOM.
    function stripMdSyntax(tok) {
        // Remove bold/italic markers, backticks, heading hashes, blockquote >,
        // link/image brackets and parens, strikethrough ~~
        return tok
            .replace(/^#{1,6}\s*/, '')         // # heading prefix
            .replace(/^\s*>\s*/, '')            // blockquote >
            .replace(/~~(.*?)~~/g, '$1')        // ~~strike~~
            .replace(/\*\*(.*?)\*\*/g, '$1')    // **bold**
            .replace(/__(.*?)__/g, '$1')        // __bold__
            .replace(/\*(.*?)\*/g, '$1')        // *italic*
            .replace(/_(.*?)_/g, '$1')          // _italic_
            .replace(/`([^`]+)`/g, '$1')        // `code`
            .replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1') // ![alt](url) → alt
            .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')  // [text](url) → text
            .replace(/[*_`~[\]()]/g, '');       // remaining stray markers
    }

    // LCS on token arrays. Returns [{token, status}] where status is
    // 'same' | 'removed' | 'added'.
    function lcsTokenDiff(oldTokens, newTokens) {
        var m = oldTokens.length, n = newTokens.length;
        // Use flat array for DP to keep memory reasonable
        var dp = new Int32Array((m + 1) * (n + 1));
        var i, j;
        for (i = 1; i <= m; i++) {
            for (j = 1; j <= n; j++) {
                if (oldTokens[i - 1] === newTokens[j - 1]) {
                    dp[i * (n + 1) + j] = dp[(i - 1) * (n + 1) + (j - 1)] + 1;
                } else {
                    dp[i * (n + 1) + j] = Math.max(dp[(i - 1) * (n + 1) + j], dp[i * (n + 1) + (j - 1)]);
                }
            }
        }
        var result = [];
        i = m; j = n;
        while (i > 0 || j > 0) {
            if (i > 0 && j > 0 && oldTokens[i - 1] === newTokens[j - 1]) {
                result.unshift({ token: oldTokens[i - 1], status: 'same' });
                i--; j--;
            } else if (j > 0 && (i === 0 || dp[i * (n + 1) + (j - 1)] >= dp[(i - 1) * (n + 1) + j])) {
                result.unshift({ token: newTokens[j - 1], status: 'added' });
                j--;
            } else {
                result.unshift({ token: oldTokens[i - 1], status: 'removed' });
                i--;
            }
        }
        return result;
    }

    // Collect all text nodes inside el, with cumulative character offsets.
    // Returns [{node, start, end}] sorted by document order.
    function collectTextNodes(el) {
        var result = [];
        var offset = 0;
        var walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null, false);
        var node;
        while ((node = walker.nextNode())) {
            var len = node.nodeValue.length;
            result.push({ node: node, start: offset, end: offset + len });
            offset += len;
        }
        return result;
    }

    // Apply per-word outline highlights to a rendered preview element.
    // Collects all ranges to wrap first, then applies them in one DOM pass to avoid
    // snapshot invalidation caused by splitText/insertBefore mutations.
    // side: 'removed' | 'added'
    // diffTokens: [{token, status}] for one side (same tokens in order + changed ones)
    function applyTokenOutlines(previewEl, diffTokens, side) {
        var snapshot = collectTextNodes(previewEl);
        if (!snapshot.length) return;

        var visText = snapshot.map(function (tn) { return tn.node.nodeValue; }).join('');
        var color = DIFF_OUTLINE[side];

        // Phase 1: collect all [charStart, charEnd) ranges to highlight
        var ranges = [];
        var cursor = 0;
        for (var i = 0; i < diffTokens.length; i++) {
            var dt = diffTokens[i];
            var tok = dt.token;
            if (!tok || /^\s+$/.test(tok)) continue;
            var searchTok = stripMdSyntax(tok);
            if (!searchTok) continue;
            var pos = visText.indexOf(searchTok, cursor);
            if (pos === -1) continue;
            cursor = pos + searchTok.length;
            if (dt.status === side) {
                ranges.push({ start: pos, end: pos + searchTok.length });
            }
        }
        if (!ranges.length) return;

        // Phase 2: for each range, collect the per-text-node fragments (no DOM mutation yet)
        // Each entry: {snapshotIdx, localStart, localEnd, isFirst, isLast}
        var allFragments = [];
        for (var ri = 0; ri < ranges.length; ri++) {
            var rStart = ranges[ri].start, rEnd = ranges[ri].end;
            var frags = [];
            for (var si = 0; si < snapshot.length; si++) {
                var tn = snapshot[si];
                if (tn.end <= rStart || tn.start >= rEnd) continue;
                var ls = Math.max(rStart, tn.start) - tn.start;
                var le = Math.min(rEnd,   tn.end)   - tn.start;
                if (ls >= le) continue;
                frags.push({ si: si, localStart: ls, localEnd: le });
            }
            for (var fi = 0; fi < frags.length; fi++) {
                frags[fi].isFirst = (fi === 0);
                frags[fi].isLast  = (fi === frags.length - 1);
                allFragments.push(frags[fi]);
            }
        }

        // Phase 3: apply DOM mutations.
        // Process fragments in reverse snapshot order so that splitText offsets
        // within the same text node remain valid (later offsets first).
        // Sort by (snapshotIdx DESC, localStart DESC)
        allFragments.sort(function (a, b) {
            if (b.si !== a.si) return b.si - a.si;
            return b.localStart - a.localStart;
        });

        for (var fi = 0; fi < allFragments.length; fi++) {
            var frag = allFragments[fi];
            var node = snapshot[frag.si].node;
            // splitText(localEnd) first (tail), then splitText(localStart) (prefix)
            // This preserves localStart for the second split.
            if (frag.localEnd < node.nodeValue.length) node.splitText(frag.localEnd);
            var targetNode = frag.localStart > 0 ? node.splitText(frag.localStart) : node;

            var isFirst = frag.isFirst, isLast = frag.isLast;
            var span = document.createElement('span');
            var bt = '1.5px solid ' + color;
            var bb = '1.5px solid ' + color;
            var bl = isFirst ? '1.5px solid ' + color : 'none';
            var br = isLast  ? '1.5px solid ' + color : 'none';
            span.style.cssText = 'border-top:' + bt + ';border-bottom:' + bb +
                ';border-left:' + bl + ';border-right:' + br +
                ';border-radius:' + (isFirst && isLast ? '2px' : isFirst ? '2px 0 0 2px' : isLast ? '0 2px 2px 0' : '0') +
                ';padding:0 1px;box-sizing:border-box;line-height:inherit;display:inline;';
            targetNode.parentNode.insertBefore(span, targetNode);
            span.appendChild(targetNode);
        }
    }

    // Compute changed-token stats: {total, changed}  (non-whitespace tokens only)
    function changedStats(diffTokens) {
        var total = 0, changed = 0;
        for (var i = 0; i < diffTokens.length; i++) {
            if (/^\s+$/.test(diffTokens[i].token)) continue;
            total++;
            if (diffTokens[i].status !== 'same') changed++;
        }
        return { total: total, changed: changed };
    }

    // LCS on line arrays. Returns [{line, status}] where status is 'same'|'removed'|'added'.
    function lcsLineDiff(oldLines, newLines) {
        var m = oldLines.length, n = newLines.length;
        // For very large line counts, use a flat Int32Array
        var dp = new Int32Array((m + 1) * (n + 1));
        var i, j;
        for (i = 1; i <= m; i++) {
            for (j = 1; j <= n; j++) {
                if (oldLines[i - 1] === newLines[j - 1]) {
                    dp[i * (n + 1) + j] = dp[(i - 1) * (n + 1) + (j - 1)] + 1;
                } else {
                    dp[i * (n + 1) + j] = Math.max(dp[(i - 1) * (n + 1) + j], dp[i * (n + 1) + (j - 1)]);
                }
            }
        }
        var result = [];
        i = m; j = n;
        while (i > 0 || j > 0) {
            if (i > 0 && j > 0 && oldLines[i - 1] === newLines[j - 1]) {
                result.unshift({ line: oldLines[i - 1], status: 'same' });
                i--; j--;
            } else if (j > 0 && (i === 0 || dp[i * (n + 1) + (j - 1)] >= dp[(i - 1) * (n + 1) + j])) {
                result.unshift({ line: newLines[j - 1], status: 'added' });
                j--;
            } else {
                result.unshift({ line: oldLines[i - 1], status: 'removed' });
                i--;
            }
        }
        return result;
    }

    // High-level: diff two markdown source texts and apply outlines to both panels.
    // Strategy: line-level LCS first, then word-level diff only on changed lines.
    // This keeps complexity proportional to the number of changed lines regardless
    // of total document size.
    function applyMdDiffOutlines(oldPreview, newPreview, oldText, newText, fallbackOld, fallbackNew) {
        var oldLines = oldText.split('\n');
        var newLines = newText.split('\n');

        // Guard against absurd line counts
        if (oldLines.length * newLines.length > 4000000) {
            if (fallbackOld) fallbackOld.style.background = DIFF_BG.removed;
            if (fallbackNew) fallbackNew.style.background = DIFF_BG.added;
            return;
        }

        var lineDiff = lcsLineDiff(oldLines, newLines);

        // Pair up consecutive removed+added lines as "changed" pairs for word diff.
        // Remaining unpaired removed/added lines get word diff against empty string.
        var pairs = []; // [{oldLine, newLine}]  — one or both may be null for pure add/remove
        var k = 0;
        while (k < lineDiff.length) {
            if (lineDiff[k].status === 'removed') {
                if (k + 1 < lineDiff.length && lineDiff[k + 1].status === 'added') {
                    pairs.push({ oldLine: lineDiff[k].line, newLine: lineDiff[k + 1].line });
                    k += 2;
                } else {
                    pairs.push({ oldLine: lineDiff[k].line, newLine: null });
                    k++;
                }
            } else if (lineDiff[k].status === 'added') {
                pairs.push({ oldLine: null, newLine: lineDiff[k].line });
                k++;
            } else {
                k++; // same — skip
            }
        }

        if (!pairs.length) return; // no changes

        // Build combined word-diff token lists for each side by concatenating
        // per-line word diffs. Insert 'same' newline separators between lines
        // so cursor tracking stays correct when searching in visText.
        var oldDiff = [], newDiff = [];
        for (var pi = 0; pi < pairs.length; pi++) {
            var pair = pairs[pi];
            var oLine = pair.oldLine !== null ? pair.oldLine : '';
            var nLine = pair.newLine !== null ? pair.newLine : '';
            var oTok = tokenizeWords(oLine);
            var nTok = tokenizeWords(nLine);
            var wdiff = lcsTokenDiff(oTok, nTok);
            for (var wi = 0; wi < wdiff.length; wi++) {
                var wd = wdiff[wi];
                if (wd.status === 'same' || wd.status === 'removed') oldDiff.push(wd);
                if (wd.status === 'same' || wd.status === 'added')   newDiff.push(wd);
            }
        }

        applyTokenOutlines(oldPreview, oldDiff, 'removed');
        applyTokenOutlines(newPreview, newDiff, 'added');
    }

    // Return flat list of {val, done?} for LCS alignment (todo/checklist only).
    function diffItems(bodyJson, template) {
        var data = {};
        try { data = JSON.parse(bodyJson || '{}'); } catch (e) {}
        if (template === 'todo' || template === 'checklist') {
            var items = Array.isArray(data.items) ? data.items : [];
            return items.map(function (it) { return { val: it.text || '', done: !!it.done }; });
        }
        return [];
    }

    // LCS-based alignment: returns [{oldIdx, newIdx, status}]
    // status: 'same' | 'changed' | 'removed' | 'added'
    function lcsAlignItems(oldItems, newItems) {
        var m = oldItems.length, n = newItems.length;
        var dp = [], i, j;
        for (i = 0; i <= m; i++) { dp[i] = []; for (j = 0; j <= n; j++) dp[i][j] = 0; }
        for (i = 1; i <= m; i++) {
            for (j = 1; j <= n; j++) {
                if (oldItems[i-1].val === newItems[j-1].val && oldItems[i-1].done === newItems[j-1].done) {
                    dp[i][j] = dp[i-1][j-1] + 1;
                } else {
                    dp[i][j] = Math.max(dp[i-1][j], dp[i][j-1]);
                }
            }
        }
        var aligned = [];
        i = m; j = n;
        while (i > 0 || j > 0) {
            if (i > 0 && j > 0 && oldItems[i-1].val === newItems[j-1].val && oldItems[i-1].done === newItems[j-1].done) {
                aligned.unshift({ oldIdx: i-1, newIdx: j-1, status: 'same' });
                i--; j--;
            } else if (j > 0 && (i === 0 || dp[i][j-1] >= dp[i-1][j])) {
                aligned.unshift({ oldIdx: -1, newIdx: j-1, status: 'added' });
                j--;
            } else {
                aligned.unshift({ oldIdx: i-1, newIdx: -1, status: 'removed' });
                i--;
            }
        }
        // merge consecutive removed+added into changed
        var result = [];
        var k = 0;
        while (k < aligned.length) {
            if (k + 1 < aligned.length && aligned[k].status === 'removed' && aligned[k+1].status === 'added') {
                result.push({ oldIdx: aligned[k].oldIdx, newIdx: aligned[k+1].newIdx, status: 'changed' });
                k += 2;
            } else {
                result.push(aligned[k]);
                k++;
            }
        }
        return result;
    }

    function buildDiffBody(container, oldBodyJson, newBodyJson, template, oldLabel, newLabel) {
        container.style.padding = '0';

        var preTags  = state.diffPreTags  !== null ? state.diffPreTags  : state.baseTags;
        var fallbackTitle = state.diffPreTitle !== null ? state.diffPreTitle : state.baseTitle;
        var oldTitle = state.diffOldTitle !== null ? state.diffOldTitle : fallbackTitle;
        var newTitle = state.diffNewTitle !== null ? state.diffNewTitle : fallbackTitle;

        var oldItem = { id: state.currentId, title: oldTitle, template: template, body: oldBodyJson, tags: preTags };
        var newItem = { id: state.currentId, title: newTitle, template: template, body: newBodyJson, tags: preTags };

        // label bar
        var labelRow = el('div', { className: 'wh-diff-label-row' });
        var oldLabelEl = el('div', { className: 'wh-diff-col-label' });
        oldLabelEl.textContent = oldLabel;
        var newLabelEl = el('div', { className: 'wh-diff-col-label' });
        newLabelEl.textContent = newLabel;
        labelRow.appendChild(oldLabelEl);
        labelRow.appendChild(newLabelEl);
        container.appendChild(labelRow);

        // two panels side by side
        var panels = el('div', { className: 'wh-diff-panels' });

        var oldPanel = el('div', { className: 'wh-diff-panel' });
        var newPanel = el('div', { className: 'wh-diff-panel' });

        buildEditBody(oldPanel, oldItem, { readonlyMode: true, readonlyBody: oldBodyJson, noFocus: true });
        buildEditBody(newPanel, newItem, { readonlyMode: true, readonlyBody: newBodyJson, noFocus: true });

        panels.appendChild(oldPanel);
        panels.appendChild(newPanel);
        container.appendChild(panels);

        // apply highlights after DOM is attached
        applyDiffHighlights(oldPanel, newPanel, oldBodyJson, newBodyJson, oldItem, newItem, template);
    }

    function applyDiffHighlights(oldPanel, newPanel, oldBodyJson, newBodyJson, oldItem, newItem, template) {
        // title diff
        if (oldItem.title !== newItem.title) {
            var oTitleEl = oldPanel.querySelector('.wh-title-input');
            var nTitleEl = newPanel.querySelector('.wh-title-input');
            if (oTitleEl) oTitleEl.style.background = DIFF_BG.removed;
            if (nTitleEl) nTitleEl.style.background = DIFF_BG.added;
        }

        var oldData = {}, newData = {};
        try { oldData = JSON.parse(oldBodyJson || '{}'); } catch (e) {}
        try { newData = JSON.parse(newBodyJson || '{}'); } catch (e) {}

        if (template === 'note') {
            var oText = (oldData.text || '').replace(/data:image\/[^;]+;base64,[A-Za-z0-9+/=]+/g, '[image]');
            var nText = (newData.text || '').replace(/data:image\/[^;]+;base64,[A-Za-z0-9+/=]+/g, '[image]');
            if (oText !== nText) {
                var oMdWrap = oldPanel.querySelector('.sk-md-wrap');
                var nMdWrap = newPanel.querySelector('.sk-md-wrap');
                var oPreview = oMdWrap && oMdWrap.querySelector('.sk-md-preview');
                var nPreview = nMdWrap && nMdWrap.querySelector('.sk-md-preview');
                if (oPreview && nPreview) {
                    applyMdDiffOutlines(oPreview, nPreview, oText, nText, oMdWrap, nMdWrap);
                } else {
                    if (oMdWrap) oMdWrap.style.background = DIFF_BG.removed;
                    if (nMdWrap) nMdWrap.style.background = DIFF_BG.added;
                }
            }
        } else if (template === 'command') {
            var oCmd = (oldData.command || ''), nCmd = (newData.command || '');
            var oDesc = (oldData.description || ''), nDesc = (newData.description || '');
            if (oCmd !== nCmd) {
                var oCmdEl = oldPanel.querySelector('.wh-command-wrap') || oldPanel.querySelector('.wh-command-input');
                var nCmdEl = newPanel.querySelector('.wh-command-wrap') || newPanel.querySelector('.wh-command-input');
                if (oCmdEl) oCmdEl.style.background = DIFF_BG.removed;
                if (nCmdEl) nCmdEl.style.background = DIFF_BG.added;
            }
            if (oDesc !== nDesc) {
                var oDescWrap = oldPanel.querySelector('.sk-md-wrap');
                var nDescWrap = newPanel.querySelector('.sk-md-wrap');
                var oDescPreview = oDescWrap && oDescWrap.querySelector('.sk-md-preview');
                var nDescPreview = nDescWrap && nDescWrap.querySelector('.sk-md-preview');
                if (oDescPreview && nDescPreview) {
                    applyMdDiffOutlines(oDescPreview, nDescPreview, oDesc, nDesc, oDescWrap, nDescWrap);
                } else {
                    if (oDescWrap) oDescWrap.style.background = DIFF_BG.removed;
                    if (nDescWrap) nDescWrap.style.background = DIFF_BG.added;
                }
            }
        } else if (template === 'todo' || template === 'checklist') {
            var oldItemsList = diffItems(oldBodyJson, template);
            var newItemsList = diffItems(newBodyJson, template);
            var aligned = lcsAlignItems(oldItemsList, newItemsList);

            var rowSel = template === 'todo' ? '.wh-todo-item' : '.wh-cl-item';
            var oldRows = Array.from(oldPanel.querySelectorAll(rowSel));
            var newRows = Array.from(newPanel.querySelectorAll(rowSel));

            // track which rows have been highlighted
            var oldHighlighted = {}, newHighlighted = {};
            aligned.forEach(function (pair) {
                if (pair.status === 'same') return;
                if (pair.oldIdx >= 0 && oldRows[pair.oldIdx] && !oldHighlighted[pair.oldIdx]) {
                    oldRows[pair.oldIdx].style.background = pair.status === 'removed' ? DIFF_BG.removed : DIFF_BG.changed;
                    oldHighlighted[pair.oldIdx] = true;
                }
                if (pair.newIdx >= 0 && newRows[pair.newIdx] && !newHighlighted[pair.newIdx]) {
                    newRows[pair.newIdx].style.background = pair.status === 'added' ? DIFF_BG.added : DIFF_BG.changed;
                    newHighlighted[pair.newIdx] = true;
                }
            });
        }
    }

    // -----------------------------------------------------------------------
    // Search
    // -----------------------------------------------------------------------
    function doSearch() {
        var input = document.getElementById('wh-search-input');
        var query = input ? input.value.trim() : '';
        if (!query) {
            clearSearch();
            return;
        }
        var docJumpMatch = query.match(/^\/go\s+(\d+)$/i);
        if (docJumpMatch) {
            var docId = parseInt(docJumpMatch[1], 10);
            callPython('work_get', { id: docId }).then(function (res) {
                if (!res || !res.success) {
                    showToast(t('docNotFound'));
                    return;
                }
                if (input) input.value = '';
                openDoc(docId);
            });
            return;
        }
        if (query === '/my') {
            if (input) input.value = '';
            state.searchQuery = '/my';
            state.isSearchMode = true;
            callPython('work_list_my', {}).then(function (res) {
                if (!res || !res.success) return;
                renderList(res.items, true, t('myDocs'), true);
            });
            return;
        }
        if (query === '/history' || query === '/history ') {
            if (input) input.value = '';
            openActionHistoryDialog();
            return;
        }
        state.searchQuery = query;
        state.isSearchMode = true;
        callPython('work_search', { query: query }).then(function (res) {
            if (!res || !res.success) return;
            renderList(res.items, true, query, true);
        });
    }

    function fmtActedAt(iso) {
        if (!iso) return '';
        var d = new Date(iso.replace('Z', '+00:00'));
        var locale = currentLanguage === 'ko' ? 'ko-KR' : 'en-US';
        return d.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' });
    }

    function fmtActionDateGroup(iso) {
        if (!iso) return '';
        var d = new Date(iso.replace('Z', '+00:00'));
        var now = new Date();
        var todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        var itemStart = new Date(d.getFullYear(), d.getMonth(), d.getDate());
        var diffDays = Math.round((todayStart - itemStart) / 86400000);
        if (diffDays === 0) return t('actionHistoryToday');
        if (diffDays === 1) return t('actionHistoryYesterday');
        if (diffDays < 7) return t('actionHistoryDaysAgo').replace('{n}', diffDays);
        var locale = currentLanguage === 'ko' ? 'ko-KR' : 'en-US';
        return d.toLocaleDateString(locale, { year: 'numeric', month: 'short', day: 'numeric' });
    }

    function getActionLabel(action) {
        var map = {
            create: t('actionCreate'),
            edit: t('actionEdit'),
            delete: t('actionDelete'),
            copy: t('actionCopy'),
            link_add: t('actionLinkAdd'),
            link_remove: t('actionLinkRemove'),
            tag: t('actionTag'),
            share: t('actionShare'),
        };
        return map[action] || action;
    }

    function openActionHistoryDialog() {
        var modal = window.parent && window.parent.desktopModal;
        if (!modal) return;

        callPython('action_log_list', {}).then(function (res) {
            if (!res || !res.success) { showToast(t('historyLoadFail')); return; }
            var items = res.items || [];

            var dlg = document.createElement('div');
            dlg.style.cssText = 'max-height:400px;overflow-y:auto;';

            if (items.length === 0) {
                var empty = document.createElement('div');
                empty.style.cssText = 'font-size:13px;color:var(--text-secondary,#8b8f9b);padding:12px 0;';
                empty.textContent = t('actionHistoryEmpty');
                dlg.appendChild(empty);
            } else {
                var lastGroup = null;
                var rowStyle = 'display:flex;align-items:center;padding:5px 0;border-bottom:1px solid var(--border-color,#373c47);font-size:13px;';
                var timeStyle = 'min-width:36px;color:var(--text-secondary,#8b8f9b);font-size:11px;flex-shrink:0;margin-right:6px;';
                var iconStyle = 'flex-shrink:0;margin-right:6px;';
                var titleStyle = 'flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;cursor:pointer;margin-right:6px;';
                var titleDeadStyle = 'flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text-secondary,#8b8f9b);text-decoration:line-through;margin-right:6px;';
                var actionLabelStyle = 'flex-shrink:0;color:var(--text-secondary,#8b8f9b);font-size:12px;margin-right:4px;';
                var detailStyle = 'font-size:11px;color:var(--text-secondary,#8b8f9b);padding:2px 0 4px 50px;';
                var groupHeaderStyle = 'font-size:11px;font-weight:600;color:var(--text-secondary,#8b8f9b);text-transform:uppercase;letter-spacing:0.4px;padding:10px 0 4px 0;';

                items.forEach(function (item) {
                    var group = fmtActionDateGroup(item.acted_at);
                    if (group !== lastGroup) {
                        lastGroup = group;
                        var hdr = document.createElement('div');
                        hdr.style.cssText = groupHeaderStyle;
                        hdr.textContent = group;
                        dlg.appendChild(hdr);
                    }

                    var row = document.createElement('div');
                    row.style.cssText = rowStyle;

                    var timeSpan = document.createElement('span');
                    timeSpan.style.cssText = timeStyle;
                    timeSpan.textContent = fmtActedAt(item.acted_at);
                    row.appendChild(timeSpan);

                    var iconWrap = document.createElement('span');
                    iconWrap.style.cssText = iconStyle;
                    if (item.work_type) {
                        iconWrap.appendChild(makeIcon(item.work_type, 14));
                    }
                    row.appendChild(iconWrap);

                    var isDeleted = (item.action === 'delete');
                    var titleSpan = document.createElement('span');
                    titleSpan.style.cssText = isDeleted ? titleDeadStyle : titleStyle;
                    titleSpan.textContent = item.work_title || t('untitled');
                    if (!isDeleted && item.work_id) {
                        (function (wid) {
                            titleSpan.addEventListener('click', function () {
                                modal.close();
                                openDoc(wid);
                            });
                        })(item.work_id);
                    }
                    row.appendChild(titleSpan);

                    var actionSpan = document.createElement('span');
                    actionSpan.style.cssText = actionLabelStyle;
                    actionSpan.textContent = getActionLabel(item.action);
                    row.appendChild(actionSpan);

                    if (item.action === 'edit') {
                        var diffBtn = document.createElement('button');
                        diffBtn.className = 'btn btn-sm btn-secondary';
                        diffBtn.style.cssText = 'font-size:11px;padding:2px 7px;flex-shrink:0;';
                        diffBtn.textContent = t('actionDiff');
                        if (!item.diff_available) {
                            diffBtn.disabled = true;
                            diffBtn.style.opacity = '0.4';
                            diffBtn.style.cursor = 'not-allowed';
                        } else {
                            (function (histId, prevHistId, wid, logTitle) {
                                diffBtn.addEventListener('click', function () {
                                    modal.close();
                                    Promise.all([
                                        callPython('history_get', { history_id: histId }),
                                        callPython('history_get', { history_id: prevHistId })
                                    ]).then(function (results) {
                                        var gr = results[0], grPrev = results[1];
                                        if (!gr || !gr.success || !grPrev || !grPrev.success) {
                                            showToast(t('historyLoadFail')); return;
                                        }
                                        var newTitle = gr.entry.title || logTitle;
                                        var oldTitle = grPrev.entry.title || newTitle;
                                        var newLabel = fmtDate(gr.entry.edited_at);
                                        var oldLabel = fmtDate(grPrev.entry.edited_at);
                                        openDoc(wid, { afterOpen: function () {
                                            enterDiffMode(grPrev.entry.body, gr.entry.body, oldLabel, newLabel, oldTitle, newTitle);
                                        }});
                                    });
                                });
                            })(item.history_id, item.prev_history_id, item.work_id, item.work_title);
                        }
                        row.appendChild(diffBtn);
                    }

                    dlg.appendChild(row);

                    // Sub-detail row for link/share actions
                    if ((item.action === 'link_add' || item.action === 'link_remove' || item.action === 'share') && item.detail) {
                        var detailRow = document.createElement('div');
                        detailRow.style.cssText = detailStyle;
                        var detailText = item.detail;
                        if (item.action === 'share') {
                            var shareMap = { me: t('visMe'), group: t('visGroup'), all: t('visAll') };
                            detailText = shareMap[item.detail] || item.detail;
                        }
                        detailRow.textContent = '└ ' + detailText;
                        dlg.appendChild(detailRow);
                    }
                });
            }

            modal.open({
                title: t('actionHistoryTitle'),
                element: dlg,
                width: '560px',
                buttons: [{ label: t('close'), onClick: function () { modal.close(); } }],
            });
            dlg.scrollTop = 0;
        });
    }

    function clearSearch() {
        state.isSearchMode = false;
        state.searchQuery = '';
        var input = document.getElementById('wh-search-input');
        if (input) input.value = '';
        loadList();
    }

    function addTagToSearch(tag) {
        var input = document.getElementById('wh-search-input');
        if (!input) return;
        var current = input.value.trim();
        var tagToken = '#' + tag;
        if (current.indexOf(tagToken) === -1) {
            input.value = (current ? current + ' ' : '') + tagToken;
        }
        doSearch();
    }

    // -----------------------------------------------------------------------
    // Toast
    // -----------------------------------------------------------------------
    function showToast(msg, opts) {
        var toast = el('div', { className: 'wh-toast' });
        if (opts && opts.avatar) {
            var img = document.createElement('img');
            img.src = 'data:' + (opts.avatarMime || 'image/jpeg') + ';base64,' + opts.avatar;
            img.style.cssText = 'width:18px;height:18px;border-radius:50%;object-fit:cover;margin-right:6px;flex-shrink:0;vertical-align:middle;';
            toast.style.display = 'flex';
            toast.style.alignItems = 'center';
            toast.appendChild(img);
        } else if (opts && opts.avatarInitial) {
            var ph = document.createElement('div');
            ph.style.cssText = 'width:18px;height:18px;border-radius:50%;background:var(--border-color,#373c47);display:flex;align-items:center;justify-content:center;font-size:9px;color:var(--text-secondary,#8b8f9b);margin-right:6px;flex-shrink:0;';
            ph.textContent = opts.avatarInitial;
            toast.style.display = 'flex';
            toast.style.alignItems = 'center';
            toast.appendChild(ph);
        }
        var span = document.createElement('span');
        span.textContent = msg;
        toast.appendChild(span);
        document.body.appendChild(toast);
        setTimeout(function () { toast.remove(); }, 2500);
    }

    // -----------------------------------------------------------------------
    // Language change handler
    // -----------------------------------------------------------------------
    window.onLanguageChange = function (lang) {
        currentLanguage = lang || 'en';

        if (state.view === 'list') {
            var listView = document.getElementById('wh-list-view');
            if (!listView) return;

            // Rebuild list header (template buttons)
            var oldHeader = listView.querySelector('.wh-header');
            if (oldHeader) oldHeader.replaceWith(buildListHeader());

            // Rebuild search bar
            var oldSearchBar = document.getElementById('wh-search-bar');
            var savedQuery = state.searchQuery;
            if (oldSearchBar) {
                var newSearchBar = buildSearchBar();
                oldSearchBar.replaceWith(newSearchBar);
                var newInput = document.getElementById('wh-search-input');
                if (newInput && savedQuery) newInput.value = savedQuery;
            }

            // Re-render list (rebuilds column header + items)
            if (state.isSearchMode && state.searchQuery) {
                callPython('work_search', { query: state.searchQuery }).then(function (res) {
                    if (!res || !res.success) return;
                    renderList(res.items, true, state.searchQuery, true);
                });
            } else {
                renderList(state.listItems, false, '');
            }
        } else if (state.view === 'edit') {
            // Collect current user input, re-render with new language
            var currentTitle = collectTitle();
            var currentBody  = collectBody();
            var currentTags  = collectTags();
            var syntheticItem = {
                id: state.currentId,
                title: currentTitle,
                template: state.currentTemplate,
                body: currentBody,
                tags: currentTags,
                is_owner: state.isOwner,
                owner_display_name: '',
                visibility: state.currentVisibility,
                group_id: state.currentGroupId,
            };
            showEditView(syntheticItem, { noFocus: true });
        }
    };

    // -----------------------------------------------------------------------
    // Utilities
    // -----------------------------------------------------------------------
    function el(tag, attrs) {
        var node = document.createElement(tag);
        if (attrs) {
            Object.keys(attrs).forEach(function (k) {
                if (k === 'className') node.className = attrs[k];
                else if (k === 'style') node.style.cssText = attrs[k];
                else node[k] = attrs[k];
            });
        }
        return node;
    }

    // Tokenize a shell command string and return an array of {type, text} tokens.
    // Types: 'cmd', 'flag', 'value', 'var', 'string', 'other'
    function tokenizeCommand(raw) {
        var tokens = [];
        var i = 0;
        var wordIndex = 0; // 0 = first word (command name)

        function peek() { return i < raw.length ? raw[i] : null; }
        function consume() { return raw[i++]; }

        while (i < raw.length) {
            var ch = peek();

            // Whitespace
            if (ch === ' ' || ch === '\t') {
                var ws = '';
                while (i < raw.length && (raw[i] === ' ' || raw[i] === '\t')) ws += consume();
                tokens.push({ type: 'other', text: ws });
                continue;
            }

            // Quoted string (single or double)
            if (ch === '"' || ch === "'") {
                var q = consume();
                var s = q;
                while (i < raw.length && raw[i] !== q) {
                    if (raw[i] === '\\' && i + 1 < raw.length) s += consume();
                    s += consume();
                }
                if (i < raw.length) s += consume(); // closing quote
                tokens.push({ type: 'string', text: s });
                wordIndex++;
                continue;
            }

            // Environment variable $VAR or ${VAR}
            if (ch === '$') {
                var varStr = consume(); // '$'
                if (i < raw.length && raw[i] === '{') {
                    varStr += consume(); // '{'
                    while (i < raw.length && raw[i] !== '}') varStr += consume();
                    if (i < raw.length) varStr += consume(); // '}'
                } else {
                    while (i < raw.length && /[A-Za-z0-9_]/.test(raw[i])) varStr += consume();
                }
                tokens.push({ type: 'var', text: varStr });
                continue;
            }

            // Read a regular word (up to space/quote/$)
            var word = '';
            while (i < raw.length && raw[i] !== ' ' && raw[i] !== '\t' && raw[i] !== '"' && raw[i] !== "'" && raw[i] !== '$') {
                word += consume();
            }
            if (!word) { tokens.push({ type: 'other', text: consume() }); continue; }

            if (wordIndex === 0) {
                tokens.push({ type: 'cmd', text: word });
            } else if (word.charAt(0) === '-') {
                // --name=value split
                var eqIdx = word.indexOf('=');
                if (eqIdx !== -1) {
                    tokens.push({ type: 'flag',  text: word.slice(0, eqIdx + 1) });
                    tokens.push({ type: 'value', text: word.slice(eqIdx + 1) });
                } else {
                    tokens.push({ type: 'flag', text: word });
                }
            } else {
                tokens.push({ type: 'other', text: word });
            }
            wordIndex++;
        }
        return tokens;
    }

    var _typeColor = {
        cmd:    'var(--sh-cmd)',
        flag:   'var(--sh-flag)',
        value:  'var(--sh-value)',
        var:    'var(--sh-var)',
        string: 'var(--sh-string)',
        other:  'var(--sh-other)',
    };

    function updateHighlight(inputEl, highlightEl) {
        var raw = inputEl.value;
        if (!raw) { highlightEl.textContent = ''; return; }
        var tokens = tokenizeCommand(raw);
        var frag = document.createDocumentFragment();
        tokens.forEach(function (tok) {
            var span = document.createElement('span');
            span.style.color = _typeColor[tok.type] || _typeColor.other;
            span.textContent = tok.text;
            frag.appendChild(span);
        });
        highlightEl.textContent = '';
        highlightEl.appendChild(frag);
    }

    function fmtDate(iso) {
        if (!iso) return '';
        var d = new Date(iso.replace('Z', '+00:00'));
        var now = new Date();
        var diff = now - d;
        if (diff < 60000) return t('justNow');
        if (diff < 3600000) return t('minutesAgo').replace('{n}', Math.floor(diff / 60000));
        if (diff < 86400000) return t('hoursAgo').replace('{n}', Math.floor(diff / 3600000));
        var locale = currentLanguage === 'ko' ? 'ko-KR' : 'en-US';
        return d.toLocaleDateString(locale, { month: 'short', day: 'numeric' });
    }

})();
