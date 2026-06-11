// ============================================
// upload.js — 파일 선택/검증/리스트 렌더 + 참석자 자동완성
// ============================================

// 드래그 앤 드롭 핸들러
function handleDragOver(e) {
    e.preventDefault();
    uploadArea.classList.add('drag-over');
}

function handleDragLeave(e) {
    e.preventDefault();
    uploadArea.classList.remove('drag-over');
}

function handleDrop(e) {
    e.preventDefault();
    uploadArea.classList.remove('drag-over');

    const files = e.dataTransfer.files;
    if (files.length > 0) {
        handleFiles(files);
    }
}

// 파일 선택 핸들러 (multiple 지원)
function handleFileSelect(e) {
    const files = e.target.files;
    if (files.length > 0) {
        handleFiles(files);
    }
}

// 다중 파일 처리: 검증 + 길이 측정 + UI 반영
async function handleFiles(fileList) {
    const allowedExtensions = ['.mp3', '.wav', '.m4a', '.ogg', '.flac', '.aac'];
    const incoming = Array.from(fileList);

    // 확장자 검증
    const invalid = incoming.filter(f => {
        const ext = '.' + f.name.split('.').pop().toLowerCase();
        return !allowedExtensions.includes(ext);
    });
    if (invalid.length) {
        alert(`지원하지 않는 파일 형식입니다.\n지원 형식: MP3, WAV, M4A, OGG, FLAC, AAC\n\n제외: ${invalid.map(f => f.name).join(', ')}`);
    }
    const valid = incoming.filter(f => !invalid.includes(f));
    if (!valid.length) return;

    // 기존 선택과 합치되 (이름+크기) 기준 중복 제거
    const keyOf = f => `${f.name}::${f.size}`;
    const existingKeys = new Set(selectedFiles.map(keyOf));
    for (const f of valid) {
        if (!existingKeys.has(keyOf(f))) {
            selectedFiles.push(f);
            fileMetas.push({ meetingTitle: '', attendees: '' });
            existingKeys.add(keyOf(f));
        }
    }

    // 합치기 모드는 최대 10개 (백엔드와 동기화)
    if (selectedFiles.length > 10) {
        alert('한 번에 처리 가능한 파일은 최대 10개입니다.');
        selectedFiles = selectedFiles.slice(0, 10);
        fileMetas = fileMetas.slice(0, 10);
    }

    // 각 파일 audio_duration 측정 (병렬). 실패 시 0.
    audioDurations = await Promise.all(
        selectedFiles.map(f => getAudioDuration(f).catch(() => 0))
    );

    renderFileList();
    if (convertBtn) convertBtn.disabled = selectedFiles.length === 0;
}

