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
        showToast(`지원하지 않는 파일 형식이 제외됐어요: ${invalid.map(f => f.name).join(', ')} (지원: MP3, WAV, M4A, OGG, FLAC, AAC)`, { type: 'error', duration: 7000 });
    }
    const valid = incoming.filter(f => !invalid.includes(f));
    if (!valid.length) return;

    // 기존 선택과 합치되 (이름+크기) 기준 중복 제거
    const keyOf = f => `${f.name}::${f.size}`;
    const existingKeys = new Set(selectedFiles.map(keyOf));
    for (const f of valid) {
        if (!existingKeys.has(keyOf(f))) {
            selectedFiles.push(f);
            fileMetas.push({ meetingTitle: '', attendees: '', projectId: '', newProjectName: '' });
            existingKeys.add(keyOf(f));
        }
    }

    // 합치기 모드는 최대 10개 (백엔드와 동기화)
    if (selectedFiles.length > 10) {
        showToast('한 번에 처리 가능한 파일은 최대 10개입니다.', { type: 'error' });
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
        if (uploadArea) {
            uploadArea.style.display = 'block';
            uploadArea.classList.remove('has-files');
        }
        return;
    }

    // 파일이 선택되면 드롭존은 "추가용" 콤팩트 모드로 축소
    if (uploadArea) {
        uploadArea.style.display = 'block';
        uploadArea.classList.add('has-files');
    }
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
        const meta = fileMetas[idx] || { meetingTitle: '', attendees: '', projectId: '', newProjectName: '' };

        li.innerHTML = `
            <div class="file-info-item-row">
                <div class="file-info-item-meta">
                    ${mergeOn ? `<span class="file-info-item-drag" title="드래그해서 순서 변경" aria-label="순서 변경 핸들">
                        <svg width="14" height="14" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                            <circle cx="7" cy="5" r="1.5"/><circle cx="13" cy="5" r="1.5"/>
                            <circle cx="7" cy="10" r="1.5"/><circle cx="13" cy="10" r="1.5"/>
                            <circle cx="7" cy="15" r="1.5"/><circle cx="13" cy="15" r="1.5"/>
                        </svg>
                    </span>` : ''}
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
                <div class="file-info-item-meta-field">
                    <label>프로젝트</label>
                    <select class="select-input js-file-project"></select>
                    <input type="text" class="text-input js-file-new-project" placeholder="새 프로젝트 이름" style="display: none;">
                </div>
            </div>
            <p class="merge-secondary-notice">합치기 모드 — 첫 번째 파일의 회의 정보·프로젝트가 사용됩니다</p>
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

        // 프로젝트 선택 (파일마다 다른 프로젝트 가능)
        const projSelect = li.querySelector('.js-file-project');
        const newProjInput = li.querySelector('.js-file-new-project');
        fillFileProjectOptions(projSelect, meta.projectId);
        newProjInput.value = meta.newProjectName || '';
        newProjInput.style.display = meta.projectId === '__new__' ? 'block' : 'none';
        projSelect.addEventListener('change', (e) => {
            if (fileMetas[idx]) fileMetas[idx].projectId = e.target.value;
            const isNew = e.target.value === '__new__';
            newProjInput.style.display = isNew ? 'block' : 'none';
            if (isNew) newProjInput.focus();
            // 프로젝트가 바뀌면 참석자 추천 캐시 무효화
            attendeeSuggestionCache = [];
            attendeeSuggestionProjectId = undefined;
        });
        newProjInput.addEventListener('input', (e) => {
            if (fileMetas[idx]) fileMetas[idx].newProjectName = e.target.value;
        });

        // 합치기 모드에서만 드래그 정렬 활성화 (순서가 곧 회의 진행 순서)
        if (mergeOn) bindFileDrag(li, idx);

        itemsEl.appendChild(li);
    });

    // 순서 변경 안내: 합치기 모드일 때만 표시
    const hintEl = document.getElementById('mergeOrderHint');
    if (hintEl) hintEl.hidden = !mergeOn;

    // 합치기 토글: 2개 이상일 때만 의미 있음
    if (mergeToggle) {
        const parent = mergeToggle.closest('.merge-toggle');
        if (parent) parent.style.display = selectedFiles.length >= 2 ? 'grid' : 'none';
        if (selectedFiles.length < 2) mergeToggle.checked = false;
    }
}

// ============================================
// 합치기 순서 드래그 정렬
// ============================================

let dragSrcIndex = null;   // 현재 드래그 중인 파일의 인덱스

// 한 파일 카드에 드래그 정렬 동작을 연결.
// 핸들(⠿)에서 mousedown해야만 li가 draggable이 되어, 카드 내 입력 필드와 충돌하지 않는다.
function bindFileDrag(li, idx) {
    const handle = li.querySelector('.file-info-item-drag');
    if (!handle) return;
    handle.style.cursor = 'grab';

    handle.addEventListener('mousedown', () => li.setAttribute('draggable', 'true'));
    handle.addEventListener('mouseup', () => li.removeAttribute('draggable'));

    li.addEventListener('dragstart', (e) => {
        dragSrcIndex = idx;
        li.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
        // 일부 브라우저는 데이터가 있어야 drop을 허용함
        try { e.dataTransfer.setData('text/plain', String(idx)); } catch (_) {}
    });

    li.addEventListener('dragend', () => {
        li.removeAttribute('draggable');
        li.classList.remove('dragging');
        clearDropIndicators();
        dragSrcIndex = null;
    });

    li.addEventListener('dragover', (e) => {
        if (dragSrcIndex === null || dragSrcIndex === idx) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        // 마우스가 카드 상/하 절반 중 어디인지로 삽입 위치 표시
        const rect = li.getBoundingClientRect();
        const after = e.clientY > rect.top + rect.height / 2;
        clearDropIndicators();
        li.classList.add(after ? 'drag-over-after' : 'drag-over-before');
    });

    li.addEventListener('dragleave', () => {
        li.classList.remove('drag-over-before', 'drag-over-after');
    });

    li.addEventListener('drop', (e) => {
        e.preventDefault();
        if (dragSrcIndex === null || dragSrcIndex === idx) return;
        const rect = li.getBoundingClientRect();
        const after = e.clientY > rect.top + rect.height / 2;
        let target = after ? idx + 1 : idx;
        // 위쪽 항목을 제거하면 타겟 인덱스가 한 칸 당겨짐
        if (dragSrcIndex < target) target -= 1;
        reorderFiles(dragSrcIndex, target);
    });
}

function clearDropIndicators() {
    document.querySelectorAll('.file-info-item.drag-over-before, .file-info-item.drag-over-after')
        .forEach(el => el.classList.remove('drag-over-before', 'drag-over-after'));
}

// 세 병렬 배열(selectedFiles / audioDurations / fileMetas)을 동시에 같은 순서로 재배치
function reorderFiles(from, to) {
    if (from === to || from < 0 || to < 0) return;
    const move = (arr) => { const [v] = arr.splice(from, 1); arr.splice(to, 0, v); };
    move(selectedFiles);
    move(audioDurations);
    move(fileMetas);
    renderFileList();
}

// 파일 카드의 프로젝트 select 옵션 채우기 (projectsCache 기반)
function fillFileProjectOptions(select, selectedValue) {
    if (!select) return;
    select.innerHTML = '';
    const noneOpt = document.createElement('option');
    noneOpt.value = '';
    noneOpt.textContent = '— 프로젝트 없음 —';
    select.appendChild(noneOpt);
    (projectsCache || []).forEach(p => {
        const opt = document.createElement('option');
        opt.value = String(p.id);
        opt.textContent = p.name;
        select.appendChild(opt);
    });
    const newOpt = document.createElement('option');
    newOpt.value = '__new__';
    newOpt.textContent = '+ 새 프로젝트 만들기...';
    select.appendChild(newOpt);
    select.value = selectedValue || '';
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
    if (uploadArea) {
        uploadArea.style.display = 'block';
        uploadArea.classList.remove('has-files');
    }
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
    // 포커스된 참석자 입력이 속한 파일 카드의 프로젝트 기준
    const sel = activeAttendeeInput?.closest('.file-info-item')?.querySelector('.js-file-project');
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
