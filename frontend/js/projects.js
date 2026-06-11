// ============================================
// projects.js — 프로젝트 목록/상세/모달 + 컨텍스트 글로서리 편집
// ============================================

async function loadProjects() {
    const statusEl = document.getElementById('projectsStatus');
    const listEl = document.getElementById('projectsList');
    if (!listEl) return;

    statusEl.textContent = '불러오는 중...';
    listEl.innerHTML = '';

    try {
        const res = await authFetch(`${API_BASE_URL}/projects`);
        if (!res.ok) throw new Error('프로젝트 목록 조회 실패');
        const data = await res.json();
        projectsCache = data.projects || [];

        if (projectsCache.length === 0) {
            statusEl.textContent = '아직 프로젝트가 없습니다. "+ 새 프로젝트"로 만들어보세요.';
            return;
        }
        statusEl.textContent = `총 ${projectsCache.length}개`;

        projectsCache.forEach(p => {
            const item = document.createElement('div');
            item.className = 'dashboard-item is-project';

            const desc = p.description
                ? `<div class="dashboard-item-preview">${escapeHtml(p.description)}</div>`
                : '';
            const dateStr = p.updated_at ? formatDateKo(p.updated_at) : '';

            item.innerHTML = `
                <div class="dashboard-item-title">${escapeHtml(p.name)}</div>
                <div class="dashboard-item-meta">
                    <span class="meta-chip">회의록 ${p.summary_count}건</span>
                    <span class="meta-chip context-count">컨텍스트 ${p.context_count}개</span>
                    ${dateStr ? `<span class="meta-chip">${dateStr}</span>` : ''}
                </div>
                ${desc}
            `;
            item.addEventListener('click', () => openProjectDetail(p.id));
            listEl.appendChild(item);
        });
    } catch (err) {
        console.error(err);
        statusEl.textContent = '프로젝트 목록을 불러오지 못했습니다: ' + err.message;
    }
}

async function openProjectDetail(projectId) {
    try {
        const res = await authFetch(`${API_BASE_URL}/projects/${projectId}`);
        if (!res.ok) throw new Error('프로젝트 조회 실패');
        const data = await res.json();
        currentProjectDetail = data;

        document.getElementById('projectDetailName').textContent = data.project.name;
        const descEl = document.getElementById('projectDetailDescription');
        descEl.textContent = data.project.description || '';
        descEl.style.display = data.project.description ? 'block' : 'none';

        renderProjectMeetings(data.summaries || []);
        renderContextList('project', data.contexts || []);
        renderProjectMemory(data.project);

        // 첫 탭(회의록)으로 초기화
        switchProjectTab('meetings');
        switchView('projectDetail');
    } catch (err) {
        console.error(err);
        showToast('프로젝트를 여는 데 실패했습니다: ' + err.message, { type: 'error' });
    }
}

function renderProjectMeetings(summaries) {
    const statusEl = document.getElementById('projectMeetingsStatus');
    const listEl = document.getElementById('projectMeetingsList');
    listEl.innerHTML = '';

    if (!summaries || summaries.length === 0) {
        statusEl.textContent = '아직 회의록이 없습니다.';
        return;
    }
    statusEl.textContent = `총 ${summaries.length}건`;

    summaries.forEach(rec => {
        const item = document.createElement('div');
        item.className = 'dashboard-item';

        const title = rec.meeting_title || rec.filename || `요약 #${rec.id}`;
        const dateStr = rec.created_at ? formatDateKo(rec.created_at) : '';
        const editedBadge = rec.is_edited
            ? `<span class="edited-badge">수정됨 v${rec.version_count}</span>`
            : '';
        const metaChips = [];
        if (rec.gpt_model) metaChips.push(`<span class="meta-chip">${escapeHtml(rec.gpt_model)}</span>`);
        if (dateStr) metaChips.push(`<span class="meta-chip">${dateStr}</span>`);

        item.innerHTML = `
            <div class="dashboard-item-title">${escapeHtml(title)} ${editedBadge}</div>
            <div class="dashboard-item-meta">${metaChips.join('')}</div>
            <div class="dashboard-item-preview">${escapeHtml(rec.summary_preview || '')}</div>
        `;
        item.addEventListener('click', () => openSummaryFromDashboard(rec.id));
        listEl.appendChild(item);
    });
}