function renderFileList() {
    const listEl = document.getElementById('fileInfoList');
    const itemsEl = document.getElementById('fileInfoItems');
    const countEl = document.getElementById('fileInfoCount');
    const mergeToggle = document.getElementById('mergeFilesCheckbox');
    if (!listEl || !itemsEl || !countEl) return;

    if (selectedFiles.length === 0) {
        listEl.style.display = 'none';
        if (uploadArea) uploadArea.style.display = 'block';
        return;
    }

    if (uploadArea) uploadArea.style.display = 'block';
    listEl.style.display = 'block';
    countEl.textContent = String(selectedFiles.length);
    itemsEl.innerHTML = '';

    const mergeOn = !!(mergeToggle?.checked) && selectedFiles.length >= 2;

    selectedFiles.forEach((file, idx) => {
        const li = document.createElement('li');
        li.className = 'file-info-item';
        if (mergeOn) {
            li.classList.add(idx === 0 ? 'is-merge-primary' : 'is-merge-secondary');
        }

        const dur = audioDurations[idx] || 0;
        const sizeText = dur > 0
            ? `${formatFileSize(file.size)} · ${Math.floor(dur / 60)}분 ${Math.round(dur % 60)}초`
            : formatFileSize(file.size);
        const meta = fileMetas[idx] || { meetingTitle: '', attendees: '' };

        li.innerHTML = `
            <div class="file-info-item-row">
                <div class="file-info-item-meta">
                    <span class="file-info-item-order">${idx + 1}</span>
                    <span class="file-info-item-name"></span>
                    <span class="file-info-item-size"></span>
                </div>
                <button type="button" class="file-info-item-remove" title="이 파일 제거" aria-label="제거">
                    <svg width="14" height="14" viewBox="0 0 20 20" fill="none">
                        <path d="M15 5L5 15M5 5L15 15" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                    </svg>
                </button>
            </div>
            <div class="file-info-item-meta-inputs">
                <div class="file-info-item-meta-field">
                    <label>회의 제목</label>
                    <input type="text" class="text-input js-file-title" placeholder="예: 주간 팀 미팅">
                </div>
                <div class="file-info-item-meta-field">
                    <label>참석자</label>
                    <input type="text" class="text-input js-file-attendees" placeholder="홍길동, 김철수" autocomplete="off">
                    <div class="attendee-suggestions" hidden></div>
                </div>
            </div>
            <p class="merge-secondary-notice">합치기 모드 — 첫 번째 파일의 회의 정보가 사용됩니다</p>
        `;
        li.querySelector('.file-info-item-name').textContent = file.name;
        li.querySelector('.file-info-item-size').textContent = sizeText;
        li.querySelector('.file-info-item-remove').addEventListener('click', () => removeFileAt(idx));

        const titleInput = li.querySelector('.js-file-title');
        const attInput = li.querySelector('.js-file-attendees');
        titleInput.value = meta.meetingTitle;
        attInput.value = meta.attendees;
        titleInput.addEventListener('input', (e) => {
            if (fileMetas[idx]) fileMetas[idx].meetingTitle = e.target.value;
        });
        attInput.addEventListener('input', (e) => {
            if (fileMetas[idx]) fileMetas[idx].attendees = e.target.value;
        });
        // 참석자 자동완성 바인딩
        const chipsEl = li.querySelector('.attendee-suggestions');
        bindAttendeeAutocomplete(attInput, chipsEl);

        itemsEl.appendChild(li);
    });

    // 합치기 토글: 2개 이상일 때만 의미 있음
    if (mergeToggle) {
        const parent = mergeToggle.closest('.merge-toggle');
        if (parent) parent.style.display = selectedFiles.length >= 2 ? 'grid' : 'none';
        if (selectedFiles.length < 2) mergeToggle.checked = false;
    }
}

function removeFileAt(idx) {
    selectedFiles.splice(idx, 1);
    audioDurations.splice(idx, 1);
    fileMetas.splice(idx, 1);
    renderFileList();
    if (convertBtn) convertBtn.disabled = selectedFiles.length === 0;
}

function clearFile() {
    selectedFiles = [];
    audioDurations = [];
    fileMetas = [];
    if (fileInput) fileInput.value = '';
    if (uploadArea) uploadArea.style.display = 'block';
    const listEl = document.getElementById('fileInfoList');
    if (listEl) listEl.style.display = 'none';
    if (convertBtn) convertBtn.disabled = true;
    const mergeToggle = document.getElementById('mergeFilesCheckbox');
    if (mergeToggle) mergeToggle.checked = false;
}

// ============================================
// 참석자 자동완성 (최근 사용 + 칩)
// ============================================

let attendeeSuggestionCache = [];      // 최근 사용 참석자 (서버에서 받아온 전체 목록)
let attendeeSuggestionProjectId = null; // 캐시가 어떤 project_id 기준인지
let attendeeFetchAbort = null;
const ATTENDEE_CHIP_LIMIT = 8;

// 자동완성 활성 input (포커스된 attendee input 추적)
let activeAttendeeInput = null;

function initAttendeeAutocomplete() {
    // 프로젝트 변경 시 캐시 무효화 + 활성 input에 대해 재렌더
    const projectSelect = document.getElementById('projectSelect');
    if (projectSelect) {
        projectSelect.addEventListener('change', () => {
            attendeeSuggestionCache = [];
            attendeeSuggestionProjectId = null;
            loadRecentAttendees().then(() => renderAttendeeChips(activeAttendeeInput));
        });
    }

    // 페이지 진입 직후 한 번 미리 로드 (캐시 워밍)
    loadRecentAttendees();
}

