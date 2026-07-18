// frontend/app.js

// Global State
let currentDoc = null;
let chatHistory = [];
let meetings = [];
let pastMeetings = [];
let allMeetings = [];
let selFolder = null; // index trong allMeetings
let pendingFiles = []; // Tệp đã chọn để tải lên
let delTarget = null; // {mi, di}
let delMeetTarget = null; // mi
let fsIdx = 1; // Font size index (A-, A, A+)
const FS_STEPS = [0.9, 1, 1.12, 1.26];
let reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

// Default Mock Structure of Meetings (from prototype)
const DEFAULT_MEETINGS = [];
const DEFAULT_PAST_MEETINGS = [];

// Initialize on DOM load
document.addEventListener('DOMContentLoaded', () => {
    initMeetingsState();
    checkCurrentDocument();
    initUploadEvents();
    initSpeechRecognition();
    buildTrongDong();
    
    // Initial UI bindings
    moveUnderline();
    window.addEventListener('resize', moveUnderline);
    
    // Check saved login session
    const savedUser = localStorage.getItem('gov_user');
    const savedDept = localStorage.getItem('gov_dept');
    if (savedUser && savedDept) {
        document.body.classList.add('authed');
        const welcomeEl = document.getElementById('welcomeName');
        if (welcomeEl) welcomeEl.textContent = savedUser;
        // GSAP Intro animations
        animateIntro();
    } else {
        initLoginAnimation();
    }
});

// Initialize Meetings State (LocalStorage & Backend sync)
async function initMeetingsState() {
    // Load from localStorage if available
    const localM = localStorage.getItem('gov_meetings');
    const localPM = localStorage.getItem('gov_past_meetings');
    
    if (localM && localPM) {
        meetings = JSON.parse(localM);
        pastMeetings = JSON.parse(localPM);
    } else {
        meetings = JSON.parse(JSON.stringify(DEFAULT_MEETINGS));
        pastMeetings = JSON.parse(JSON.stringify(DEFAULT_PAST_MEETINGS));
    }
    
    // Tự động xoá/lọc bỏ các kỳ họp tĩnh mặc định khỏi bộ nhớ local storage nếu chúng còn tồn tại
    const mockNames = [
        'Kỳ họp thứ 12 · HĐND tỉnh',
        'Phiên họp UBND tháng 8',
        'Hội nghị chuyên đề cải cách hành chính',
        'Kỳ họp thứ 11 · HĐND tỉnh',
        'Phiên họp UBND tháng 6'
    ];
    meetings = meetings.filter(m => !mockNames.includes(m.name));
    pastMeetings = pastMeetings.filter(m => !mockNames.includes(m.name));
    saveMeetingsToLocal();
    
    // Sync with backend files list
    await syncWithBackendFiles();
    renderMeetings();
}

function saveMeetingsToLocal() {
    localStorage.setItem('gov_meetings', JSON.stringify(meetings));
    localStorage.setItem('gov_past_meetings', JSON.stringify(pastMeetings));
}

// Fetch files from backend and insert them into the folders if not already present
async function syncWithBackendFiles() {
    try {
        const response = await fetch('/api/document/list');
        const result = await response.json();
        if (result.status === 'success' && result.data) {
            const backendFiles = result.data; // array of { filename, page_count }
            
            // Collect all file names in current local state
            const localFileNames = new Set();
            meetings.forEach(m => m.docs.forEach(d => localFileNames.add(d.t.toLowerCase())));
            pastMeetings.forEach(m => m.docs.forEach(d => localFileNames.add(d.t.toLowerCase())));
            
            // Check for new backend files
            backendFiles.forEach(file => {
                const fname = file.filename;
                const baseName = fname.replace(/\.[^/.]+$/, ""); // strip extension
                
                // If this file is not found in our folders, add it to the first folder
                if (!localFileNames.has(fname.toLowerCase()) && !localFileNames.has(baseName.toLowerCase())) {
                    if (meetings.length === 0) {
                        meetings.push({ name: 'Thư mục cuộc họp mặc định', date: '—', docs: [], open: true });
                    }
                    meetings[0].docs.push({ t: fname, on: false });
                }
            });
            saveMeetingsToLocal();
        }
    } catch (e) {
        console.error('Lỗi đồng bộ danh sách tài liệu từ backend:', e);
    }
}

// Check active document on system
async function checkCurrentDocument() {
    showLoading('Đang kiểm tra tài liệu...', 'Đang tải dữ liệu phiên làm việc hiện tại');
    try {
        const response = await fetch('/api/document/current');
        const result = await response.json();
        if (result.status === 'success' && result.data && result.data.pages) {
            loadDocumentData(result.data);
        } else {
            showEmptyState();
            hideLoading();
        }
    } catch (e) {
        console.error('Lỗi kiểm tra tài liệu hiện tại:', e);
        showEmptyState();
        hideLoading();
    }
}

function showLoading(title = 'Đang tải và xử lý tài liệu...', sub = 'Hệ thống đang đồng bộ nội dung và phân tích thuật ngữ AI') {
    const overlay = document.getElementById('doc-loading-overlay');
    if (overlay) {
        document.getElementById('loading-title').textContent = title;
        document.getElementById('loading-sub').textContent = sub;
        hideEmptyState(); 
        overlay.style.display = 'flex';
    }
}

function hideLoading() {
    const overlay = document.getElementById('doc-loading-overlay');
    if (overlay) {
        overlay.style.display = 'none';
    }
}

function showEmptyState() {
    document.getElementById('empty-state-container').style.display = 'flex';
    document.getElementById('workspace-container').style.display = 'none';
}

// Ensure the helper is exposed globally so other scripts can use it
window.showLoading = showLoading;
window.hideLoading = hideLoading;

function hideEmptyState() {
    document.getElementById('empty-state-container').style.display = 'none';
    document.getElementById('workspace-container').style.display = 'grid';
}

// Load document details and analysis into UI
function loadDocumentData(doc) {
    currentDoc = doc;
    chatHistory = [];
    hideEmptyState();

    // 1. Update active document indicators in meetings list
    updateActiveDocInMeetings(doc.filename);
    
    // 2. Set headers
    const titleText = doc.filename.replace(/\.[^/.]+$/, ""); // strip extension
    document.getElementById('doc-title-header').innerHTML = `<span class="badge">DỰ THẢO</span>${titleText}`;
    
    const pageCountVal = document.getElementById('page-count-val');
    pageCountVal.setAttribute('data-count', doc.pages.length);
    pageCountVal.textContent = doc.pages.length;
    countUp(pageCountVal);
    
    // 3. Render Document Text with term tooltips wrapping
    renderDocumentPane(doc);
    
    // 4. Load Tabs data (Tóm tắt, Thuật ngữ, Câu hỏi, Hỏi đáp)
    const analysis = doc.analysis || {};
    
    // Initialize Summary (5-minute summary is default)
    renderSummaryTab(analysis.summary);
    
    // Initialize Terminology
    renderTerminologyTab(analysis.terminology || []);
    
    // Initialize Questions
    renderQuestionsTab(analysis.suggested_questions || []);
    
    // Initialize Chat
    const thread = document.getElementById('thread');
    thread.innerHTML = `
      <div class="ans">
        <div class="ans-body">
          Chào bạn! Tôi là trợ lý AI chuẩn bị họp. Tôi đã đọc tài liệu <b>“${doc.filename}”</b> (${doc.pages.length} trang) và trích xuất các thông tin quan trọng. Bạn có thể hỏi tôi bất kỳ điều gì liên quan đến tài liệu này.
        </div>
      </div>
    `;
    
    // Adjust sidebar details if available
    updateSidebarCountdown(doc.filename);
    hideLoading();
}

// Update Active document indicator in Accordion meetings list
function updateActiveDocInMeetings(activeFilename) {
    const stripExt = (name) => name.replace(/\.[^/.]+$/, "").toLowerCase();
    const activeClean = stripExt(activeFilename);
    
    let found = false;
    meetings.forEach(m => {
        m.docs.forEach(d => {
            const isMatch = stripExt(d.t) === activeClean;
            d.on = isMatch;
            if (isMatch) {
                m.open = true;
                found = true;
            }
        });
    });
    pastMeetings.forEach(m => {
        m.docs.forEach(d => {
            const isMatch = stripExt(d.t) === activeClean;
            d.on = isMatch;
            if (isMatch) {
                m.open = true;
                found = true;
            }
        });
    });
    
    saveMeetingsToLocal();
    renderMeetings();
}

