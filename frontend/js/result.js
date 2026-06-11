// ============================================
// result.js — 회의록 상세/편집 페이지: 표시/탭/복사/편집/이메일/버전+diff/분류/삭제
// ============================================

// ---- 상세 표시 ----

function showResult(data) {
    // 마크다운 설정
    marked.setOptions({
        breaks: true,
        gfm: true,
        headerIds: false,
        mangle: false
    });

    currentSummaryMarkdown = data.summary;
    const summaryElement = document.getElementById('summaryText');
    summaryElement.innerHTML = marked.parse(data.summary);

    document.getElementById('transcriptText').textContent = data.transcript;

    // 직전 상세에서 열어둔 편집 모드/탭 상태 초기화
    if (isEditMode) cancelEdit();
    switchTab('summary');
}

// ---- 프로젝트 분류 (상세에서 변경) ----

async function populateDetailProjectSelect(selectedProjectId) {
    const select = document.getElementById('detailProjectSelect');
    if (!select) return;

    select.innerHTML = '';
    const noneOpt = document.createElement('option');
    noneOpt.value = '';
    noneOpt.textContent = '— 프로젝트 없음 —';
    select.appendChild(noneOpt);

    try {
        const res = await authFetch(`${API_BASE_URL}/projects`);
        if (res.ok) {
            const data = await res.json();
            (data.projects || []).forEach(p => {
                const opt = document.createElement('option');
                opt.value = String(p.id);
                opt.textContent = p.name;
                select.appendChild(opt);
            });
        }
    } catch (err) {
        console.warn('프로젝트 옵션 로드 실패:', err);
    }

    select.value = selectedProjectId != null ? String(selectedProjectId) : '';
}

async function applyDetailProject() {
    if (!resultData || !resultData.summaryId) return;
    const select = document.getElementById('detailProjectSelect');
    const btn = document.getElementById('detailProjectApplyBtn');
    if (!select) return;

    const newProjectId = select.value ? parseInt(select.value, 10) : null;
    if (btn) { btn.disabled = true; btn.textContent = '적용 중...'; }
    try {
        const res = await authFetch(`${API_BASE_URL}/summaries/${resultData.summaryId}/project`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ project_id: newProjectId }),
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || '분류 변경 실패');
        }
        const data = await res.json();
        resultData.projectId = data.project_id;
        if (data.project_name) {
            showToast(`"${data.project_name}" 프로젝트로 분류했어요. 분류를 마치면 프로젝트의 AI 메모리 탭에서 "전체 재구축"을 눌러주세요.`, { type: 'success', duration: 7000 });
        } else {
            showToast('프로젝트 분류를 해제했어요.', { type: 'success' });
        }
    } catch (err) {
        console.error(err);
        showToast('분류 변경 중 오류: ' + err.message, { type: 'error' });
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = '분류 적용'; }
    }
}

// ---- 상세에서 삭제 ----

async function deleteCurrentSummary() {
    if (!resultData || !resultData.summaryId) return;
    const title = resultData.meetingTitle || resultData.fileName || '이 회의록';
    if (!confirm(`"${title}"을(를) 삭제할까요?\n버전 이력까지 함께 삭제되며 되돌릴 수 없습니다.`)) return;
    try {
        const res = await authFetch(`${API_BASE_URL}/summaries/${resultData.summaryId}`, { method: 'DELETE' });
        if (!res.ok) throw new Error('삭제 실패');
        showToast('회의록을 삭제했어요.', { type: 'success' });
        switchView('dashboard');
    } catch (err) {
        console.error(err);
        showToast('삭제 중 오류: ' + err.message, { type: 'error' });
    }
}

// 탭 전환 (상세 페이지 회의록/원본 — 다른 화면의 탭과 간섭하지 않도록 스코프 한정)
function switchTab(tabName) {
    document.querySelectorAll('#detailView .tab[data-tab]').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.tab === tabName);
    });
    ['summaryContent', 'transcriptContent'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.classList.toggle('active', id === tabName + 'Content');
    });
}