function switchProjectTab(tabName) {
    document.querySelectorAll('[data-project-tab]').forEach(btn => {
        if (btn.dataset.projectTab === tabName) btn.classList.add('active');
        else btn.classList.remove('active');
    });
    const meetTab = document.getElementById('projectMeetingsTab');
    const ctxTab = document.getElementById('projectContextTab');
    const memTab = document.getElementById('projectMemoryTab');
    if (meetTab) meetTab.classList.toggle('active', tabName === 'meetings');
    if (ctxTab) ctxTab.classList.toggle('active', tabName === 'context');
    if (memTab) memTab.classList.toggle('active', tabName === 'memory');
}

// ============================================
// 프로젝트 AI 메모리 (회의가 쌓일수록 깊어지는 장기 기억)
// ============================================

function renderProjectMemory(project) {
    const textarea = document.getElementById('projectMemoryText');
    const statusEl = document.getElementById('projectMemoryStatus');
    if (!textarea) return;

    textarea.value = project.memory || '';
    if (statusEl) {
        if (project.memory && project.memory_updated_at) {
            statusEl.textContent = `마지막 갱신: ${formatDateKo(project.memory_updated_at)} — 회의록이 생성될 때마다 자동으로 갱신됩니다.`;
        } else if (project.memory) {
            statusEl.textContent = '회의록이 생성될 때마다 자동으로 갱신됩니다.';
        } else {
            statusEl.textContent = '아직 메모리가 없습니다. 이 프로젝트로 회의록을 만들면 AI가 자동으로 쌓기 시작해요.';
        }
    }
}