function updateSidebarCountdown(filename) {
    // Dynamic countdown based on doc or folder
    const daysEl = document.getElementById('countdown-days');
    let isPast = false;
    let meetingTitle = 'Kỳ họp thứ 12 · HĐND tỉnh';
    let rDate = '—';
    let mDate = 'Chưa có lịch';
    let daysRemaining = '—';
    
    allMeetings.forEach(m => {
        m.docs.forEach(d => {
            if (d.on) {
                isPast = m.past;
                meetingTitle = m.name;
                const dPart = m.date.split('/');
                if (dPart.length === 3) {
                    const day = parseInt(dPart[0]);
                    const rDay = day > 1 ? day - 1 : day;
                    rDate = `${rDay.toString().padStart(2, '0')}/${dPart[1]}`;
                    mDate = `${dPart[0]}/${dPart[1]} · 08:00`;
                    
                    // Dynamic countdown calculation
                    const today = new Date();
                    today.setHours(0, 0, 0, 0);
                    const meetD = new Date(parseInt(dPart[2]), parseInt(dPart[1]) - 1, parseInt(dPart[0]));
                    meetD.setHours(0, 0, 0, 0);
                    
                    const diffTime = meetD.getTime() - today.getTime();
                    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
                    if (diffDays <= 0) {
                        daysRemaining = 0;
                        isPast = true;
                    } else {
                        daysRemaining = diffDays;
                    }
                }
            }
        });
    });
    
    daysEl.setAttribute('data-count', daysRemaining);
    daysEl.textContent = daysRemaining;
    if (typeof daysRemaining === 'number') {
        countUp(daysEl);
    }
    
    document.getElementById('sidebar-meeting-title').textContent = meetingTitle;
    document.getElementById('sidebar-receive-date').innerHTML = `Nhận tài liệu <b>${rDate}</b>`;
    document.getElementById('sidebar-meeting-date').innerHTML = `Họp <b>${mDate}</b>`;
}

// Render dynamic pages in left docpane and wrap terminology terms
function renderDocumentPane(doc) {
    const container = document.getElementById('doc-content-body');
    const terminology = doc.analysis?.terminology || [];
    
    let html = '';
    doc.pages.forEach(p => {
        html += `<div class="pagemark">Trang ${p.page_num} / ${doc.pages.length}</div>`;
        const lines = p.text.split('\n');
        lines.forEach(line => {
            const trimmed = line.trim();
            if (!trimmed) return;
            
            // Heuristics for formatting paragraphs and headings
            if (trimmed.startsWith('Điều ') || trimmed.startsWith('Chương ') || trimmed.startsWith('Mục ') || trimmed.match(/^[I|V|X|L|C|D|M]+\./)) {
                const uniqueId = `page-${p.page_num}-header-${encodeURIComponent(trimmed.slice(0, 15))}`;
                html += `<h2 id="${uniqueId}">${trimmed}</h2>`;
            } else if (trimmed.includes('Điều khoản quan trọng') || trimmed.startsWith('Quan trọng:') || trimmed.startsWith('Lưu ý:')) {
                html += `<div class="imp"><div class="imp-lbl">Điều khoản quan trọng</div><p>${trimmed}</p></div>`;
            } else {
                html += `<p>${trimmed}</p>`;
            }
        });
    });
    
    // Wrap terminology terms inside the rendered HTML
    const wrappedHTML = wrapTermsInDOM(html, terminology);
    container.innerHTML = wrappedHTML;
    
    // Re-initialize ScrollTrigger for new document content with optimized performance
    setTimeout(() => {
        // Kill previous scroll triggers to free memory and prevent lag
        ScrollTrigger.getAll().forEach(t => t.kill());
        
        // Fast fade-in for the whole document block once
        gsap.fromTo('#doc-content-body', { autoAlpha: 0, y: 10 }, { autoAlpha: 1, y: 0, duration: 0.35, ease: 'power2.out' });
        
        // Only trigger on key headers to keep animations premium but lightweight
        gsap.utils.toArray('.doc h2').forEach(el => {
            gsap.from(el, {
                y: 10,
                autoAlpha: 0,
                duration: 0.4,
                ease: 'power2.out',
                scrollTrigger: {
                    trigger: el,
                    scroller: '#docpane',
                    start: 'top 95%',
                    once: true
                }
            });
        });
        ScrollTrigger.refresh();
    }, 100);
}

// Highly optimized single-pass RegExp approach to safely insert term spans
function wrapTermsInDOM(htmlString, terminology) {
    if (!terminology || terminology.length === 0) return htmlString;
    
    const parser = new DOMParser();
    const doc = parser.parseFromString(`<div>${htmlString}</div>`, 'text/html');
    const container = doc.body.firstChild;
    
    // Sort terminology by length descending to match longer phrases first
    const sortedTerms = [...terminology].sort((a, b) => b.term.length - a.term.length);
    
    // Fast O(1) definition lookup map
    const termMap = new Map();
    sortedTerms.forEach(t => {
        termMap.set(t.term.toLowerCase(), t.definition);
    });
    
    // Build combined escaping regex patterns
    const escapeRegExp = (str) => str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const pattern = sortedTerms.map(t => escapeRegExp(t.term)).join('|');
    const regex = new RegExp(`(${pattern})`, 'gi');
    
    // Vietnamese word boundary validation helper
    const isWordChar = (char) => {
        if (!char) return false;
        return /^[a-zA-Z0-9_À-ỹ]$/.test(char);
    };
    
    // Fetch all text nodes in order
    const walk = document.createTreeWalker(container, NodeFilter.SHOW_TEXT, null, false);
    let node;
    const textNodes = [];
    while (node = walk.nextNode()) {
        textNodes.push(node);
    }
    
    textNodes.forEach(textNode => {
        const text = textNode.nodeValue;
        if (!text.trim()) return;
        
        let lastIdx = 0;
        let match;
        const parent = textNode.parentNode;
        if (!parent) return;
        
        const fragment = document.createDocumentFragment();
        let hasMatches = false;
        
        // Reset RegExp execution index
        regex.lastIndex = 0;
        
        while ((match = regex.exec(text)) !== null) {
            const matchedText = match[0];
            const start = match.index;
            const end = start + matchedText.length;
            
            // Validate boundaries so it doesn't wrap part of a word
            const prevChar = start > 0 ? text[start - 1] : ' ';
            const nextChar = end < text.length ? text[end] : ' ';
            
            if (isWordChar(prevChar) || isWordChar(nextChar)) {
                continue;
            }
            
            hasMatches = true;
            
            // Append preceding text block
            if (start > lastIdx) {
                fragment.appendChild(document.createTextNode(text.substring(lastIdx, start)));
            }
            
            // Create term span element
            const def = termMap.get(matchedText.toLowerCase()) || '';
            const termSpan = document.createElement('span');
            termSpan.className = 'term';
            termSpan.setAttribute('data-def', def);
            termSpan.textContent = matchedText;
            fragment.appendChild(termSpan);
            
            lastIdx = end;
        }
        
        if (hasMatches) {
            if (lastIdx < text.length) {
                fragment.appendChild(document.createTextNode(text.substring(lastIdx)));
            }
            parent.replaceChild(fragment, textNode);
        }
    });
    
    return container.innerHTML;
}

// ---------------- TAB 1: TÓM TẮT (SUMMARY) ----------------
function renderSummaryTab(summaryData) {
    const summaryBody = document.getElementById('summaryBody');
    if (!summaryData) {
        summaryBody.innerHTML = '<div class="sec"><div class="sec-txt">Không có dữ liệu tóm tắt cho tài liệu này.</div></div>';
        return;
    }
    
    // Store in global variable for setTier callback
    window.currentDocSummary = summaryData;
    
    // Render the default 5-minute summary
    setTier(5);
}

