// SkMdControl: shared markdown read/edit textarea control
// Usage: var ctrl = SkMdControl.build(opts);
//        container.appendChild(ctrl.element);
// Requires: marked 16.x, highlight.js 11.x (both optional)
(function(global) {
    'use strict';

    var EDIT_SVG = '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M11.5 2.5a1.414 1.414 0 0 1 2 2L5 13l-3 1 1-3 8.5-8.5z"/></svg>';

    function _escHtml(str) {
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    // Convert @[id|name] and [[id|title]] tokens to HTML spans/anchors.
    // mentionMap:   {id -> {display_name, avatar_small, avatar_mime}} (may be null/undefined)
    // docLinkClick: function(id) called on doc-link click (may be null)
    // docLinkMap:   {id -> {title, template}} for icon rendering (may be null)
    // Parts outside fenced code blocks only.
    var _DOC_LINK_TEMPLATE_SVG = {
        note:      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="16" rx="2"/><line x1="8" y1="9" x2="16" y2="9"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="13" y2="17"/></svg>',
        command:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="6,9 11,12 6,15"/><line x1="13" y1="15" x2="18" y2="15"/></svg>',
        todo:      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="7" height="7" rx="1" stroke-width="1.2"/><polyline points="5.5,7.5 7,9 9.5,6"/><line x1="14" y1="7" x2="20" y2="7"/><rect x="4" y="13" width="7" height="7" rx="1" stroke-width="1.2"/><line x1="14" y1="16" x2="20" y2="16"/></svg>',
        checklist: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="4,12 8,16 14,8"/><line x1="17" y1="12" x2="21" y2="12"/></svg>',
    };
    function _applyInlineTokens(src, mentionMap, docLinkClick, docLinkMap) {
        // Split on fenced code blocks to avoid converting inside them
        var parts = src.split(/(^```[^\n]*\n[\s\S]*?^```|^~~~[^\n]*\n[\s\S]*?^~~~)/m);
        var result = '';
        for (var pi = 0; pi < parts.length; pi++) {
            if (pi % 2 !== 0) {
                result += parts[pi];
                continue;
            }
            var chunk = parts[pi];
            // Replace @[id|name]
            chunk = chunk.replace(/@\[([^|]*)\|([^\]]*)\]/g, function(_, id, displayName) {
                var safeId = _escHtml(id);
                var safeName = _escHtml(displayName);
                var info = mentionMap && mentionMap[id];
                if (!info) {
                    return '<span class="sk-mention sk-mention-unknown">@' + safeName + '</span>';
                }
                var avatarHtml = '';
                if (info.avatar_small) {
                    var mime = _escHtml(info.avatar_mime || 'image/jpeg');
                    avatarHtml = '<img class="sk-mention-avatar" src="data:' + mime + ';base64,' + info.avatar_small + '">';
                }
                return '<span class="sk-mention">' + avatarHtml + '@' + safeName + '</span>';
            });
            // Replace [[id|title]]
            chunk = chunk.replace(/\[\[(\d+)\|([^\]]*)\]\]/g, function(_, id, title) {
                var dataId = _escHtml(id);
                var info = docLinkMap && docLinkMap[id];
                // Use live title from map; fall back to token title when document is deleted/unknown
                var displayTitle = _escHtml(info && info.title ? info.title : title);
                var template = info && info.template || 'note';
                var svgStr = _DOC_LINK_TEMPLATE_SVG[template] || _DOC_LINK_TEMPLATE_SVG.note;
                var iconHtml = '<span class="sk-doc-link-icon">' + svgStr + '</span>';
                var cls = info ? 'sk-doc-link' : 'sk-doc-link sk-doc-link-dead';
                return '<a class="' + cls + '" data-id="' + dataId + '">' + iconHtml + displayTitle + '</a>';
            });
            result += chunk;
        }
        return result;
    }

    function renderMd(text, renderOpts) {
        var mentionMap = renderOpts && renderOpts.mentionMap || null;
        var docLinkClick = renderOpts && renderOpts.docLinkClick || null;
        var docLinkMap = renderOpts && renderOpts.docLinkMap || null;

        if (window.marked) {
            // Preserve blank lines outside fenced code blocks: 3+ consecutive newlines →
            // paragraph break + blank-line divs. Two newlines (1 blank line) are handled
            // by paragraph margin in CSS. Fenced code blocks are left untouched.
            var src = String(text || '');
            // Apply inline tokens before markdown parsing (outside fences only)
            if (mentionMap !== null || docLinkClick !== null || docLinkMap !== null) {
                src = _applyInlineTokens(src, mentionMap, docLinkClick, docLinkMap);
            }
            // Preserve leading blank lines: marked strips them, so convert each leading
            // newline to a blank-line div before parsing.
            var leadingBlanks = '';
            src = src.replace(/^\n+/, function(m) {
                for (var i = 0; i < m.length; i++) leadingBlanks += '<div class="sk-blank"></div>\n';
                return '';
            });
            var result = '';
            // Split on fenced code blocks (``` or ~~~), alternating outside/inside.
            var parts = src.split(/(^```[^\n]*\n[\s\S]*?^```|^~~~[^\n]*\n[\s\S]*?^~~~)/m);
            for (var pi = 0; pi < parts.length; pi++) {
                if (pi % 2 === 0) {
                    // Outside a code block: replace 3+ newlines with blank-line divs.
                    result += parts[pi].replace(/\n{3,}/g, function(m) {
                        var extras = m.length - 2;
                        var divs = '';
                        for (var i = 0; i < extras; i++) divs += '\n\n<div class="sk-blank"></div>';
                        return '\n\n' + divs + '\n\n';
                    });
                } else {
                    result += parts[pi];
                }
            }
            var html = leadingBlanks + window.marked.parse(result, { gfm: true, breaks: true });
            if (window.hljs) {
                var tmp = document.createElement('div');
                tmp.innerHTML = html;
                tmp.querySelectorAll('pre code').forEach(function(el) {
                    hljs.highlightElement(el);
                });
                return tmp.innerHTML;
            }
            return html;
        }
        var d = document.createElement('div');
        d.textContent = text || '';
        return d.innerHTML;
    }

    // build(opts) -> { element, getValue(), setValue(v), refresh(), focus() }
    //
    // opts:
    //   id                - element id. writable: set on textarea. readonly: set on preview div.
    //   placeholder       - textarea placeholder text
    //   initialValue      - initial text (expanded form, i.e. real data URLs if any)
    //   minHeight         - CSS min-height string e.g. '200px' (optional)
    //   readonly          - if true, renders preview-only with no edit controls
    //   lang              - 'ko' | 'en' for tooltip text (default 'ko')
    //   imagePaste        - if true, enables clipboard image paste:
    //                         pastes are converted to image:N tokens stored in textarea;
    //                         getValue() always returns expanded text (real data URLs);
    //                         setValue(v) tokenizes incoming data URLs before storing.
    //   onChange          - function() called on textarea input event
    //   onBlur            - function() called after blur triggers switchToView
    //   measureEditHeight - function(preview) → number(px) | 0; overrides height measurement
    //                       on switchToEdit. Return 0 to use default (preview.offsetHeight).
    //   mentionSearch     - function(query, callback) for @ autocomplete
    //                         callback(items): [{id, display_name, avatar_small, avatar_mime}]
    //   docSearch         - function(query, callback) for [[ autocomplete
    //                         callback(items): [{id, title, template}]
    //   docLinkClick      - function(id) called when a rendered doc link is clicked
    //   mentionMap        - {id -> {display_name, avatar_small, avatar_mime}} for rendering
    function build(opts) {
        opts = opts || {};
        var id                = opts.id                || null;
        var placeholder       = opts.placeholder       || '';
        var initVal           = opts.initialValue      || '';
        var minHeight         = opts.minHeight         || null;
        var readonly          = opts.readonly          || false;
        var lang              = opts.lang              || 'ko';
        var imagePaste        = opts.imagePaste        || false;
        var onChange          = opts.onChange          || null;
        var onBlur            = opts.onBlur            || null;
        var measureEditHeight = opts.measureEditHeight || null;
        var mentionSearch     = opts.mentionSearch     || null;
        var docSearch         = opts.docSearch         || null;
        var docLinkClick      = opts.docLinkClick      || null;
        var autoResize        = opts.autoResize        || false;
        var mentionMap        = opts.mentionMap        || null;
        var docLinkMap        = opts.docLinkMap        || null;

        var renderOpts = (mentionMap || docLinkClick || docLinkMap) ? { mentionMap: mentionMap, docLinkClick: docLinkClick, docLinkMap: docLinkMap } : null;

        // Image token state (only used when imagePaste: true)
        var imgMap = {};
        var imgSeq = 0;

        function _imgExpand(text) {
            return text.replace(/!\[([^\]]*)\]\(image:(\d+)\)/g, function(_, alt, imgId) {
                var data = imgMap[imgId];
                return data ? '![' + alt + '](' + data + ')' : '![' + alt + '](image:' + imgId + ')';
            });
        }

        function _imgTokenize(text) {
            return text.replace(/!\[([^\]]*)\]\((data:image\/[^)]+)\)/g, function(_, alt, data) {
                var imgId = ++imgSeq;
                imgMap[imgId] = data;
                return '![' + alt + '](image:' + imgId + ')';
            });
        }

        var wrap = document.createElement('div');
        wrap.className = 'sk-md-wrap';

        var preview = document.createElement('div');
        preview.className = 'sk-md-preview';
        if (minHeight) preview.style.minHeight = minHeight;

        var ta      = null;
        var editBtn = null;

        if (!readonly) {
            ta = document.createElement('textarea');
            ta.className = 'sk-md-textarea';
            if (id) ta.id = id;
            ta.placeholder = placeholder;
            ta.value = imagePaste ? _imgTokenize(initVal) : initVal;
            if (minHeight) ta.style.minHeight = minHeight;

            editBtn = document.createElement('button');
            editBtn.type = 'button';
            editBtn.className = 'sk-md-edit-btn';
            editBtn.setAttribute('aria-label', lang === 'ko' ? '편집' : 'Edit');
            editBtn.setAttribute('data-tooltip', lang === 'ko' ? '편집' : 'Edit');
            editBtn.innerHTML = EDIT_SVG;
        } else {
            // Readonly: preview element carries the primary id for external lookups.
            if (id) preview.id = id;
        }

        function _renderPreview(val) {
            var text = imagePaste ? _imgExpand(val) : val;
            return renderMd(text, renderOpts);
        }

        function switchToView() {
            var val = ta ? ta.value : initVal;
            if (ta && !autoResize) ta.style.height = '';
            if (!val.trim()) {
                preview.style.display = 'none';
                if (ta)      ta.style.display     = '';
                if (editBtn) editBtn.style.display = 'none';
                return;
            }
            preview.innerHTML = _renderPreview(val);
            // Wire up doc-link click handlers after innerHTML assignment
            if (docLinkClick) {
                var links = preview.querySelectorAll('.sk-doc-link[data-id]');
                for (var li = 0; li < links.length; li++) {
                    (function(link) {
                        link.addEventListener('click', function(e) {
                            e.preventDefault();
                            var docId = parseInt(link.getAttribute('data-id'), 10);
                            if (!isNaN(docId)) docLinkClick(docId);
                        });
                    })(links[li]);
                }
            }
            preview.style.display = '';
            if (ta)      ta.style.display     = 'none';
            if (editBtn) editBtn.style.display = '';
        }

        function _isLastInParent() {
            if (!wrap.parentNode) return false;
            var siblings = wrap.parentNode.children;
            for (var i = siblings.length - 1; i >= 0; i--) {
                if (siblings[i] === wrap) return true;
                if (siblings[i].style.display !== 'none') return false;
            }
            return false;
        }

        function switchToEdit() {
            preview.style.display = 'none';
            if (ta)      ta.style.display     = '';
            if (editBtn) editBtn.style.display = 'none';
            if (ta) {
                if (autoResize && _isLastInParent()) {
                    ta.style.height = 'auto';
                    requestAnimationFrame(function() {
                        ta.style.height = ta.scrollHeight + 'px';
                    });
                }
                ta.focus({ preventScroll: true });
            }
        }

        // -----------------------------------------------------------------------
        // Autocomplete popup (@ mention and [[ doc link)
        // -----------------------------------------------------------------------
        var acPopup = null;
        var acItems = [];
        var acIdx = -1;
        var acMode = null; // 'mention' | 'doc'
        var acDocDebounce = null;

        function _removePopup() {
            if (acPopup) {
                acPopup.parentNode && acPopup.parentNode.removeChild(acPopup);
                acPopup = null;
            }
            acItems = [];
            acIdx = -1;
            acMode = null;
            clearTimeout(acDocDebounce);
        }

        function _caretCoords(textarea) {
            // Mirror-div technique: measure caret pixel position in textarea
            var mirror = document.createElement('div');
            var style = window.getComputedStyle(textarea);
            var props = [
                'fontFamily', 'fontSize', 'fontWeight', 'fontStyle',
                'letterSpacing', 'lineHeight', 'textTransform',
                'wordWrap', 'whiteSpace', 'overflowWrap', 'wordBreak',
                'paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft',
                'borderTopWidth', 'borderRightWidth', 'borderBottomWidth', 'borderLeftWidth',
                'boxSizing'
            ];
            for (var i = 0; i < props.length; i++) {
                mirror.style[props[i]] = style[props[i]];
            }
            mirror.style.position = 'absolute';
            mirror.style.visibility = 'hidden';
            mirror.style.top = '0';
            mirror.style.left = '0';
            mirror.style.width = textarea.offsetWidth + 'px';
            mirror.style.height = 'auto';
            mirror.style.overflow = 'hidden';
            mirror.style.whiteSpace = 'pre-wrap';

            var textBefore = textarea.value.slice(0, textarea.selectionEnd);
            var textNode = document.createTextNode(textBefore);
            mirror.appendChild(textNode);
            var span = document.createElement('span');
            span.textContent = '|';
            mirror.appendChild(span);

            document.body.appendChild(mirror);
            var taRect = textarea.getBoundingClientRect();
            var spanRect = span.getBoundingClientRect();
            document.body.removeChild(mirror);

            // span.getBoundingClientRect is relative to viewport, mirror is at body (0,0).
            // We need position relative to textarea.
            var mirrorLeft = parseFloat(style.borderLeftWidth) || 0;
            var mirrorTop  = parseFloat(style.borderTopWidth)  || 0;
            var relX = span.offsetLeft - textarea.scrollLeft + mirrorLeft;
            var relY = span.offsetTop  - textarea.scrollTop  + mirrorTop;

            return {
                x: taRect.left + relX,
                y: taRect.top  + relY,
                lineHeight: parseFloat(style.lineHeight) || 16
            };
        }

        function _showPopup(textarea, items, mode, onSelect) {
            _removePopup();
            if (!items || items.length === 0) return;
            acMode = mode;
            acItems = items;
            acIdx = -1;

            var coords = _caretCoords(textarea);
            var popup = document.createElement('div');
            popup.className = 'sk-autocomplete-popup';

            // Position: prefer above caret, fallback below
            var popupMaxH = Math.min(items.length, 8) * 34 + 8;
            var above = coords.y - popupMaxH - 4;
            var below = coords.y + coords.lineHeight + 4;
            var useAbove = above >= 0;

            popup.style.position = 'fixed';
            popup.style.left = Math.max(0, coords.x) + 'px';
            if (useAbove) {
                popup.style.top = above + 'px';
            } else {
                popup.style.top = below + 'px';
            }
            popup.style.zIndex = '99999';

            var shown = items.slice(0, 8);
            for (var i = 0; i < shown.length; i++) {
                (function(item, idx) {
                    var row = document.createElement('div');
                    row.className = 'sk-autocomplete-item';
                    row.setAttribute('data-idx', idx);

                    if (mode === 'mention') {
                        if (item.avatar_small) {
                            var img = document.createElement('img');
                            img.className = 'sk-mention-avatar';
                            img.src = 'data:' + (item.avatar_mime || 'image/jpeg') + ';base64,' + item.avatar_small;
                            row.appendChild(img);
                        }
                        var nameSpan = document.createElement('span');
                        nameSpan.textContent = item.display_name || item.id;
                        var idSpan = document.createElement('span');
                        idSpan.className = 'sk-autocomplete-item-sub';
                        idSpan.textContent = item.id;
                        row.appendChild(nameSpan);
                        row.appendChild(idSpan);
                    } else {
                        var titleSpan = document.createElement('span');
                        titleSpan.textContent = item.title || ('ID ' + item.id);
                        row.appendChild(titleSpan);
                        if (item.template) {
                            var tmplSpan = document.createElement('span');
                            tmplSpan.className = 'sk-autocomplete-item-sub';
                            tmplSpan.textContent = item.template;
                            row.appendChild(tmplSpan);
                        }
                    }

                    row.addEventListener('mousedown', function(e) {
                        e.preventDefault();
                        _setActive(idx);
                        onSelect(item);
                        _removePopup();
                    });
                    popup.appendChild(row);
                })(shown[i], i);
            }

            document.body.appendChild(popup);
            acPopup = popup;
        }

        function _setActive(idx) {
            if (!acPopup) return;
            acIdx = idx;
            var rows = acPopup.querySelectorAll('.sk-autocomplete-item');
            for (var i = 0; i < rows.length; i++) {
                if (i === idx) rows[i].classList.add('active');
                else rows[i].classList.remove('active');
            }
        }

        // Parse current trigger: returns {mode, query, triggerStart} or null
        function _parseTrigger(textarea) {
            var val = textarea.value;
            var pos = textarea.selectionEnd;
            // Scan backwards from caret to find @ or [[ trigger
            var i = pos - 1;
            while (i >= 0 && i >= pos - 200) {
                var ch = val[i];
                if (ch === '\n') break;
                if (ch === '@') {
                    var query = val.slice(i + 1, pos);
                    if (!/\s/.test(query)) {
                        return { mode: 'mention', query: query, triggerStart: i };
                    }
                    break;
                }
                if (i >= 1 && val[i] === '[' && val[i - 1] === '[') {
                    var query2 = val.slice(i + 1, pos);
                    if (!/\s/.test(query2)) {
                        return { mode: 'doc', query: query2, triggerStart: i - 1 };
                    }
                    break;
                }
                i--;
            }
            return null;
        }

        function _insertToken(textarea, triggerStart, token) {
            var val = textarea.value;
            var pos = textarea.selectionEnd;
            var before = val.slice(0, triggerStart);
            var after = val.slice(pos);
            textarea.value = before + token + after;
            var newPos = triggerStart + token.length;
            textarea.selectionStart = textarea.selectionEnd = newPos;
            if (onChange) onChange();
        }

        function _onAcSelect(item, trigger) {
            if (!ta) return;
            var token;
            if (trigger.mode === 'mention') {
                token = '@[' + item.id + '|' + item.display_name + ']';
            } else {
                token = '[[' + item.id + '|' + item.title + ']]';
            }
            _insertToken(ta, trigger.triggerStart, token);
        }

        function _handleInput(textarea) {
            if (!mentionSearch && !docSearch) return;
            var trigger = _parseTrigger(textarea);
            if (!trigger) {
                _removePopup();
                return;
            }
            if (trigger.mode === 'mention' && mentionSearch) {
                var capturedTrigger = trigger;
                mentionSearch(trigger.query, function(items) {
                    // Check trigger is still valid
                    var currentTrigger = _parseTrigger(textarea);
                    if (!currentTrigger || currentTrigger.mode !== 'mention' ||
                        currentTrigger.triggerStart !== capturedTrigger.triggerStart) return;
                    _showPopup(textarea, items, 'mention', function(item) {
                        _onAcSelect(item, capturedTrigger);
                    });
                });
            } else if (trigger.mode === 'doc' && docSearch) {
                var capturedTrigger2 = trigger;
                clearTimeout(acDocDebounce);
                acDocDebounce = setTimeout(function() {
                    var currentTrigger = _parseTrigger(textarea);
                    if (!currentTrigger || currentTrigger.mode !== 'doc' ||
                        currentTrigger.triggerStart !== capturedTrigger2.triggerStart) return;
                    docSearch(capturedTrigger2.query, function(items) {
                        var currentTrigger2 = _parseTrigger(textarea);
                        if (!currentTrigger2 || currentTrigger2.mode !== 'doc' ||
                            currentTrigger2.triggerStart !== capturedTrigger2.triggerStart) return;
                        _showPopup(textarea, items, 'doc', function(item) {
                            _onAcSelect(item, capturedTrigger2);
                        });
                    });
                }, 300);
            }
        }

        function _handleKeydown(e) {
            if (!acPopup) return;
            var count = acItems.length > 8 ? 8 : acItems.length;
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                _setActive((acIdx + 1) % count);
                return;
            }
            if (e.key === 'ArrowUp') {
                e.preventDefault();
                _setActive((acIdx - 1 + count) % count);
                return;
            }
            if (e.key === 'Escape') {
                e.preventDefault();
                _removePopup();
                return;
            }
            if (e.key === 'Enter' || e.key === 'Tab') {
                var target = acIdx >= 0 ? acItems[acIdx] : acItems[0];
                if (target) {
                    e.preventDefault();
                    var trigger = _parseTrigger(ta);
                    if (trigger) _onAcSelect(target, trigger);
                    _removePopup();
                }
            }
        }

        if (ta) {
            // _refreshMdPreview: external callers can trigger preview refresh via
            // el.value = newVal; el._refreshMdPreview(); (applySetValues pattern)
            ta._refreshMdPreview = switchToView;
            ta._switchToEdit = switchToEdit;
            // _getValue: returns the expanded value (data URLs restored from tokens).
            // Use instead of ta.value when imagePaste is active.
            ta._getValue = function() {
                return imagePaste ? _imgExpand(ta.value) : ta.value;
            };

            function _autoResize() {
                if (!autoResize || !_isLastInParent()) return;
                ta.style.height = 'auto';
                ta.style.height = ta.scrollHeight + 'px';
            }
            if (onChange) ta.addEventListener('input', onChange);
            ta.addEventListener('input', _autoResize);
            ta.addEventListener('input', function() { _handleInput(ta); });
            ta.addEventListener('keydown', _handleKeydown);
            ta.addEventListener('blur', function() {
                // Delay removal so mousedown on popup item fires first
                setTimeout(_removePopup, 150);
                switchToView();
                if (onBlur) onBlur();
            });
            editBtn.addEventListener('click', function() { editBtn.blur(); switchToEdit(); });

            if (imagePaste) {
                ta.addEventListener('paste', function(e) {
                    var items = e.clipboardData && e.clipboardData.items;
                    if (!items) return;
                    for (var i = 0; i < items.length; i++) {
                        if (!items[i].type.startsWith('image/')) continue;
                        e.preventDefault();
                        var file = items[i].getAsFile();
                        var img = new Image();
                        var url = URL.createObjectURL(file);
                        (function(capturedImg, capturedUrl) {
                            capturedImg.onload = function() {
                                URL.revokeObjectURL(capturedUrl);
                                var canvas = document.createElement('canvas');
                                canvas.width  = capturedImg.naturalWidth;
                                canvas.height = capturedImg.naturalHeight;
                                canvas.getContext('2d').drawImage(capturedImg, 0, 0);
                                var dataUrl = canvas.toDataURL('image/webp', 0.85);
                                var imgId = ++imgSeq;
                                imgMap[imgId] = dataUrl;
                                var token = '![](image:' + imgId + ')';
                                var start = ta.selectionStart;
                                var end   = ta.selectionEnd;
                                ta.value = ta.value.slice(0, start) + token + ta.value.slice(end);
                                ta.selectionStart = ta.selectionEnd = start + token.length;
                                if (onChange) onChange();
                            };
                            capturedImg.src = capturedUrl;
                        })(img, url);
                        break;
                    }
                });
            }
        }

        wrap.appendChild(preview);
        if (ta)      wrap.appendChild(ta);
        if (editBtn) wrap.appendChild(editBtn);

        if (initVal.trim()) {
            switchToView();
        } else if (!readonly) {
            preview.style.display = 'none';
            if (editBtn) editBtn.style.display = 'none';
        }

        return {
            element:  wrap,
            getValue: function() {
                if (!ta) return initVal;
                return imagePaste ? _imgExpand(ta.value) : ta.value;
            },
            setValue: function(v) {
                initVal = v;
                if (ta) ta.value = imagePaste ? _imgTokenize(v) : v;
                switchToView();
            },
            refresh:  function() { switchToView(); },
            focus:    function() { switchToEdit(); }
        };
    }

    global.SkMdControl = { renderMd: renderMd, build: build };
})(window);
