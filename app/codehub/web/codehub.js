// ============================================================================
// CodeHub - Common JavaScript
// ============================================================================

let currentLanguage = 'en';

// ============================================================================
// i18n
// ============================================================================
const i18n = {
    en: {
        projects: 'Projects',
        myProjects: 'My Projects (master)',
        memberProjects: 'Projects I belong to (member)',
        allProjects: 'All Projects',
        newProject: 'New Project',
        search: 'Search',
        noProjects: 'No projects found.',
        about: 'About',
        master: 'Master',
        members: 'Members',
        stars: 'Stars',
        favorite: 'Favorite',
        favorited: 'Favorited',
        openTerminal: 'Open in Terminal',
        refresh: 'Refresh',
        openInSkillbot: 'Open in Skill Bot',
        openInSkillbotTitle: 'Open in Skill Bot',
        openInSkillbotRunningMsg: 'Skill Bot is currently running. Close it and open this project?',
        currentRevision: 'Current Revision',
        created: 'Created',
        download: 'Download',
        deploy: 'Deploy',
        projectName: 'Project Name',
        description: 'Description',
        selectMembers: 'Select Members',
        create: 'Create',
        cancel: 'Cancel',
        nameRequired: 'Project name is required.',
        nameInvalid: 'Name must contain only letters, numbers, hyphens, and underscores.',
        nameTaken: 'A project with this name already exists.',
        configRequired: 'SVN repo URL is not configured.',
        configSvnUrl: 'SVN Repo URL',
        configSave: 'Save',
        configTitle: 'Configure SVN Repository',
        configDesc: 'Enter the SVN repository URL to use for CodeHub.',
        fileExplorer: 'Files',
        revision: 'Revision',
        revisions: 'Revisions',
        colAuthor: 'Author',
        colDate: 'Date',
        colMessage: 'Message',
        noFiles: 'This directory is empty.',
        back: 'Back',
        loading: 'Loading...',
        error: 'Error',
        deleteProject: 'Delete Project',
        confirmDelete: 'Delete this project? This cannot be undone.',
        manageMembersTitle: 'Manage Members',
        memberSearchPlaceholder: 'Search accounts...',
        memberAdd: 'Add',
        memberRemove: 'Remove',
        membersMore: 'and {n} more',
        memberNoResults: 'No accounts found.',
        memberAlreadyAdded: 'Already a member',
        save: 'Save',
        notLoggedIn: 'Not logged in',
        uploadFile: 'Upload File',
        commitMessage: 'Commit message',
        upload: 'Upload',
        noRevisions: 'No revisions yet.',
        statusUnmodified: '',
        statusModified: 'modified',
        statusAdded: 'added',
        statusDeleted: 'deleted',
        statusUntracked: 'untracked',
        statusMissing: 'missing',
        statusUnregistered: 'unregistered',
        addFile: 'Add',
        addFileConfirmTitle: 'Add file',
        addFileConfirmMsg: 'Add this file to version control?',
        deployTitle: 'Deploy',
        deployMessage: 'Commit message',
        deploySuccess: '{rev} has been deployed.',
        nothingToDeploy: 'Nothing to commit.',
        changedFiles: 'Changed files',
        showAll: 'Show all',
        collapse: 'Collapse',
        viewDeployed: 'Deployed',
        viewLocal: 'Local',
        viewDiff: 'Diff',
        binaryFile: '[binary file]',
        noHeadVersion: 'Not in repository (untracked)',
        noLocalVersion: 'Deleted locally',
        revertFile: 'Revert',
        revertFileConfirmTitle: 'Revert file',
        revertFileConfirmMsg: 'Discard changes and revert this file to the last committed version?',
        revisionDetail: 'Revision Detail',
        changedPaths: 'Changed paths',
        goToRevision: 'Go to this revision',
        rollback: 'Rollback',
        rollbackConfirmTitle: 'Rollback',
        rollbackConfirmMsg: 'Roll back to this revision? A new deployment will be created.',
        rollbackLatestTip: 'Already the latest revision',
        rollbackNoPermissionTip: 'Only the master can rollback',
        actionAdded: 'added',
        actionModified: 'modified',
        actionDeleted: 'deleted',
        actionReplaced: 'replaced',
        revisionBadgeHead: 'HEAD',
        viewChanges: 'Changes',
        revertAll: 'Revert All',
        backToList: 'Back',
        noChanges: 'No changes.',
        confirmRevertAll: 'Revert All',
        confirmRevertAllMsg: 'Discard all local changes and revert to the last committed version?',
        updateAvailable: 'Update available',
        updateTitle: 'Update Working Copy',
        updateDesc: 'Working copy is at r{wc} (outdated). Update to r{head} before continuing.',
        updateBtn: 'Update',
        conflictsFound: 'Conflicts detected. Choose how to resolve each file, then click Apply.',
        conflictKeepMine: 'Keep mine',
        conflictUseTheirs: 'Use theirs',
        conflictKeep: 'Keep current',
        conflictMine: 'My version',
        conflictTheirs: 'Their version',
        conflictDiff: 'Diff',
        conflictApply: 'Apply',
        allConflictsResolved: 'All conflicts resolved.',
        behindHeadError: 'Working copy is behind HEAD (r{wc} < r{head}). Update before deploying.',
        updateAndDeploy: 'Update first',
        conflictDiffTitle: 'Diff: {file}',
        conflictDiffMine: 'My version',
        conflictDiffTheirs: 'Their version',
        conflictLater: 'Later',
        conflictPending: 'Unresolved conflicts',
        transferMasterTitle: 'Transfer Master',
        transferMasterMsg: 'Transfer master to {name}?',
        transferMasterHasChanges: 'There are uncommitted changes. They will be discarded. Proceed?',
        orphanTitle: 'Unused Local Directories Found',
        orphanDesc: 'The following local directories are no longer linked to any project. Delete them?',
        orphanDelete: 'Delete All',
        orphanCancel: 'Dismiss for 1 week',
        orphanDoneMsg: 'Deleted {n} directory/directories.',
        orphanFailMsg: 'Failed to delete: {list}',
    },
    ko: {
        projects: '프로젝트',
        myProjects: '내가 master인 프로젝트',
        memberProjects: '내가 member인 프로젝트',
        allProjects: '전체 프로젝트',
        newProject: '새 프로젝트',
        search: '검색',
        noProjects: '프로젝트가 없습니다.',
        about: 'About',
        master: 'master',
        members: '멤버',
        stars: '스타',
        favorite: '즐겨찾기',
        favorited: '즐겨찾기 완료',
        openTerminal: '터미널로 열기',
        refresh: '새로고침',
        openInSkillbot: '스킬봇으로 열기',
        openInSkillbotTitle: '스킬봇으로 열기',
        openInSkillbotRunningMsg: '스킬봇이 실행 중입니다. 종료하고 이 프로젝트를 여시겠습니까?',
        currentRevision: '현재 Revision',
        created: '생성일',
        download: '다운로드',
        deploy: '배포',
        projectName: '프로젝트 이름',
        description: '설명',
        selectMembers: '멤버 선택',
        create: '생성',
        cancel: '취소',
        nameRequired: '프로젝트 이름을 입력하세요.',
        nameInvalid: '이름은 영문, 숫자, 하이픈, 언더스코어만 허용됩니다.',
        nameTaken: '이미 존재하는 프로젝트 이름입니다.',
        configRequired: 'SVN repo URL이 설정되지 않았습니다.',
        configSvnUrl: 'SVN Repo URL',
        configSave: '저장',
        configTitle: 'SVN 저장소 설정',
        configDesc: 'CodeHub에서 사용할 SVN 저장소 URL을 입력하세요.',
        fileExplorer: '파일',
        revision: 'revision',
        revisions: '배포 내역',
        colAuthor: '작성자',
        colDate: '날짜',
        colMessage: '메시지',
        noFiles: '이 디렉토리는 비어 있습니다.',
        back: '뒤로',
        loading: '불러오는 중...',
        error: '오류',
        deleteProject: '프로젝트 삭제',
        confirmDelete: '이 프로젝트를 삭제하시겠습니까? 이 작업은 취소할 수 없습니다.',
        manageMembersTitle: '멤버 관리',
        memberSearchPlaceholder: '계정 검색...',
        memberAdd: '추가',
        memberRemove: '제거',
        membersMore: '외 {n}명',
        memberNoResults: '계정이 없습니다.',
        memberAlreadyAdded: '이미 멤버입니다',
        save: '저장',
        notLoggedIn: '로그인되지 않음',
        uploadFile: '파일 업로드',
        commitMessage: '배포 메시지',
        upload: '배포',
        noRevisions: '배포 내역이 없습니다.',
        statusUnmodified: '',
        statusModified: '수정됨',
        statusAdded: '추가됨',
        statusDeleted: '삭제됨',
        statusUntracked: '추가됨',
        statusMissing: '삭제됨',
        statusUnregistered: '미등록',
        addFile: '추가하기',
        addFileConfirmTitle: '파일 추가',
        addFileConfirmMsg: '이 파일을 버전 관리에 추가하시겠습니까?',
        deployTitle: '배포',
        deployMessage: '커밋 메시지',
        deploySuccess: '{rev}이(가) 배포되었습니다.',
        nothingToDeploy: '변경사항이 없습니다.',
        changedFiles: '변경된 파일',
        showAll: '모두 보기',
        collapse: '접기',
        viewDeployed: '배포 버전',
        viewLocal: '현재 버전',
        viewDiff: 'Diff',
        binaryFile: '[바이너리 파일]',
        noHeadVersion: '저장소에 없음 (untracked)',
        noLocalVersion: '로컬에서 삭제됨',
        revertFile: '되돌리기',
        revertFileConfirmTitle: '파일 되돌리기',
        revertFileConfirmMsg: '변경된 내용을 초기화하고 해당 파일을 최신 배포 버전으로 되돌리겠습니까?',
        revisionDetail: 'Revision 세부 내역',
        changedPaths: '변경된 파일 목록',
        goToRevision: '이동',
        rollback: '롤백',
        rollbackConfirmTitle: '롤백',
        rollbackConfirmMsg: '이 Revision으로 롤백하시겠습니까? 새로운 배포가 발생합니다.',
        rollbackLatestTip: '이미 최신 Revision입니다',
        rollbackNoPermissionTip: 'master만 롤백할 수 있습니다',
        actionAdded: '추가됨',
        actionModified: '수정됨',
        actionDeleted: '삭제됨',
        actionReplaced: '교체됨',
        revisionBadgeHead: 'HEAD',
        viewChanges: '수정 내용',
        revertAll: '전체 되돌리기',
        backToList: '목록으로',
        noChanges: '변경사항이 없습니다.',
        confirmRevertAll: '전체 되돌리기',
        confirmRevertAllMsg: '모든 변경사항을 되돌리겠습니까? 마지막 배포 버전으로 초기화됩니다.',
        updateAvailable: '업데이트 필요',
        updateTitle: '작업 디렉토리 업데이트',
        updateDesc: '현재 작업 디렉토리는 과거 r{wc}입니다. 최신 r{head}로 업데이트 후 작업을 진행하세요.',
        updateBtn: '업데이트',
        conflictsFound: '충돌이 발생했습니다. 각 파일의 처리 방법을 선택한 후 실행하세요.',
        conflictKeepMine: '내 버전 유지',
        conflictUseTheirs: '저장소 버전 사용',
        conflictKeep: '현 상황 유지',
        conflictMine: '내 수정으로 결정',
        conflictTheirs: '내 수정 포기',
        conflictDiff: '비교',
        conflictApply: '실행',
        allConflictsResolved: '모든 충돌이 해결되었습니다.',
        behindHeadError: '작업 디렉토리가 HEAD보다 낮습니다 (r{wc} < r{head}). 배포 전에 업데이트하세요.',
        updateAndDeploy: '먼저 업데이트',
        conflictDiffTitle: 'Diff: {file}',
        conflictDiffMine: '내 수정',
        conflictDiffTheirs: '저장소 버전',
        conflictLater: '나중에',
        conflictPending: '충돌 미해결',
        transferMasterTitle: 'Master 변경',
        transferMasterMsg: '{name}을(를) Master로 변경하시겠습니까?',
        transferMasterHasChanges: '커밋되지 않은 변경 내용이 있습니다. 변경 내용은 삭제됩니다. 계속하시겠습니까?',
        orphanTitle: '불필요한 로컬 디렉토리 발견',
        orphanDesc: '아래 로컬 디렉토리는 현재 어떤 프로젝트에도 연결되어 있지 않습니다. 삭제하시겠습니까?',
        orphanDelete: '전체 삭제',
        orphanCancel: '1주일간 보지 않기',
        orphanDoneMsg: '{n}개 디렉토리를 삭제했습니다.',
        orphanFailMsg: '삭제 실패: {list}',
    }
};