function setTier(t) {
    document.querySelectorAll('.tier').forEach(el => el.classList.toggle('on', el.dataset.tier == t));
    const hints = {
        1: 'Bản 1 phút — chỉ những gì cần biết trước khi vào họp',
        5: 'Bản 5 phút — tóm tắt đầy đủ theo bốn mục',
        0: 'Toàn văn — phân tích chi tiết từng mục'
    };
    
    const hintEl = document.getElementById('tierHint');
    if (hintEl) {
        hintEl.lastChild.textContent = ' ' + hints[t];
    }
    
    const summary = window.currentDocSummary || {};
    
    // Formulate summaries depending on tier
    let summaryItems = [];
    
    if (t === 1) {
        // Quick 1-minute summary: taking shortened versions of the texts
        summaryItems = [
          { ic: 'map', lbl: 'Bối cảnh', txt: getFirstSentence(summary.context || 'Bối cảnh ban hành tài liệu cuộc họp.') },
          { ic: 'doc', lbl: 'Nội dung chính', txt: getFirstSentence(summary.main_content || 'Tóm tắt nội dung chính và các điều khoản.') },
          { ic: 'check', lbl: 'Điểm cần quyết định', txt: getFirstSentence(summary.decision_points || 'Các chỉ tiêu và phê duyệt cần thông qua.') },
          { ic: 'warn', lbl: 'Tác động cần lưu ý', txt: getFirstSentence(summary.impact || 'Tác động đến các sở ban ngành liên quan.') }
        ];
    } else if (t === 0) {
        // Full summary text
        summaryItems = [
          { ic: 'map', lbl: 'Bối cảnh', txt: summary.context || 'Bối cảnh ban hành văn bản.' },
          { ic: 'doc', lbl: 'Nội dung chính', txt: summary.main_content || 'Nội dung chi tiết của kế hoạch cuộc họp.' },
          { ic: 'check', lbl: 'Điểm cần quyết định', txt: summary.decision_points || 'Danh sách các chỉ tiêu bắt buộc cần lưu ý duyệt.' },
          { ic: 'warn', lbl: 'Tác động cần lưu ý', txt: summary.impact || 'Đánh giá tác động xã hội và các chính sách kèm theo.' }
        ];
    } else {
        // Default 5-minute: slightly formatted mid-length summary
        summaryItems = [
          { ic: 'map', lbl: 'Bối cảnh', txt: getMidText(summary.context, 150) },
          { ic: 'doc', lbl: 'Nội dung chính', txt: getMidText(summary.main_content, 150) },
          { ic: 'check', lbl: 'Điểm cần quyết định', txt: getMidText(summary.decision_points, 150) },
          { ic: 'warn', lbl: 'Tác động cần lưu ý', txt: getMidText(summary.impact, 150) }
        ];
    }
    
    const icons = {
      map: '<path d="M9 20 3 17V4l6 3 6-3 6 3v13l-6-3-6 3zM9 7v13M15 4v13"/>',
      doc: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5M9 13h6M9 17h6"/>',
      check: '<path d="M9 11l3 3 8-8M20 12v7a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h9"/>',
      warn: '<path d="M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>'
    };
    
    document.getElementById('summaryBody').innerHTML = summaryItems.map(s => `
      <div class="sec">
        <div class="sec-ic" style="background:#fdecea;color:#da251d">
          <svg class="i" style="width:17px;height:17px" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">${icons[s.ic]}</svg>
        </div>
        <div>
          <div class="sec-lbl">${s.lbl}</div>
          <div class="sec-txt">${s.txt} <span class="cite" onclick="scrollTophysPage(1)">📍 Trang 1</span></div>
        </div>
      </div>`).join('');
      
    animateStagger('#summaryBody .sec');
    
    if (!reduce) {
      const on = document.querySelector('.tier.on');
      if (on) gsap.fromTo(on, { scale: 0.92 }, { scale: 1, duration: 0.4, ease: 'back.out(2.2)' });
    }
}

function getFirstSentence(text) {
    if (!text) return '';
    const sentences = text.split(/[.!?]/g);
    return sentences.length > 0 ? (sentences[0].trim() + '.') : text;
}

function getMidText(text, limit) {
    if (!text) return '';
    if (text.length <= limit) return text;
    return text.substring(0, limit) + '...';
}

// ---------------- TAB 2: THUẬT NGỮ (TERMINOLOGY) ----------------
function renderTerminologyTab(terminologyList) {
    // Store in global
    window.currentTerminology = terminologyList;
    
    const countEl = document.getElementById('termCount');
    countEl.textContent = terminologyList.length;
    
    filterTerms('');
}

function filterTerms(query) {
    const list = window.currentTerminology || [];
    const q = query.toLowerCase().trim();
    
    const filtered = list.filter(t => t.term.toLowerCase().includes(q) || t.definition.toLowerCase().includes(q));
    
    const getTermCat = (name) => {
        const n = name.toLowerCase();
        if (n.includes('ngân sách') || n.includes('thu') || n.includes('chi') || n.includes('tài chính') || n.includes('dự toán') || n.includes('vốn') || n.includes('tăng thu')) {
            return { cat: 'fin', lbl: 'tài chính' };
        } else if (n.includes('luật') || n.includes('nghị quyết') || n.includes('quy định') || n.includes('pháp lý') || n.includes('hiệu lực') || n.includes('điều')) {
            return { cat: 'law', lbl: 'pháp lý' };
        } else {
            return { cat: 'adm', lbl: 'hành chính' };
        }
    };
    
    const termList = document.getElementById('termList');
    if (filtered.length === 0) {
        termList.innerHTML = '<div class="sec"><div class="sec-txt">Không tìm thấy thuật ngữ phù hợp.</div></div>';
        return;
    }
    
    termList.innerHTML = filtered.map(t => {
        const cInfo = getTermCat(t.term);
        const pagesStr = (t.pages || [1]).join(', ');
        const firstPage = (t.pages && t.pages.length > 0) ? t.pages[0] : 1;
        
        return `
          <div class="term-item">
            <div class="term-top">
              <span class="term-name">${t.term}</span>
              <span class="tag tag-${cInfo.cat}">${cInfo.lbl}</span>
            </div>
            <div class="term-expl">${t.definition}</div>
            <span class="chip" onclick="scrollTophysPage(${firstPage})">📍 Trang ${pagesStr}</span>
          </div>
        `;
    }).join('');
    
    animateStagger('#termList .term-item');
}

function applyFilter() {
    const v = document.getElementById('fieldFilter').value;
    const list = window.currentTerminology || [];
    
    if (v === 'all') {
        filterTerms('');
        return;
    }
    
    const getTermCatCode = (name) => {
        const n = name.toLowerCase();
        if (n.includes('ngân sách') || n.includes('thu') || n.includes('chi') || n.includes('tài chính') || n.includes('dự toán') || n.includes('vốn') || n.includes('tăng thu')) {
            return 'fin';
        } else if (n.includes('luật') || n.includes('nghị quyết') || n.includes('quy định') || n.includes('pháp lý') || n.includes('hiệu lực') || n.includes('điều')) {
            return 'law';
        } else {
            return 'adm';
        }
    };
    
    const filtered = list.filter(t => getTermCatCode(t.term) === v);
    
    // Render filtered terms directly
    const getTermCat = (name) => {
        const n = name.toLowerCase();
        if (n.includes('ngân sách') || n.includes('thu') || n.includes('chi') || n.includes('tài chính') || n.includes('dự toán') || n.includes('vốn') || n.includes('tăng thu')) {
            return { cat: 'fin', lbl: 'tài chính' };
        } else if (n.includes('luật') || n.includes('nghị quyết') || n.includes('quy định') || n.includes('pháp lý') || n.includes('hiệu lực') || n.includes('điều')) {
            return { cat: 'law', lbl: 'pháp lý' };
        } else {
            return { cat: 'adm', lbl: 'hành chính' };
        }
    };
    
    const termList = document.getElementById('termList');
    if (filtered.length === 0) {
        termList.innerHTML = '<div class="sec"><div class="sec-txt">Không tìm thấy thuật ngữ thuộc lĩnh vực này.</div></div>';
        return;
    }
    
    termList.innerHTML = filtered.map(t => {
        const cInfo = getTermCat(t.term);
        const pagesStr = (t.pages || [1]).join(', ');
        const firstPage = (t.pages && t.pages.length > 0) ? t.pages[0] : 1;
        
        return `
          <div class="term-item">
            <div class="term-top">
              <span class="term-name">${t.term}</span>
              <span class="tag tag-${cInfo.cat}">${cInfo.lbl}</span>
            </div>
            <div class="term-expl">${t.definition}</div>
            <span class="chip" onclick="scrollTophysPage(${firstPage})">📍 Trang ${pagesStr}</span>
          </div>
        `;
    }).join('');
    
    animateStagger('#termList .term-item');
}