// 클립보드 복사
async function copyToClipboard() {
    if (!currentSummaryMarkdown) return;

    const originalHTML = copyBtn.innerHTML;
    try {
        await navigator.clipboard.writeText(currentSummaryMarkdown);
        copyBtn.innerHTML = `
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M5 10L8 13L15 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            복사 완료!`;
        setTimeout(() => { copyBtn.innerHTML = originalHTML; }, 2000);
    } catch (error) {
        console.error('Copy error:', error);
        showToast('복사에 실패했습니다.', { type: 'error' });
    }
}

// ---- 버전 드롭다운 + diff ----

function renderVersionBar() {
    const bar = document.getElementById('versionBar');
    const select = document.getElementById('versionSelect');
    const toggleDiffBtn = document.getElementById('toggleDiffBtn');
    if (!bar || !select) return;

    if (!currentVersions || currentVersions.length === 0) {
        bar.style.display = 'none';
        return;
    }

    bar.style.display = 'flex';
    select.innerHTML = '';
    // 최신 → 과거 순으로 옵션 구성
    const reversed = [...currentVersions].reverse();
    reversed.forEach((v, idx) => {
        const isLatest = idx === 0;
        const sourceLabel = v.source === 'ai_initial' ? 'AI 원본' : '내 수정';
        const dateStr = v.created_at ? formatDateKo(v.created_at) : '';
        const latestTag = isLatest ? ' · 최신' : '';
        const opt = document.createElement('option');
        opt.value = String(v.version_no);
        opt.textContent = `v${v.version_no} (${sourceLabel}${latestTag}) — ${dateStr}`;
        select.appendChild(opt);
    });

    select.value = String(currentVersionNo);
    updateVersionBadge();

    // 첫 버전(v1)이면 diff 버튼 비활성화
    if (toggleDiffBtn) {
        const hasPrevious = currentVersionNo > 1;
        toggleDiffBtn.disabled = !hasPrevious;
        toggleDiffBtn.style.opacity = hasPrevious ? '1' : '0.4';
        toggleDiffBtn.style.cursor = hasPrevious ? 'pointer' : 'not-allowed';
        toggleDiffBtn.textContent = isDiffOpen ? '차이 숨기기' : '이전 버전과 차이 보기';
    }

    // diff 영역 갱신
    const diffView = document.getElementById('diffView');
    if (diffView) diffView.style.display = isDiffOpen && currentVersionNo > 1 ? 'block' : 'none';
    if (isDiffOpen && currentVersionNo > 1) renderDiff();

    // 편집 버튼 가능 여부
    refreshEditButtonState();
}

function updateVersionBadge() {
    const badge = document.getElementById('versionBadge');
    if (!badge) return;
    const current = currentVersions.find(v => v.version_no === currentVersionNo);
    if (!current) {
        badge.textContent = '';
        badge.className = 'version-badge';
        return;
    }
    if (current.source === 'ai_initial') {
        badge.textContent = 'AI가 처음 만든 버전입니다';
        badge.className = 'version-badge is-ai';
    } else {
        badge.textContent = '내가 수정한 버전입니다';
        badge.className = 'version-badge is-edit';
    }
}