// 임의 attendee input과 그 옆 칩 컨테이너에 자동완성 바인딩
function bindAttendeeAutocomplete(input, container) {
    if (!input || !container) return;
    input.dataset.attendeeBound = '1';

    input.addEventListener('input', () => renderAttendeeChips(input));
    input.addEventListener('focus', () => {
        activeAttendeeInput = input;
        loadRecentAttendees().then(() => renderAttendeeChips(input));
    });
    input.addEventListener('blur', () => {
        // blur 직후 칩 클릭이 처리될 수 있도록 살짝 지연
        setTimeout(() => {
            if (activeAttendeeInput === input) activeAttendeeInput = null;
            container.hidden = true;
            container.innerHTML = '';
        }, 150);
    });
}

function getCurrentProjectIdForAttendees() {
    const sel = document.getElementById('projectSelect');
    if (!sel) return null;
    const val = sel.value;
    if (!val || val === '__new__') return null;
    const n = parseInt(val, 10);
    return Number.isFinite(n) ? n : null;
}

async function loadRecentAttendees() {
    const projectId = getCurrentProjectIdForAttendees();

    // 같은 프로젝트 컨텍스트면 캐시 재사용
    if (attendeeSuggestionCache.length && attendeeSuggestionProjectId === projectId) {
        return attendeeSuggestionCache;
    }

    try {
        if (attendeeFetchAbort) attendeeFetchAbort.abort();
        attendeeFetchAbort = new AbortController();

        const params = new URLSearchParams();
        if (projectId !== null) params.set('project_id', String(projectId));
        params.set('limit', '50');

        const res = await authFetch(
            `${API_BASE_URL}/me/recent-attendees?${params.toString()}`,
            { signal: attendeeFetchAbort.signal }
        );
        if (!res.ok) return [];
        const data = await res.json();
        attendeeSuggestionCache = Array.isArray(data.attendees) ? data.attendees : [];
        attendeeSuggestionProjectId = projectId;
        return attendeeSuggestionCache;
    } catch (err) {
        if (err.name !== 'AbortError') console.warn('최근 참석자 로드 실패:', err);
        return [];
    }
}

function parseAttendeeInput(value) {
    return (value || '')
        .split(/[,;/\n]/)
        .map(s => s.trim())
        .filter(Boolean);
}

function getCurrentTypingFragment(value) {
    // 마지막 콤마 뒤 부분 = 사용자가 지금 타이핑 중인 토큰
    const idx = Math.max(value.lastIndexOf(','), value.lastIndexOf(';'), value.lastIndexOf('/'));
    return value.slice(idx + 1).trim();
}

function renderAttendeeChips(input) {
    if (!input) return;
    // input 옆 .attendee-suggestions 컨테이너 (마크업 규약)
    const container = input.parentElement?.querySelector('.attendee-suggestions');
    if (!container) return;

    const rawValue = input.value;
    const alreadyAdded = new Set(
        parseAttendeeInput(rawValue).map(n => n.toLowerCase())
    );
    const typing = getCurrentTypingFragment(rawValue).toLowerCase();

    let matches = attendeeSuggestionCache;
    if (typing) {
        matches = matches.filter(name => name.toLowerCase().includes(typing));
    }
    matches = matches.slice(0, ATTENDEE_CHIP_LIMIT);

    if (!matches.length) {
        container.hidden = true;
        container.innerHTML = '';
        return;
    }

    container.hidden = false;
    container.innerHTML = '';
    matches.forEach(name => {
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'attendee-chip';
        chip.textContent = name;
        if (alreadyAdded.has(name.toLowerCase())) {
            chip.classList.add('is-added');
        }
        // mousedown 사용 — blur보다 먼저 발생해서 input 값 갱신 가능
        chip.addEventListener('mousedown', (e) => {
            e.preventDefault();
            addAttendeeFromChip(input, name);
        });
        container.appendChild(chip);
    });
}

function addAttendeeFromChip(input, name) {
    if (!input) return;
    const existing = parseAttendeeInput(input.value);
    if (existing.some(n => n.toLowerCase() === name.toLowerCase())) return;
    input.value = [...existing, name].join(', ') + ', ';
    // 갱신 이벤트 발생 — 파일별 meta 동기화 트리거
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.focus();
    renderAttendeeChips(input);
}