// ---------------- TAB 3: CÂU HỎI (QUESTIONS) ----------------
function renderQuestionsTab(suggestedQuestions) {
    const listEl = document.getElementById('questionList');
    const countEl = document.getElementById('questionCount');
    countEl.textContent = suggestedQuestions.length;
    
    if (suggestedQuestions.length === 0) {
        listEl.innerHTML = '<div class="sec"><div class="sec-txt">Không có câu hỏi gợi ý nào cho tài liệu này.</div></div>';
        return;
    }
    
    // Group questions into 3 categories (simulation similar to prototype)
    const grouped = [
        { grp: 'Ngân sách và tài chính', color: 'green', items: [] },
        { grp: 'Tính pháp lý', color: 'navy', items: [] },
        { grp: 'Tính khả thi', color: 'gold', items: [] }
    ];
    
    suggestedQuestions.forEach((q, i) => {
        const catIdx = i % 3;
        // Determine a page citation dynamically
        const citePage = (i % (currentDoc?.pages.length || 1)) + 1;
        grouped[catIdx].items.push({ q, cite: citePage });
    });
    
    const colorMap = { navy: '#1a1f2b', green: '#0f5132', gold: '#3a2f00' };
    
    listEl.innerHTML = grouped.filter(g => g.items.length > 0).map(g => `
      <div class="grp-lbl"><span style="width:8px;height:8px;border-radius:50%;background:${colorMap[g.color]}"></span>${g.grp}</div>
      ${g.items.map(it => `
        <div class="q">
          <div class="q-txt">${it.q}</div>
          <div class="q-foot">
            <span class="chip" onclick="scrollTophysPage(${it.cite})">📍 Trang ${it.cite}</span>
            <span class="deep" onclick="askDeep('${it.q.replace(/'/g, "\\'")}')">Hỏi sâu →</span>
          </div>
        </div>`).join('')}
    `).join('');
    
    animateStagger('#pane-q .q');
}

// ---------------- TAB 4: HỎI ĐÁP (Q&A / CHAT) ----------------
function askDeep(q) {
    showTab('qa');
    document.getElementById('qaInput').value = q;
    sendQ();
}

async function sendQ() {
    const inputEl = document.getElementById('qaInput');
    const text = inputEl.value.trim();
    if (!text) return;
    
    inputEl.value = '';
    
    // Add user question bubble
    appendChatBubble('user', text);
    
    // Add typing loader
    const typingId = appendChatBubble('typing', '');
    
    // Request server
    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: text,
                history: chatHistory.map(m => ({ role: m.role, message: m.message })),
                customer_id: null,
                role: 'admin'
            })
        });
        
        const result = await response.json();
        
        // Remove typing
        const typingEl = document.getElementById(typingId);
        if (typingEl) typingEl.remove();
        
        let answerText = "";
        let citations = [];

        if (typeof result === 'string') {
            answerText = result;
        } else if (result.answer) {
            answerText = result.answer;
            citations = result.citations || [];
        } else if (result.content) {
            answerText = result.content;
            citations = result.citations || [];
        } else {
            answerText = JSON.stringify(result);
        }
        
        // Format answer Markdown using marked.js if available
        let finalHTML = answerText;
        if (typeof marked !== 'undefined') {
            finalHTML = marked.parse(answerText);
        } else {
            finalHTML = finalHTML.replace(/\n/g, '<br>');
            finalHTML = finalHTML.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        }
        
        // Parse page citation format like [Trang X] into clickable links
        finalHTML = finalHTML.replace(/\[(?:Trang\s+)?(\d+)\]/gi, (match, pageNum) => {
            return `<span class="chip" onclick="scrollTophysPage(${pageNum})">📍 Trang ${pageNum}</span>`;
        });
        
        // Add AI response bubble
        appendChatBubble('ai', finalHTML);
        
        // Push to history
        chatHistory.push({ role: 'user', message: text });
        chatHistory.push({ role: 'ai', message: answerText });
        
    } catch (e) {
        console.error('Lỗi API Chat:', e);
        const typingEl = document.getElementById(typingId);
        if (typingEl) typingEl.remove();
        appendChatBubble('ai', 'Đã xảy ra lỗi khi kết nối máy chủ AI.');
    }
}

function appendChatBubble(role, htmlContent) {
    const thread = document.getElementById('thread');
    const bubble = document.createElement('div');
    const uniqueId = 'cb-' + Date.now() + '-' + Math.random().toString(36).substr(2, 5);
    bubble.id = uniqueId;
    
    if (role === 'user') {
        bubble.className = 'ask';
        bubble.textContent = htmlContent;
        thread.appendChild(bubble);
        
        if (!reduce) gsap.from(bubble, { y: 12, autoAlpha: 0, duration: 0.4, ease: 'back.out(1.6)' });
    } else if (role === 'typing') {
        bubble.className = 'ans';
        bubble.innerHTML = '<div class="ans-body"><div class="typing"><i></i><i></i><i></i></div></div>';
        thread.appendChild(bubble);
        
        if (!reduce) {
            gsap.from(bubble, { y: 8, autoAlpha: 0, duration: 0.3 });
            gsap.to(bubble.querySelectorAll('.typing i'), { y: -5, duration: 0.35, repeat: -1, yoyo: true, stagger: 0.12, ease: 'sine.inOut' });
        }
    } else {
        bubble.className = 'ans';
        bubble.innerHTML = `
          <div class="ans-body">
            ${htmlContent}
            <div class="verify"><svg class="i vchk" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 6 9 17l-5-5"/></svg>Đã đối chiếu với văn bản gốc</div>
          </div>
        `;
        thread.appendChild(bubble);
        
        if (!reduce) {
            gsap.from(bubble, { y: 10, autoAlpha: 0, duration: 0.4 });
            const chk = bubble.querySelector('.vchk path');
            if (chk) {
                const len = chk.getTotalLength();
                gsap.fromTo(chk, { strokeDasharray: len, strokeDashoffset: len }, { strokeDashoffset: 0, duration: 0.5, delay: 0.3, ease: 'power2.out' });
            }
        }
    }
    
    scrollThread();
    return uniqueId;
}

function scrollThread() {
    const w = document.querySelector('.tabwrap');
    gsap.to(w, { scrollTop: w.scrollHeight, duration: reduce ? 0 : 0.4, ease: 'power2.out' });
}

// ---------------- ACCORDION & DIRECTORY UTILITIES ----------------
function renderMeetings() {
    allMeetings = [...meetings, ...pastMeetings.map(m => ({ ...m, past: true }))];
    const upcoming = allMeetings.slice(0, meetings.length);
    const past = allMeetings.slice(meetings.length);
    const wrap = document.getElementById('meetingList');
    
    const meetHTML = (m, i) => {
        return `
          <div class="meet ${m.open ? 'on' : ''} ${m.past ? 'past' : ''}" data-i="${i}">
            <div class="meet-head" onclick="toggleMeet(${i})">
              <span class="meet-dot"></span>
              <div class="meet-name">${m.name}<div class="meet-sub">Họp ${m.date} · ${m.docs.length} tài liệu</div></div>
              <button class="meet-del" title="Xoá kỳ họp" onclick="askDelMeet(event, ${i})">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m2 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/></svg>
              </button>
              <svg class="meet-chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>
            </div>
            <div class="meet-body">
              ${m.docs.map((d, di) => `
                <div class="doc-item ${d.on ? 'on' : ''}" onclick="selectDoc(${i}, ${di})">
                  <span class="dot"></span>
                  <span class="di-name">${d.t}</span>
                  <button class="doc-del" title="Xoá tài liệu" onclick="askDelDoc(event,${i},${di})">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6 6 18M6 6l12 12"/></svg>
                  </button>
                </div>
              `).join('')}
            </div>
          </div>`;
    };
    
    wrap.innerHTML = 
      `<p class="rail-lbl">Kỳ họp sắp tới</p>` +
      upcoming.map((m, k) => meetHTML(m, k)).join('') +
      `<p class="rail-lbl rail-lbl-past">Các kỳ họp vừa qua</p>` +
      past.map((m, k) => meetHTML(m, meetings.length + k)).join('');
      
    allMeetings.forEach((m, i) => { if (m.open) setMeetBody(i, true, true); });
}