function onVersionSelectChange(e) {
    const newVerNo = parseInt(e.target.value, 10);
    if (Number.isNaN(newVerNo)) return;

    const v = currentVersions.find(x => x.version_no === newVerNo);
    if (!v) return;

    currentVersionNo = newVerNo;
    const latestNo = currentVersions[currentVersions.length - 1].version_no;
    isViewingLatest = newVerNo === latestNo;

    // 화면 본문 갱신
    currentSummaryMarkdown = v.content;
    const summaryElement = document.getElementById('summaryText');
    if (summaryElement) summaryElement.innerHTML = marked.parse(v.content);

    // 이전 버전 보기 안내
    let notice = document.getElementById('viewingOldNotice');
    const summaryContent = document.getElementById('summaryContent');
    if (!isViewingLatest) {
        if (!notice && summaryContent) {
            notice = document.createElement('div');
            notice.id = 'viewingOldNotice';
            notice.className = 'viewing-old-notice';
            notice.textContent = '과거 버전을 보고 있습니다. 편집은 최신 버전에서만 가능합니다.';
            summaryContent.insertBefore(notice, summaryContent.firstChild);
        }
    } else if (notice) {
        notice.remove();
    }

    updateVersionBadge();
    refreshEditButtonState();

    // 첫 버전이면 diff 자동 닫기
    const toggleDiffBtn = document.getElementById('toggleDiffBtn');
    if (currentVersionNo <= 1) {
        isDiffOpen = false;
        const diffView = document.getElementById('diffView');
        if (diffView) diffView.style.display = 'none';
        if (toggleDiffBtn) {
            toggleDiffBtn.disabled = true;
            toggleDiffBtn.style.opacity = '0.4';
            toggleDiffBtn.style.cursor = 'not-allowed';
            toggleDiffBtn.textContent = '이전 버전과 차이 보기';
        }
    } else {
        if (toggleDiffBtn) {
            toggleDiffBtn.disabled = false;
            toggleDiffBtn.style.opacity = '1';
            toggleDiffBtn.style.cursor = 'pointer';
        }
        if (isDiffOpen) renderDiff();
    }
}

function toggleDiff() {
    if (!currentVersionNo || currentVersionNo <= 1) return;
    isDiffOpen = !isDiffOpen;
    const diffView = document.getElementById('diffView');
    const btn = document.getElementById('toggleDiffBtn');
    if (diffView) diffView.style.display = isDiffOpen ? 'block' : 'none';
    if (btn) btn.textContent = isDiffOpen ? '차이 숨기기' : '이전 버전과 차이 보기';
    if (isDiffOpen) renderDiff();
}

function renderDiff() {
    if (!currentVersionNo || currentVersionNo <= 1) return;
    const prev = currentVersions.find(v => v.version_no === currentVersionNo - 1);
    const curr = currentVersions.find(v => v.version_no === currentVersionNo);
    if (!prev || !curr) return;

    const headerText = document.getElementById('diffHeaderText');
    if (headerText) {
        headerText.textContent = `v${prev.version_no} → v${curr.version_no}`;
    }

    const pre = document.getElementById('diffContent');
    if (!pre) return;
    pre.innerHTML = '';

    if (typeof Diff === 'undefined') {
        pre.textContent = '(diff 라이브러리 로드 실패)';
        return;
    }

    const parts = Diff.diffLines(prev.content || '', curr.content || '');
    parts.forEach(part => {
        const lines = part.value.split('\n');
        // 마지막 빈 라인 제거 (split로 인한 trailing)
        if (lines.length > 0 && lines[lines.length - 1] === '') lines.pop();

        const cls = part.added ? 'added' : (part.removed ? 'removed' : 'context');
        const prefix = part.added ? '+ ' : (part.removed ? '− ' : '  ');

        lines.forEach(line => {
            const span = document.createElement('span');
            span.className = `diff-line ${cls}`;
            span.textContent = prefix + line;
            pre.appendChild(span);
        });
    });
}

function refreshEditButtonState() {
    const editBtn = document.getElementById('editBtn');
    if (!editBtn) return;
    if (isViewingLatest) {
        editBtn.disabled = false;
        editBtn.style.opacity = '1';
        editBtn.style.cursor = 'pointer';
        editBtn.title = '';
    } else {
        editBtn.disabled = true;
        editBtn.style.opacity = '0.5';
        editBtn.style.cursor = 'not-allowed';
        editBtn.title = '편집은 최신 버전에서만 가능합니다';
    }
}

// ---- 편집 ----

function toggleEditMode() {
    if (isEditMode) {
        cancelEdit();
        return;
    }

    isEditMode = true;
    document.querySelector('#summaryContent .content-box').style.display = 'none';
    document.getElementById('editArea').style.display = 'block';
    document.getElementById('editTextarea').value = currentSummaryMarkdown;
    document.getElementById('editBtn').textContent = '편집 취소';
}