async function saveProjectMemory() {
    if (!currentProjectDetail) return;
    const textarea = document.getElementById('projectMemoryText');
    const saveBtn = document.getElementById('projectMemorySaveBtn');
    if (!textarea) return;

    if (saveBtn) { saveBtn.disabled = true; saveBtn.textContent = '저장 중...'; }
    try {
        const res = await authFetch(`${API_BASE_URL}/projects/${currentProjectDetail.project.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ memory: textarea.value }),
        });
        if (!res.ok) throw new Error('저장 실패');
        const data = await res.json();
        currentProjectDetail.project = data.project;
        renderProjectMemory(data.project);
        showToast('프로젝트 메모리를 저장했어요. 다음 회의록부터 반영됩니다.', { type: 'success' });
    } catch (err) {
        console.error(err);
        showToast('메모리 저장 중 오류: ' + err.message, { type: 'error' });
    } finally {
        if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = '저장'; }
    }
}

async function rebuildProjectMemory() {
    if (!currentProjectDetail) return;
    const p = currentProjectDetail.project;
    if (!confirm(`"${p.name}"의 모든 회의록을 시간순으로 다시 읽어 AI 메모리를 처음부터 재구축할까요?\n현재 메모리는 대체되며, 회의록 수에 따라 수 분 걸릴 수 있습니다.`)) return;

    const btn = document.getElementById('projectMemoryRebuildBtn');
    if (btn) { btn.disabled = true; btn.textContent = '재구축 중...'; }
    try {
        const res = await authFetch(`${API_BASE_URL}/projects/${p.id}/rebuild-memory`, { method: 'POST' });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || '재구축 요청 실패');
        }
        const data = await res.json();
        showToast(data.message + ' 끝나면 이 탭을 다시 열어 확인하세요.', { type: 'success', duration: 9000 });
    } catch (err) {
        console.error(err);
        showToast('메모리 재구축 중 오류: ' + err.message, { type: 'error' });
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = '↻ 전체 회의록으로 재구축'; }
    }
}

// ============================================
// 프로젝트 생성/편집/삭제 (모달)
// ============================================

function openProjectModal(mode, project) {
    projectModalMode = mode;
    projectModalTargetId = mode === 'edit' ? project.id : null;
    document.getElementById('projectModalTitle').textContent =
        mode === 'edit' ? '프로젝트 수정' : '새 프로젝트';
    document.getElementById('projectModalName').value = mode === 'edit' ? (project.name || '') : '';
    document.getElementById('projectModalDescription').value = mode === 'edit' ? (project.description || '') : '';
    document.getElementById('projectModal').style.display = 'flex';
    setTimeout(() => document.getElementById('projectModalName').focus(), 50);
}

function closeProjectModal() {
    document.getElementById('projectModal').style.display = 'none';
}

async function saveProjectModal() {
    const name = document.getElementById('projectModalName').value.trim();
    const description = document.getElementById('projectModalDescription').value.trim();
    if (!name) { showToast('프로젝트명을 입력해주세요.', { type: 'error' }); return; }

    try {
        let url = `${API_BASE_URL}/projects`;
        let method = 'POST';
        if (projectModalMode === 'edit' && projectModalTargetId) {
            url = `${API_BASE_URL}/projects/${projectModalTargetId}`;
            method = 'PUT';
        }
        const res = await authFetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, description }),
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || '저장 실패');
        }
        const data = await res.json();
        closeProjectModal();
        if (projectModalMode === 'edit') {
            await openProjectDetail(projectModalTargetId);
        } else {
            await loadProjects();
            // 새로 만든 프로젝트는 생성 폼 드롭다운에도 즉시 반영
            await populateProjectSelect(data.project.id);
        }
    } catch (err) {
        console.error(err);
        showToast('저장 중 오류: ' + err.message, { type: 'error' });
    }
}

async function deleteCurrentProject() {
    if (!currentProjectDetail) return;
    const p = currentProjectDetail.project;
    if (!confirm(`프로젝트 "${p.name}"을(를) 삭제할까요? 회의록은 유지되지만 프로젝트 연결이 해제됩니다.`)) return;
    try {
        const res = await authFetch(`${API_BASE_URL}/projects/${p.id}`, { method: 'DELETE' });
        if (!res.ok) throw new Error('삭제 실패');
        currentProjectDetail = null;
        switchView('projects');
    } catch (err) {
        console.error(err);
        showToast('삭제 중 오류: ' + err.message, { type: 'error' });
    }
}

// ============================================
// 생성 폼: 프로젝트 드롭다운
// ============================================

async function populateProjectSelect(selectedId = null) {
    const select = document.getElementById('projectSelect');
    if (!select) return;

    try {
        const res = await authFetch(`${API_BASE_URL}/projects`);
        if (!res.ok) return;
        const data = await res.json();
        const projects = data.projects || [];
        projectsCache = projects;

        // 기존 옵션 비우고 다시 채움
        select.innerHTML = '';
        const noneOpt = document.createElement('option');
        noneOpt.value = '';
        noneOpt.textContent = '— 프로젝트 없음 —';
        select.appendChild(noneOpt);

        projects.forEach(p => {
            const opt = document.createElement('option');
            opt.value = String(p.id);
            opt.textContent = p.name;
            select.appendChild(opt);
        });

        const newOpt = document.createElement('option');
        newOpt.value = '__new__';
        newOpt.textContent = '+ 새 프로젝트 만들기...';
        select.appendChild(newOpt);

        if (selectedId) {
            select.value = String(selectedId);
        }
    } catch (err) {
        console.warn('프로젝트 옵션 로드 실패:', err);
    }
}

function onProjectSelectChange() {
    const select = document.getElementById('projectSelect');
    const newInput = document.getElementById('projectName');
    if (!select || !newInput) return;

    if (select.value === '__new__') {
        newInput.style.display = 'block';
        newInput.focus();
    } else {
        newInput.style.display = 'none';
        newInput.value = '';
    }
}

// ============================================
// 컨텍스트 엔트리 편집 (개인/프로젝트 공통)
// ============================================

async function loadPersonalContext() {
    const statusEl = document.getElementById('personalContextStatus');
    const listEl = document.getElementById('personalContextList');
    if (!listEl) return;

    statusEl.textContent = '불러오는 중...';
    listEl.innerHTML = '';

    try {
        const res = await authFetch(`${API_BASE_URL}/contexts?scope=personal`);
        if (!res.ok) throw new Error('내 컨텍스트 조회 실패');
        const data = await res.json();
        const entries = data.entries || [];

        if (entries.length === 0) {
            statusEl.textContent = '아직 컨텍스트가 없습니다. 회의록을 수정하면 자동으로 추가되거나, 직접 추가할 수 있어요.';
        } else {
            statusEl.textContent = `총 ${entries.length}개`;
        }
        renderContextList('personal', entries);
    } catch (err) {
        console.error(err);
        statusEl.textContent = '컨텍스트를 불러오지 못했습니다: ' + err.message;
    }
}

function renderContextList(scope, entries) {
    const listEl = scope === 'project'
        ? document.getElementById('projectContextList')
        : document.getElementById('personalContextList');
    if (!listEl) return;
    listEl.innerHTML = '';

    const termEntries = entries.filter(e => (e.entry_type || 'term') === 'term');
    const styleEntries = entries.filter(e => e.entry_type === 'style');

    termEntries.forEach(e => {
        const row = document.createElement('div');
        row.className = 'context-row' + (e.source === 'auto' ? ' is-auto' : '');
        row.dataset.entryId = e.id;

        const sourceLabel = e.source === 'auto' ? '자동' : '직접';

        row.innerHTML = `
            <input type="text" class="text-input" data-field="term" value="${escapeAttr(e.term)}">
            <input type="text" class="text-input" data-field="correction" value="${escapeAttr(e.correction)}">
            <input type="text" class="text-input" data-field="note" value="${escapeAttr(e.note || '')}" placeholder="설명 (선택)">
            <div class="context-row-actions">
                <span class="context-source-badge">${sourceLabel}</span>
                <button class="btn-icon-mini" data-action="save" type="button">저장</button>
                <button class="btn-icon-mini danger" data-action="delete" type="button">삭제</button>
            </div>
        `;
        listEl.appendChild(row);
    });

    // 이벤트 바인딩 (저장 / 삭제)
    listEl.querySelectorAll('[data-action="save"]').forEach(btn => {
        btn.addEventListener('click', () => handleContextSave(scope, btn.closest('.context-row')));
    });
    listEl.querySelectorAll('[data-action="delete"]').forEach(btn => {
        btn.addEventListener('click', () => handleContextDelete(scope, btn.closest('.context-row')));
    });

    renderStyleRules(scope, styleEntries);
}

// AI가 수정 패턴에서 학습한 스타일 선호 목록
function renderStyleRules(scope, styleEntries) {
    const section = document.getElementById(scope === 'project' ? 'projectStyleSection' : 'personalStyleSection');
    const listEl = document.getElementById(scope === 'project' ? 'projectStyleList' : 'personalStyleList');
    if (!section || !listEl) return;

    listEl.innerHTML = '';
    if (!styleEntries.length) {
        section.hidden = true;
        return;
    }
    section.hidden = false;

    styleEntries.forEach(e => {
        const row = document.createElement('div');
        row.className = 'style-rule-row';
        row.dataset.entryId = e.id;
        row.innerHTML = `
            <div class="style-rule-body">
                <span class="style-rule-label"></span>
                <span class="style-rule-text"></span>
            </div>
            <button class="btn-icon-mini danger" data-action="delete-style" type="button" title="이 규칙 삭제">삭제</button>
        `;
        row.querySelector('.style-rule-label').textContent = e.term;
        row.querySelector('.style-rule-text').textContent = e.correction;
        row.querySelector('[data-action="delete-style"]').addEventListener('click', async () => {
            if (!confirm('이 스타일 규칙을 삭제할까요? 다음 회의록부터 적용되지 않습니다.')) return;
            try {
                const res = await authFetch(`${API_BASE_URL}/contexts/${e.id}`, { method: 'DELETE' });
                if (!res.ok) throw new Error('삭제 실패');
                row.remove();
                if (!listEl.children.length) section.hidden = true;
                showToast('스타일 규칙을 삭제했어요.', { type: 'success' });
            } catch (err) {
                console.error(err);
                showToast('삭제 중 오류: ' + err.message, { type: 'error' });
            }
        });
        listEl.appendChild(row);
    });
}

async function handleContextSave(scope, row) {
    const id = parseInt(row.dataset.entryId, 10);
    const term = row.querySelector('[data-field="term"]').value.trim();
    const correction = row.querySelector('[data-field="correction"]').value.trim();
    const note = row.querySelector('[data-field="note"]').value.trim();
    if (!term || !correction) {
        showToast('표기와 올바른 표기는 비울 수 없습니다.', { type: 'error' });
        return;
    }
    try {
        const res = await authFetch(`${API_BASE_URL}/contexts/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ term, correction, note }),
        });
        if (!res.ok) throw new Error('저장 실패');
        // 시각적 피드백: badge "직접"으로 변경 + 자동 학습 표시 해제
        row.classList.remove('is-auto');
        const badge = row.querySelector('.context-source-badge');
        if (badge) badge.textContent = '직접';
    } catch (err) {
        console.error(err);
        showToast('저장 중 오류: ' + err.message, { type: 'error' });
    }
}