function setMeetBody(i, open, instant) {
    const body = document.querySelector(`.meet[data-i="${i}"] .meet-body`);
    if (!body) return;
    const full = body.scrollHeight;
    if (instant || reduce) { body.style.height = open ? 'auto' : '0'; return; }
    if (open) {
      gsap.fromTo(body, { height: 0 }, { height: full, duration: 0.35, ease: 'power2.out', onComplete: () => body.style.height = 'auto' });
    } else {
      gsap.fromTo(body, { height: body.scrollHeight }, { height: 0, duration: 0.28, ease: 'power2.in' });
    }
}

function toggleMeet(i) {
    const wasOpen = allMeetings[i].open;
    allMeetings[i].open = !wasOpen;
    
    // update source models
    const nUp = meetings.length;
    if (i < nUp) {
        meetings[i].open = !wasOpen;
    } else {
        pastMeetings[i - nUp].open = !wasOpen;
    }
    saveMeetingsToLocal();
    
    const el = document.querySelector(`.meet[data-i="${i}"]`);
    el.classList.toggle('on', !wasOpen);
    setMeetBody(i, !wasOpen);
}

// Select document from sidebar accordion
async function selectDoc(mi, di) {
    event.stopPropagation(); // prevent collapsing accordion
    const name = allMeetings[mi].docs[di].t;
    
    // Highlight UI immediately
    allMeetings.forEach((m, i) => {
        m.docs.forEach((d, k) => {
            d.on = (i === mi && k === di);
        });
    });
    renderMeetings();
    
    showLoading('Đang nạp tài liệu...', `Đang chuẩn bị nội dung tài liệu “${name}”`);
    
    // Call selection API
    try {
        const response = await fetch('/api/document/select', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename: name })
        });
        const result = await response.json();
        if (result.status === 'success') {
            loadDocumentData(result.data);
        } else {
            // Fallback: document might have been deleted on server, trigger upload or warn
            alert('Không tìm thấy tài liệu trên máy chủ. Bạn có thể tải lên lại.');
            hideLoading();
        }
    } catch (e) {
        console.error('Lỗi chọn tài liệu:', e);
        hideLoading();
    }
}

// ---------------- DELETE DOCUMENT ACTIONS ----------------
function askDelDoc(ev, mi, di) {
    ev.stopPropagation(); // prevent accordion toggle
    delTarget = { mi, di };
    const name = allMeetings[mi].docs[di].t;
    document.getElementById('cfText').innerHTML = `Bạn có chắc muốn xoá tài liệu <b>“${name}”</b> khỏi thư mục kỳ họp? Thao tác này không thể hoàn tác.`;
    
    const scrim = document.getElementById('confirmModal');
    scrim.classList.add('show');
    if (!reduce) gsap.fromTo('.confirm-box', { y: 16, scale: 0.96, autoAlpha: 0 }, { y: 0, scale: 1, autoAlpha: 1, duration: 0.3, ease: 'back.out(1.5)' });
}

function closeConfirm() {
    delTarget = null;
    delMeetTarget = null;
    document.getElementById('confirmModal').classList.remove('show');
}

function askDelMeet(ev, mi) {
    ev.stopPropagation(); // prevent accordion toggle
    delMeetTarget = mi;
    const name = allMeetings[mi].name;
    document.getElementById('cfText').innerHTML = `Bạn có chắc muốn xoá kỳ họp <b>“${name}”</b> cùng toàn bộ tài liệu bên trong? Thao tác này không thể hoàn tác.`;
    
    const scrim = document.getElementById('confirmModal');
    scrim.classList.add('show');
    if (!reduce) gsap.fromTo('.confirm-box', { y: 16, scale: 0.96, autoAlpha: 0 }, { y: 0, scale: 1, autoAlpha: 1, duration: 0.3, ease: 'back.out(1.5)' });
}

async function doDelMeet() {
    if (delMeetTarget === null) return;
    const mi = delMeetTarget;
    
    const nUp = meetings.length;
    const src = mi < nUp ? meetings[mi] : pastMeetings[mi - nUp];
    
    // Call delete API for all files in the meeting folder
    const deletePromises = src.docs.map(async d => {
        try {
            await fetch('/api/document/delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filename: d.t })
            });
        } catch (e) {
            console.error('Lỗi khi xoá tài liệu trong kỳ họp:', e);
        }
    });
    
    await Promise.all(deletePromises);
    
    // Remove from array
    if (mi < nUp) {
        meetings.splice(mi, 1);
    } else {
        pastMeetings.splice(mi - nUp, 1);
    }
    
    closeConfirm();
    saveMeetingsToLocal();
    renderMeetings();
    
    checkCurrentDocument();
}

async function doDelDoc() {
    if (delMeetTarget !== null) {
        await doDelMeet();
        return;
    }
    if (!delTarget) return;
    const { mi, di } = delTarget;
    const name = allMeetings[mi].name;
    
    const nUp = meetings.length;
    const src = mi < nUp ? meetings[mi] : pastMeetings[mi - nUp];
    const filename = src.docs[di].t;
    
    const wasActive = src.docs[di].on;
    
    // Call backend API to delete the file permanently from the server
    try {
        await fetch('/api/document/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename })
        });
    } catch (e) {
        console.error('Lỗi khi gọi API xoá tài liệu:', e);
    }
    
    src.docs.splice(di, 1);
    src.open = true;
    
    closeConfirm();
    saveMeetingsToLocal();
    renderMeetings();
    
    const i = allMeetings.findIndex(x => x.name === name);
    if (i >= 0) setMeetBody(i, true, true);
    
    if (wasActive) {
        checkCurrentDocument();
    }
}

// ---------------- MODAL UPLOAD ACTIONS ----------------
function openUpload() {
    // Tự động chọn thư mục kỳ họp chứa tài liệu đang active, hoặc mặc định chọn thư mục đầu tiên
    let activeFolderIdx = 0;
    if (allMeetings && allMeetings.length > 0) {
        allMeetings.forEach((m, idx) => {
            if (m.docs && m.docs.some(d => d.on)) {
                activeFolderIdx = idx;
            }
        });
        selFolder = activeFolderIdx;
    } else {
        selFolder = null;
    }
    pendingFiles = [];
    renderFolderGrid();
    renderFileList();
    cancelNewFolder();
    syncConfirm();
    
    const scrim = document.getElementById('uploadModal');
    scrim.classList.add('show');
    
    if (!reduce) {
      gsap.fromTo('.modal', { y: 20, scale: 0.96, autoAlpha: 0 }, { y: 0, scale: 1, autoAlpha: 1, duration: 0.35, ease: 'back.out(1.4)' });
      gsap.fromTo('.modal-scrim', { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.25 });
    }
}

function closeUpload() {
    const scrim = document.getElementById('uploadModal');
    if (reduce) { scrim.classList.remove('show'); return; }
    
    gsap.to('.modal', { y: 14, scale: 0.97, autoAlpha: 0, duration: 0.2, ease: 'power2.in' });
    gsap.to('.modal-scrim', { autoAlpha: 1, duration: 0.2, onComplete: () => {
        scrim.classList.remove('show');
        gsap.set('.modal-scrim', { clearProps: 'opacity,visibility' });
    }});
}

function renderFolderGrid() {
    const grid = document.getElementById('folderGrid');
    grid.innerHTML = allMeetings.map((m, i) => `
      <div class="folder ${selFolder === i ? 'on' : ''}" onclick="pickFolder(${i})">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>
        <div style="flex:1"><div class="f-name">${m.name}</div><div class="f-sub">${m.date} · ${m.docs.length} tài liệu${m.past ? ' · đã họp' : ''}</div></div>
        <div class="f-check"></div>
      </div>`).join('') +
      `<div class="folder new" onclick="showNewFolder()">＋ Tạo thư mục cuộc họp mới</div>`;
}