function cancelEdit() {
    isEditMode = false;
    document.querySelector('#summaryContent .content-box').style.display = 'block';
    document.getElementById('editArea').style.display = 'none';
    document.getElementById('editBtn').innerHTML = `
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M14.85 2.85a1.2 1.2 0 011.7 1.7L6.7 14.4l-3.4.85.85-3.4L14.85 2.85z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        편집`;
}

async function saveSummaryEdit() {
    if (!resultData || !resultData.summaryId) return;

    const newSummary = document.getElementById('editTextarea').value.trim();
    if (!newSummary) {
        showToast('요약 내용을 입력해주세요.', { type: 'error' });
        return;
    }

    const saveBtn = document.getElementById('saveEditBtn');
    saveBtn.textContent = '저장 중...';
    saveBtn.disabled = true;

    try {
        const res = await authFetch(`${API_BASE_URL}/summaries/${resultData.summaryId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ summary: newSummary }),
        });

        if (!res.ok) {
            const error = await res.json();
            throw new Error(error.detail || '저장에 실패했습니다');
        }

        currentSummaryMarkdown = newSummary;
        resultData.summary = newSummary;
        document.getElementById('summaryText').innerHTML = marked.parse(newSummary);

        // 버전 이력 재조회하여 드롭다운 갱신
        try {
            const verRes = await authFetch(`${API_BASE_URL}/summaries/${resultData.summaryId}/versions`);
            if (verRes.ok) {
                const verData = await verRes.json();
                currentVersions = verData.versions || [];
                if (currentVersions.length > 0) {
                    currentVersionNo = currentVersions[currentVersions.length - 1].version_no;
                    isViewingLatest = true;
                    renderVersionBar();
                }
            }
        } catch (e) {
            console.warn('버전 이력 갱신 실패:', e);
        }

        cancelEdit();
        showToast('수정이 저장됐어요. AI가 수정 패턴(용어·스타일)을 백그라운드에서 학습합니다.', { type: 'success', duration: 6000 });
    } catch (error) {
        console.error('Save error:', error);
        showToast('저장 중 오류가 발생했습니다: ' + error.message, { type: 'error' });
    } finally {
        saveBtn.textContent = '저장';
        saveBtn.disabled = false;
    }
}

// ---- 이메일 발송 ----

async function sendEmail() {
    if (!resultData || !resultData.summaryId) return;

    const btn = document.getElementById('sendEmailBtn');
    const originalHTML = btn.innerHTML;
    btn.innerHTML = '<div class="spinner" style="width:16px;height:16px;border-width:2px;"></div> 발송 중...';
    btn.disabled = true;

    try {
        const res = await authFetch(`${API_BASE_URL}/summaries/${resultData.summaryId}/send-email`, {
            method: 'POST',
        });

        if (!res.ok) {
            const error = await res.json();
            throw new Error(error.detail || '이메일 발송에 실패했습니다');
        }

        const data = await res.json();
        showToast(data.message, { type: 'success' });
    } catch (error) {
        console.error('Email error:', error);
        showToast('이메일 발송 중 오류가 발생했습니다: ' + error.message, { type: 'error' });
    } finally {
        btn.innerHTML = originalHTML;
        btn.disabled = false;
    }
}

// ---- 상세 상태 정리 (상세 페이지를 떠날 때 호출) ----

function clearDetailState() {
    resultData = null;
    currentSummaryId = null;
    currentVersions = [];
    currentVersionNo = null;
    isViewingLatest = true;
    isDiffOpen = false;
    if (isEditMode) cancelEdit();
    const versionBar = document.getElementById('versionBar');
    if (versionBar) versionBar.style.display = 'none';
    const diffView = document.getElementById('diffView');
    if (diffView) diffView.style.display = 'none';
    const oldNotice = document.getElementById('viewingOldNotice');
    if (oldNotice) oldNotice.remove();
}