function t(key) {
    return (i18n[currentLanguage] || i18n.en)[key] || key;
}

// ============================================================================
// API call - delegates to window.callPython (provided by common.js)
// ============================================================================
function apiCall(action, data) {
    data = data || {};
    // Wait for common.js to finish loading if needed
    if (typeof window.callPython === 'function') {
        return window.callPython(action, data);
    }
    return new Promise((resolve) => {
        window.addEventListener('callPythonReady', function handler() {
            window.removeEventListener('callPythonReady', handler);
            resolve(window.callPython(action, data));
        });
    });
}

// ============================================================================
// Navigation
// ============================================================================
function navigateTo(url) {
    if (window.isInIframe) {
        window.parent.postMessage({ action: 'navigateIframe', url: url }, '*');
    } else {
        window.location.href = url;
    }
}

// ============================================================================
// Diff utilities (shared by project.html and file_view.html)
// ============================================================================
function escHtml(s) {
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// Convert Diff.diffLines() output to side-by-side aligned row descriptors.
function chBuildDiffRows(changes) {
    const segments = [];
    changes.forEach(function(c) {
        const lines = c.value.replace(/\n$/, '').split('\n');
        if (c.removed) segments.push({ type: 'removed', lines: lines });
        else if (c.added) segments.push({ type: 'added',   lines: lines });
        else              segments.push({ type: 'equal',   lines: lines });
    });
    const rows = [];
    let i = 0;
    while (i < segments.length) {
        const seg = segments[i];
        if (seg.type === 'removed' && i + 1 < segments.length && segments[i + 1].type === 'added') {
            const rem = seg.lines, add = segments[i + 1].lines;
            const len = Math.max(rem.length, add.length);
            for (let j = 0; j < len; j++) {
                const hasOld = j < rem.length, hasNew = j < add.length;
                if (hasOld && hasNew)      rows.push({ type: 'changed', oldLine: rem[j], newLine: add[j] });
                else if (hasOld)           rows.push({ type: 'removed', line: rem[j] });
                else                       rows.push({ type: 'added',   line: add[j] });
            }
            i += 2;
        } else if (seg.type === 'removed') {
            seg.lines.forEach(function(l) { rows.push({ type: 'removed', line: l }); });
            i++;
        } else if (seg.type === 'added') {
            seg.lines.forEach(function(l) { rows.push({ type: 'added', line: l }); });
            i++;
        } else {
            seg.lines.forEach(function(l) { rows.push({ type: 'equal', line: l }); });
            i++;
        }
    }
    return rows;
}

function _chDiffNumSpan(n) {
    return '<span class="ch-diff-linenum">' + n + '</span>';
}

function _chDiffInlineHl(charDiffs, isOld) {
    let html = '';
    charDiffs.forEach(function(part) {
        if (!part.removed && !part.added) {
            html += escHtml(part.value);
        } else if (isOld && part.removed) {
            html += '<span class="ch-diff-hl">' + escHtml(part.value) + '</span>';
        } else if (!isOld && part.added) {
            html += '<span class="ch-diff-hl">' + escHtml(part.value) + '</span>';
        }
    });
    return html;
}

// Render a side-by-side diff table into container.
// withResizer: add a drag handle for adjusting column widths.
function chDiffRender(oldText, newText, container, options) {
    options = options || {};
    var withResizer = options.withResizer !== false;

    if (typeof Diff === 'undefined') {
        container.textContent = '(diff library not loaded)';
        return;
    }

    var splitRatio = options.splitRatio || 50;
    var changes = Diff.diffLines(oldText, newText);
    var rows = chBuildDiffRows(changes);

    var wrap = document.createElement('div');
    wrap.className = 'ch-diff-wrap';
    wrap.style.position = 'relative';

    var table = document.createElement('table');
    table.className = 'ch-diff-table';
    var colL = document.createElement('col');
    var colR = document.createElement('col');
    colL.style.width = splitRatio + '%';
    colR.style.width = (100 - splitRatio) + '%';
    var colgroup = document.createElement('colgroup');
    colgroup.appendChild(colL);
    colgroup.appendChild(colR);
    table.appendChild(colgroup);

    var tbody = document.createElement('tbody');
    var oldNum = 1, newNum = 1;

    rows.forEach(function(row) {
        var tr = document.createElement('tr');
        tr.className = row.type;
        var tdOld = document.createElement('td');
        var tdNew = document.createElement('td');

        if (row.type === 'equal') {
            tdOld.innerHTML = _chDiffNumSpan(oldNum++) + escHtml(row.line);
            tdNew.innerHTML = _chDiffNumSpan(newNum++) + escHtml(row.line);
        } else if (row.type === 'removed') {
            tdOld.innerHTML = _chDiffNumSpan(oldNum++) + escHtml(row.line);
        } else if (row.type === 'added') {
            tdNew.innerHTML = _chDiffNumSpan(newNum++) + escHtml(row.line);
        } else if (row.type === 'changed') {
            var charDiffs = Diff.diffChars(row.oldLine, row.newLine);
            tdOld.innerHTML = _chDiffNumSpan(oldNum++) + _chDiffInlineHl(charDiffs, true);
            tdNew.innerHTML = _chDiffNumSpan(newNum++) + _chDiffInlineHl(charDiffs, false);
        }
        tr.appendChild(tdOld);
        tr.appendChild(tdNew);
        tbody.appendChild(tr);
    });

    table.appendChild(tbody);
    wrap.appendChild(table);

    if (withResizer) {
        var onRatioChange = options.onRatioChange || null;
        var handle = document.createElement('div');
        handle.className = 'ch-diff-resizer';
        handle.style.left = splitRatio + '%';
        handle.addEventListener('pointerdown', function(e) {
            e.preventDefault();
            handle.setPointerCapture(e.pointerId);
            document.body.style.userSelect = 'none';
            document.body.style.cursor = 'col-resize';
            function onMove(ev) {
                var rect = wrap.getBoundingClientRect();
                var ratio = Math.min(90, Math.max(10, (ev.clientX - rect.left) / rect.width * 100));
                splitRatio = ratio;
                colL.style.width = ratio + '%';
                colR.style.width = (100 - ratio) + '%';
                handle.style.left = ratio + '%';
                if (onRatioChange) onRatioChange(ratio);
            }
            function onUp() {
                handle.removeEventListener('pointermove', onMove);
                handle.removeEventListener('pointerup', onUp);
                document.body.style.userSelect = '';
                document.body.style.cursor = '';
            }
            handle.addEventListener('pointermove', onMove);
            handle.addEventListener('pointerup', onUp);
        });
        wrap.appendChild(handle);
    }

    container.appendChild(wrap);
}

// ============================================================================
// Language change callback (called by common.js setLanguage handler)
// ============================================================================
function onLanguageChange(lang) {
    const newLang = lang || 'en';
    const changed = newLang !== currentLanguage;
    currentLanguage = newLang;
    if (typeof onLanguageSet === 'function') onLanguageSet(changed);
}

// ============================================================================
// Init
// ============================================================================
document.addEventListener('DOMContentLoaded', () => {
    if (typeof onPageLoad === 'function') onPageLoad();
});