function pickFolder(i) {
    selFolder = i;
    renderFolderGrid();
    syncConfirm();
}

function showNewFolder() {
    document.getElementById('newFolderRow').style.display = 'flex';
    const inp = document.getElementById('newFolderName');
    inp.value = '';
    inp.focus();
    if (!reduce) gsap.from('#newFolderRow', { y: -6, autoAlpha: 0, duration: 0.25 });
}

function cancelNewFolder() {
    document.getElementById('newFolderRow').style.display = 'none';
}

function confirmNewFolder() {
    const name = document.getElementById('newFolderName').value.trim();
    const dateInput = document.getElementById('newFolderDate').value;
    if (!name) return;
    
    let displayDate = '—';
    if (dateInput) {
        const parts = dateInput.split('-');
        if (parts.length === 3) {
            displayDate = `${parts[2]}/${parts[1]}/${parts[0]}`;
        }
    }
    
    meetings.push({ name, date: displayDate, docs: [], open: false });
    saveMeetingsToLocal();
    initMeetingsState();
    
    selFolder = meetings.length - 1; // set as active folder
    cancelNewFolder();
    renderFolderGrid();
    syncConfirm();
}

function initUploadEvents() {
    const dz = document.getElementById('dropzone');
    dz.addEventListener('click', () => document.getElementById('modalFileInput').click());
    
    ['dragenter', 'dragover'].forEach(ev => dz.addEventListener(ev, e => {
        e.preventDefault();
        dz.classList.add('drag');
    }));
    
    ['dragleave', 'drop'].forEach(ev => dz.addEventListener(ev, e => {
        e.preventDefault();
        dz.classList.remove('drag');
    }));
    
    dz.addEventListener('drop', e => {
        if (e.dataTransfer.files.length > 0) {
            onPickFiles(e.dataTransfer.files);
        }
    });
}

function onPickFiles(files) {
    // Save file reference
    for (let f of files) {
        pendingFiles.push(f);
    }
    document.getElementById('modalFileInput').value = '';
    renderFileList();
    syncConfirm();
}

function renderFileList() {
    const box = document.getElementById('fileList');
    box.innerHTML = pendingFiles.map((f, k) => `
      <div class="fl-item">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5"/></svg>
        <span class="fl-n">${f.name}</span>
        <button class="fl-x" onclick="removeFile(${k})" aria-label="Bỏ tệp">×</button>
      </div>`).join('');
      
    if (!reduce && pendingFiles.length > 0) {
        gsap.from('#fileList .fl-item:last-child', { x: -8, autoAlpha: 0, duration: 0.25 });
    }
}

function removeFile(k) {
    pendingFiles.splice(k, 1);
    renderFileList();
    syncConfirm();
}

function syncConfirm() {
    document.getElementById('uploadConfirm').disabled = !(selFolder !== null && pendingFiles.length > 0);
}

// Perform document upload call and process state
async function confirmUpload() {
    if (selFolder === null || pendingFiles.length === 0) return;
    
    const file = pendingFiles[0]; // upload first file for demo/practical limits
    
    // Close modal immediately and show main screen loader!
    closeUpload();
    showLoading('Đang tải lên và phân tích tài liệu bằng AI...', `Đang xử lý tệp “${file.name}” (Quá trình này có thể mất 15-45 giây...)`);
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
        const response = await fetch('/api/document/upload', {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) throw new Error('Phân tích văn bản thất bại.');
        
        const result = await response.json();
        
        // Add file to selected local structure
        const nUp = meetings.length;
        const src = selFolder < nUp ? meetings[selFolder] : pastMeetings[selFolder - nUp];
        
        // Check if file is already in the list
        if (!src.docs.some(d => d.t === file.name)) {
            src.docs.push({ t: file.name, on: true });
        }
        src.open = true;
        saveMeetingsToLocal();
        
        // Trigger selection and render
        selectDocumentFromLibrary(file.name);
        
    } catch (e) {
        hideLoading();
        alert(e.message || 'Lỗi xử lý tải tệp.');
    }
}

async function selectDocumentFromLibrary(filename) {
    showLoading('Đang nạp tài liệu...', `Đang chuẩn bị nội dung tài liệu “${filename}”`);
    try {
        const response = await fetch('/api/document/select', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename })
        });
        const result = await response.json();
        if (result.status === 'success') {
            loadDocumentData(result.data);
        } else {
            hideLoading();
        }
    } catch (e) {
        console.error('Lỗi nạp tài liệu vừa tải lên:', e);
        hideLoading();
    }
}

// ---------------- GLOBAL DOCUMENT SEARCH ----------------
function esc(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }
function hl(text, q) { if (!q) return text; return text.replace(new RegExp('(' + esc(q) + ')', 'ig'), '<mark>$1</mark>'); }

function globalSearch(v) {
    const box = document.getElementById('tsResults');
    const q = v.trim().toLowerCase();
    if (!q) { box.classList.remove('show'); box.innerHTML = ''; return; }
    
    const up = [], past = [];
    allMeetings.forEach(m => {
        m.docs.forEach(d => {
            if (d.t.toLowerCase().includes(q)) (m.past ? past : up).push({ d, m });
        });
    });
    
    const row = (x) => `
      <div class="ts-item" onclick="openDocFromSearch('${x.m.name.replace(/'/g, "\\'")}', '${x.d.t.replace(/'/g, "\\'")}')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5"/></svg>
        <div><div class="ti-t">${hl(x.d.t, v.trim())}</div><div class="ti-s">${x.m.name} · ${x.m.date}</div></div>
      </div>`;
      
    let html = '';
    if (up.length) html += `<div class="ts-grp">Kỳ họp sắp tới</div>` + up.map(row).join('');
    if (past.length) html += `<div class="ts-grp">Các kỳ họp vừa qua</div>` + past.map(row).join('');
    if (!html) html = `<div class="ts-empty">Không tìm thấy tài liệu phù hợp</div>`;
    
    box.innerHTML = html;
    box.classList.add('show');
}

function openDocFromSearch(meetName, docName) {
    document.getElementById('tsResults').classList.remove('show');
    document.getElementById('globalSearch').value = '';
    
    // Find meeting index
    const mi = allMeetings.findIndex(m => m.name === meetName);
    if (mi >= 0) {
        if (!allMeetings[mi].open) toggleMeet(mi);
        const di = allMeetings[mi].docs.findIndex(d => d.t === docName);
        if (di >= 0) {
            selectDoc(mi, di);
            const el = document.querySelector(`.meet[data-i="${mi}"]`);
            if (el) {
                el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                if (!reduce) gsap.fromTo(el, { backgroundColor: 'rgba(255,205,0,.18)' }, { backgroundColor: 'rgba(255,255,255,.05)', duration: 1.2, clearProps: 'backgroundColor' });
            }
        }
    }
}

// ---------------- CITE JUMP & SCROLL ----------------
function scrollTophysPage(pageNum) {
    const marks = document.querySelectorAll('.pagemark');
    let targetEl = null;
    for (let mark of marks) {
        if (mark.textContent.includes(`Trang ${pageNum} /`)) {
            targetEl = mark;
            break;
        }
    }
    
    if (!targetEl) return;
    
    document.getElementById('docpane').scrollTo({ top: targetEl.offsetTop - 15, behavior: 'smooth' });
    
    // Animate next element (which is the actual content starting on that page)
    const highlightTarget = targetEl.nextElementSibling;
    if (highlightTarget && !reduce) {
        gsap.fromTo(highlightTarget, { backgroundColor: 'rgba(255,205,0,.55)' }, { backgroundColor: 'transparent', duration: 1.6, ease: 'power2.out', clearProps: 'backgroundColor' });
        gsap.fromTo(highlightTarget, { scale: 1 }, { scale: 1.01, duration: 0.22, yoyo: true, repeat: 1, ease: 'power1.inOut', transformOrigin: 'left center' });
    }
}

