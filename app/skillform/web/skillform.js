// ============================================================
// Skill Form - Common JavaScript
// ============================================================

const isInIframe = window.isInIframe;
const isInWebBrowser = window.isInWebBrowser;

let currentLanguage = 'en';

// ============================================================
// i18n
// ============================================================
const i18n = {
    en: {
        schemaPath: 'Schema File Path (.json)',
        schemaPathPlaceholder: 'Enter path to JSON schema file...',
        load: 'Load',
        submit: 'Submit',
        cancel: 'Cancel',
        noSchema: 'No form loaded. Enter a schema file path and click Load.',
        submitted: 'Form submitted.',
        cancelled: 'Cancelled.',
        loadError: 'Failed to load schema',
        saveError: 'Failed to save',
        saved: 'Saved',
        designerFile: 'Form File (.json)',
        designerFilePlaceholder: 'Enter path to save/load form...',
        open: 'Open',
        save: 'Save',
        newForm: 'New',
        schemaEditor: 'JSON Schema',
        preview: 'Preview',
        previewEmpty: 'Enter valid JSON Schema to preview the form.',
        invalidJson: 'Invalid JSON',
        formResult: 'Result',
    },
    ko: {
        schemaPath: '스키마 파일 경로 (.json)',
        schemaPathPlaceholder: 'JSON 스키마 파일 경로를 입력하세요...',
        load: '불러오기',
        submit: '제출',
        cancel: '취소',
        noSchema: '폼이 없습니다. 스키마 파일 경로를 입력하고 불러오기를 클릭하세요.',
        submitted: '폼이 제출되었습니다.',
        cancelled: '취소되었습니다.',
        loadError: '스키마 로드 실패',
        saveError: '저장 실패',
        saved: '저장됨',
        designerFile: '폼 파일 (.json)',
        designerFilePlaceholder: '저장/불러올 폼 파일 경로를 입력하세요...',
        open: '열기',
        save: '저장',
        newForm: '새 폼',
        schemaEditor: 'JSON 스키마',
        preview: '미리보기',
        previewEmpty: '올바른 JSON 스키마를 입력하면 폼이 미리보기됩니다.',
        invalidJson: '잘못된 JSON',
        formResult: '결과',
    }
};

function t(key) {
    const lang = i18n[currentLanguage] || i18n.en;
    return lang[key] || i18n.en[key] || key;
}

// ============================================================
// json-editor instance management
// ============================================================

let _editorInstance = null;

/**
 * Destroy existing json-editor instance if any.
 */
function destroyEditor() {
    if (_editorInstance) {
        try { _editorInstance.destroy(); } catch (e) { /* ignore */ }
        _editorInstance = null;
    }
}

/**
 * Create a json-editor instance inside `container` using the given schema.
 * @param {HTMLElement} container
 * @param {Object} schema  JSON Schema object
 * @param {Object} [startval]  Initial values
 * @returns {JSONEditor}
 */
function createEditor(container, schema, startval) {
    destroyEditor();
    container.innerHTML = '';

    const options = {
        schema: schema,
        theme: 'bootstrap4',
        iconlib: 'fontawesome5',
        disable_edit_json: true,
        disable_properties: true,
        disable_collapse: false,
        no_additional_properties: true,
        required_by_default: false,
    };
    if (startval !== undefined) options.startval = startval;

    _editorInstance = new JSONEditor(container, options);
    return _editorInstance;
}

/**
 * Get current editor values.
 */
function getEditorValues() {
    if (!_editorInstance) return null;
    return _editorInstance.getValue();
}

// ============================================================
// Language support
// ============================================================

function onLanguageChange(lang) {
    currentLanguage = lang || 'en';
    if (typeof applyI18n === 'function') applyI18n();
}

// ============================================================
// Status helper
// ============================================================

function setStatus(el, msg, type) {
    if (!el) return;
    el.textContent = msg;
    el.className = 'sf-status' + (type ? ' sf-status-' + type : '');
}