async function handleContextDelete(scope, row) {
    if (!confirm('이 컨텍스트를 삭제할까요?')) return;
    const id = parseInt(row.dataset.entryId, 10);
    try {
        const res = await authFetch(`${API_BASE_URL}/contexts/${id}`, { method: 'DELETE' });
        if (!res.ok) throw new Error('삭제 실패');
        row.remove();
        // 개인 컨텍스트는 카운트 갱신을 위해 재조회, 프로젝트는 row 제거로 충분
        if (scope === 'personal') {
            await loadPersonalContext();
        }
    } catch (err) {
        console.error(err);
        showToast('삭제 중 오류: ' + err.message, { type: 'error' });
    }
}

async function handleContextAdd(scope, container) {
    const term = container.querySelector('[data-field="term"]').value.trim();
    const correction = container.querySelector('[data-field="correction"]').value.trim();
    const note = container.querySelector('[data-field="note"]').value.trim();
    if (!term || !correction) {
        showToast('표기와 올바른 표기는 비울 수 없습니다.', { type: 'error' });
        return;
    }
    const body = { term, correction, note: note || null };
    if (scope === 'project') {
        if (!currentProjectDetail) return;
        body.project_id = currentProjectDetail.project.id;
    }
    try {
        const res = await authFetch(`${API_BASE_URL}/contexts`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || '추가 실패');
        }
        // 입력 칸 비우기
        container.querySelector('[data-field="term"]').value = '';
        container.querySelector('[data-field="correction"]').value = '';
        container.querySelector('[data-field="note"]').value = '';
        // 다시 로드
        if (scope === 'project') {
            await openProjectDetail(currentProjectDetail.project.id);
            switchProjectTab('context');
        } else {
            await loadPersonalContext();
        }
    } catch (err) {
        console.error(err);
        showToast('추가 중 오류: ' + err.message, { type: 'error' });
    }
}