// ---------------- NOTIFICATIONS ACTIONS ----------------
const MOCK_NOTIFS = [
  { t: 'Đã cập nhật hệ thống: sẵn sàng nạp tài liệu Word, PDF.', time: 'Hôm nay · 09:12' },
  { t: 'Tài liệu “Dự thảo Nghị quyết phân bổ ngân sách 2026” đã được xử lý xong.', time: 'Hôm qua · 16:40' },
  { t: 'Kỳ họp thứ 12 sẽ diễn ra sau 1 ngày.', time: '2 ngày trước', read: true }
];

function renderNotif() {
    const p = document.getElementById('notifPanel');
    p.innerHTML = `<div class="np-head">Thông báo</div>` + MOCK_NOTIFS.map(n => `
      <div class="np-item ${n.read ? 'read' : ''}"><span class="np-dot"></span>
        <div><div class="np-t">${n.t}</div><div class="np-time">${n.time}</div></div>
      </div>`).join('');
}

function toggleNotif() {
    const p = document.getElementById('notifPanel');
    const show = !p.classList.contains('show');
    p.classList.toggle('show', show);
    if (show) {
      document.getElementById('notifBadge').classList.add('hide');
      MOCK_NOTIFS.forEach(n => n.read = true);
      renderNotif();
      if (!reduce) gsap.from('.notif-panel .np-item', { y: 6, autoAlpha: 0, stagger: 0.05, duration: 0.3 });
    }
}

// Close panels when clicking outside
document.addEventListener('click', e => {
    if (!e.target.closest('.topsearch')) {
        const res = document.getElementById('tsResults');
        if (res) res.classList.remove('show');
    }
    if (!e.target.closest('.notif-btn') && !e.target.closest('.notif-panel')) {
        const notif = document.getElementById('notifPanel');
        if (notif) notif.classList.remove('show');
    }
    if (e.target.id === 'uploadModal') closeUpload();
    if (e.target.id === 'confirmModal') closeConfirm();
});

document.addEventListener('keydown', e => {
    if (e.key !== 'Escape') return;
    if (document.getElementById('confirmModal').classList.contains('show')) closeConfirm();
    else if (document.getElementById('uploadModal').classList.contains('show')) closeUpload();
});

// ---------------- PANEL TABS SWITCHER ----------------
function showTab(t) {
    document.querySelectorAll('.tab').forEach(el => el.classList.toggle('on', el.dataset.tab === t));
    ['sum', 'term', 'q', 'qa'].forEach(p => {
      const el = document.getElementById('pane-' + p);
      if (el) {
          const active = p === t;
          el.classList.toggle('on', active);
          el.style.display = active ? 'block' : 'none';
      }
    });
    
    document.getElementById('inbar').style.display = (t === 'qa') ? 'flex' : 'none';
    moveUnderline();
    
    const paneMap = { sum: '#summaryBody .sec', term: '#termList .term-item', q: '#pane-q .q', qa: '#thread > *' };
    if (!reduce) animateStagger(paneMap[t]);
}

function moveUnderline() {
    const on = document.querySelector('.tab.on');
    const u = document.getElementById('tabUnderline');
    if (!on || !u) return;
    const target = { x: on.offsetLeft, width: on.offsetWidth };
    if (reduce) { gsap.set(u, { left: target.x, width: target.width }); return; }
    gsap.to(u, { left: target.x, width: target.width, duration: 0.35, ease: 'power3.out' });
}

function animateStagger(sel) {
    if (reduce) return;
    gsap.from(sel, { y: 10, autoAlpha: 0, duration: 0.4, stagger: 0.06, ease: 'power2.out', clearProps: 'all' });
}

// ---------------- GENERAL SETTINGS ----------------
function setFont(dir) {
    if (dir === 0) fsIdx = 1;
    else fsIdx = Math.max(0, Math.min(FS_STEPS.length - 1, fsIdx + dir));
    
    const doc = document.querySelector('.doc');
    if (doc) {
        doc.style.setProperty('--fs', FS_STEPS[fsIdx]);
        
        // Highlight active font size button
        document.querySelectorAll('.fs-btn').forEach((b, i) => {
            b.classList.toggle('on', i === 1 && fsIdx === 1); // standard
        });
        
        if (!reduce) gsap.fromTo(doc, { scale: 0.996 }, { scale: 1, duration: 0.25, ease: 'power2.out' });
    }
}

function countUp(el) {
    const target = +el.getAttribute('data-count');
    if (isNaN(target)) return;
    const o = { v: 0 };
    gsap.to(o, { v: target, duration: 1.1, ease: 'power1.out', onUpdate: () => el.textContent = Math.round(o.v) });
}

// Render term hover tooltips
const tip = document.getElementById('tip');
document.addEventListener('mouseover', e => {
    const t = e.target.closest('.term');
    if (t && t.getAttribute('data-def')) {
        tip.innerHTML = '<b>' + t.textContent + '</b>' + t.getAttribute('data-def');
        tip.classList.add('show');
        if (!reduce) gsap.fromTo(tip, { y: 4 }, { y: 0, duration: 0.2 });
    }
});

document.addEventListener('mousemove', e => {
    if (tip && tip.classList.contains('show')) {
        let x = e.clientX + 14, y = e.clientY + 16;
        if (x + 290 > window.innerWidth) x = e.clientX - 290;
        tip.style.left = x + 'px'; tip.style.top = y + 'px';
    }
});

document.addEventListener('mouseout', e => {
    if (tip && e.target.closest('.term')) tip.classList.remove('show');
});

// ---------------- SPEECH RECOGNITION (STT) ----------------
let recognition = null;
let isRecording = false;

function initSpeechRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        const mic = document.getElementById('mic-btn');
        if (mic) mic.style.display = 'none';
        return;
    }
    
    try {
        recognition = new SpeechRecognition();
        recognition.continuous = false;
        recognition.lang = 'vi-VN';
        recognition.interimResults = false;
        
        recognition.onstart = () => {
            isRecording = true;
            const mic = document.getElementById('mic-btn');
            if (mic) {
                mic.classList.add('recording');
                mic.title = "Đang lắng nghe... Bấm để dừng";
            }
        };
        
        recognition.onend = () => {
            isRecording = false;
            const mic = document.getElementById('mic-btn');
            if (mic) {
                mic.classList.remove('recording');
                mic.title = "Nói tiếng Việt (Speech-to-Text)";
            }
        };
        
        recognition.onresult = (event) => {
            const transcript = event.results[0][0].transcript;
            const inp = document.getElementById('qaInput');
            if (transcript && inp) {
                const oldVal = inp.value;
                inp.value = oldVal ? (oldVal + ' ' + transcript) : transcript;
            }
        };
        
        recognition.onerror = (e) => {
            console.error('Lỗi SpeechRecognition:', e.error);
        };
        
    } catch (e) {
        console.error('Không thể khởi tạo SpeechRecognition:', e);
    }
}

function toggleVoiceInput() {
    if (!recognition) return;
    if (isRecording) {
        recognition.stop();
    } else {
        recognition.start();
    }
}

// ---------------- GSAP INTRO ANIMATION ----------------
function animateIntro() {
    renderNotif();
    
    gsap.registerPlugin(ScrollTrigger);
    gsap.defaults({ duration: 0.5, ease: 'power2.out' });
    
    window.addEventListener('load', () => {
        const mm = gsap.matchMedia();
        mm.add({ motion: '(prefers-reduced-motion: no-preference)' }, () => {
            reduce = false;
            
            // Trong dong watermark infinite rotation
            gsap.to('#trongdong', { rotation: 360, duration: 240, repeat: -1, ease: 'none', transformOrigin: '50% 50%' });
            
            // Element sequences animations
            const tl = gsap.timeline();
            tl.from('.brand', { x: -16, autoAlpha: 0, duration: 0.5, clearProps: 'all' })
              .from('.upload-btn', { y: -8, autoAlpha: 0, duration: 0.4, clearProps: 'all' }, '-=.25')
              .from('.rail-lbl, .meet', { x: -14, autoAlpha: 0, stagger: 0.06, duration: 0.4, clearProps: 'all' }, '-=.2')
              .from('.meeting-card', { y: 14, autoAlpha: 0, duration: 0.45, ease: 'back.out(1.5)', clearProps: 'all' }, '-=.2')
              .from('.doc-title .badge', { scale: 0.4, autoAlpha: 0, duration: 0.5, ease: 'back.out(2)' }, '-=.4')
              .from('.doc-title', { x: -10, autoAlpha: 0, duration: 0.4 }, '-=.3')
              .from('.filter', { autoAlpha: 0, duration: 0.4 }, '-=.3')
              .from('.tabs .tab', { y: -10, autoAlpha: 0, stagger: 0.05, duration: 0.35 }, '-=.2');
              
            gsap.from('#pane-sum .tier', { y: 8, stagger: 0.06, duration: 0.4, delay: 0.5, ease: 'back.out(1.7)', clearProps: 'all' });
            
            document.querySelectorAll('[data-count]').forEach(countUp);
            return () => {};
        });
        
        mm.add({ reduced: '(prefers-reduced-motion: reduce)' }, () => {
            reduce = true;
            document.querySelectorAll('[data-count]').forEach(el => el.textContent = el.getAttribute('data-count'));
            return () => {};
        });
    });
}

// ---------------- WATERMARK SVG ALGORITHM ----------------
function buildTrongDong() {
    const C = 200, NS = 'http://www.w3.org/2000/svg';
    const svg = document.getElementById('trongdong');
    if (!svg) return;
    
    const stroke = 'rgba(255,255,255,0.055)';
    const strokeStrong = 'rgba(255,255,255,0.085)';
    const fill = 'rgba(255,255,255,0.045)';
    const el = (n, a) => {
        const e = document.createElementNS(NS, n);
        for (const k in a) e.setAttribute(k, a[k]);
        return e;
    };
    const pt = (r, deg) => [C + r * Math.cos(deg * Math.PI / 180), C + r * Math.sin(deg * Math.PI / 180)];
    
    // Sun rays in center
    const rays = 14, rOut = 34, rIn = 13;
    let d = '';
    for (let i = 0; i < rays; i++) {
        const a0 = (360 / rays) * i - 90;
        const a1 = a0 + (360 / rays) / 2;
        const a2 = a0 + (360 / rays);
        const [x0, y0] = pt(rOut, a0);
        const [x1, y1] = pt(rIn, a1);
        const [x2, y2] = pt(rOut, a2);
        d += (i === 0 ? `M${x0} ${y0} ` : `L${x0} ${y0} `) + `L${x1} ${y1} L${x2} ${y2} `;
    }
    d += 'Z';
    svg.appendChild(el('path', { d, fill, stroke: strokeStrong, 'stroke-width': 1 }));
    svg.appendChild(el('circle', { cx: C, cy: C, r: 8, fill: 'rgba(255,205,0,0.14)' }));
    
    // Rings
    [46, 58, 92, 104, 150, 164, 196].forEach((r, i) => {
        svg.appendChild(el('circle', { cx: C, cy: C, r, fill: 'none', stroke: (i % 2 ? strokeStrong : stroke), 'stroke-width': 1 }));
    });
    
    // Dots band
    const dotR = 75, dots = 36;
    for (let i = 0; i < dots; i++) {
        const [x, y] = pt(dotR, (360 / dots) * i);
        svg.appendChild(el('circle', { cx: x, cy: y, r: 2, fill: 'rgba(255,205,0,0.12)' }));
    }
    
    // Bird silhouettes Lạc band
    const birdR = 127, birds = 18;
    for (let i = 0; i < birds; i++) {
        const a = (360 / birds) * i;
        const [bx, by] = pt(birdR, a);
        const g = el('g', { transform: `translate(${bx} ${by}) rotate(${a + 90})` });
        g.appendChild(el('path', { d: 'M0 -6 L5 6 L0 3 L-5 6 Z', fill: 'rgba(255,205,0,0.10)' }));
        svg.appendChild(g);
    }
    
    // Spikes outer rim
    const spikes = 48;
    let sd = '';
    for (let i = 0; i < spikes; i++) {
        const a0 = (360 / spikes) * i;
        const a1 = a0 + (360 / spikes) / 2;
        const [x0, y0] = pt(196, a0);
        const [x1, y1] = pt(168, a1);
        sd += (i === 0 ? `M${x0} ${y0} ` : `L${x0} ${y0} `) + `L${x1} ${y1} `;
    }
    sd += 'Z';
    svg.appendChild(el('path', { d: sd, fill: 'none', stroke, 'stroke-width': 1 }));
}

/* ---------- Đăng nhập / Đăng xuất ---------- */
function initLoginAnimation() {
    if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        gsap.to('#trongdongLogin', { rotation: 360, duration: 300, repeat: -1, ease: 'none', transformOrigin: '50% 50%' });
        gsap.from('.login-card', { y: 24, autoAlpha: 0, scale: .97, duration: .6, ease: 'back.out(1.4)' });
        gsap.from('.login-card > *', { y: 12, autoAlpha: 0, stagger: .06, duration: .4, delay: .15, clearProps: 'all' });
    }
}
function togglePass() {
    const p = document.getElementById('loginKey');
    p.type = p.type === 'password' ? 'text' : 'password';
}
function doLogout() {
    localStorage.removeItem('gov_user');
    localStorage.removeItem('gov_dept');
    
    document.getElementById('loginKey').value = '';
    document.getElementById('loginErr').textContent = '';
    document.body.classList.remove('authed');
    const scr = document.getElementById('loginScreen');
    if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        gsap.fromTo(scr, { autoAlpha: 0 }, { autoAlpha: 1, duration: .4, ease: 'power2.out' });
        gsap.fromTo('.login-card', { y: 20, scale: .97, autoAlpha: 0 }, { y: 0, scale: 1, autoAlpha: 1, duration: .5, ease: 'back.out(1.4)' });
    } else {
        scr.style.display = 'flex';
    }
}
function doLogin(ev) {
    ev.preventDefault();
    const user = document.getElementById('loginUser').value.trim();
    const dept = document.getElementById('loginDept').value;
    const key = document.getElementById('loginKey').value;
    const err = document.getElementById('loginErr');
    if (!user) { err.textContent = 'Vui lòng nhập tên đăng nhập.'; return; }
    if (!dept) { err.textContent = 'Vui lòng chọn phòng ban.'; return; }
    if (!key) { err.textContent = 'Vui lòng nhập khóa đăng nhập.'; return; }
    err.textContent = '';
    
    // Save to localStorage if "Ghi nhớ phòng ban" is checked
    const remember = document.getElementById('loginRemember').checked;
    if (remember) {
        localStorage.setItem('gov_user', user);
        localStorage.setItem('gov_dept', dept);
    } else {
        localStorage.removeItem('gov_user');
        localStorage.removeItem('gov_dept');
    }
    
    const welcomeEl = document.getElementById('welcomeName');
    if (welcomeEl) welcomeEl.textContent = user;
    
    const scr = document.getElementById('loginScreen');
    const reduceNow = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduceNow) { 
        document.body.classList.add('authed'); 
        animateIntro();
        return; 
    }
    gsap.to(scr, { autoAlpha: 0, duration: 0.45, ease: 'power2.inOut', onComplete: () => {
        document.body.classList.add('authed');
        gsap.set(scr, { clearProps: 'all' });
        animateIntro();
    }});
}

// Register global callback functions for HTML calls
window.openUpload = openUpload;
window.closeUpload = closeUpload;
window.pickFolder = pickFolder;
window.showNewFolder = showNewFolder;
window.cancelNewFolder = cancelNewFolder;
window.confirmNewFolder = confirmNewFolder;
window.onPickFiles = onPickFiles;
window.removeFile = removeFile;
window.confirmUpload = confirmUpload;
window.closeConfirm = closeConfirm;
window.doDelDoc = doDelDoc;
window.toggleMeet = toggleMeet;
window.selectDoc = selectDoc;
window.askDelDoc = askDelDoc;
window.askDelMeet = askDelMeet;
window.setFont = setFont;
window.showTab = showTab;
window.setTier = setTier;
window.filterTerms = filterTerms;
window.applyFilter = applyFilter;
window.globalSearch = globalSearch;
window.openDocFromSearch = openDocFromSearch;
window.toggleNotif = toggleNotif;
window.scrollTophysPage = scrollTophysPage;
window.askDeep = askDeep;
window.sendQ = sendQ;
window.toggleVoiceInput = toggleVoiceInput;
window.togglePass = togglePass;
window.doLogin = doLogin;
window.doLogout = doLogout;
