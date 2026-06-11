// ============================================
// result.js — 결과 카드: 표시/탭/복사/편집/이메일/버전+diff/리셋
// ============================================

// ---- Accordion (업로드 카드 접기/펼치기) ----

function collapseUploadCard() {
    const card = document.getElementById('uploadCard');
    if (card) card.classList.add('collapsed');
}

function expandUploadCard() {
    const card = document.getElementById('uploadCard');
    if (card) card.classList.remove('collapsed');
}

function toggleUploadCard() {
    const card = document.getElementById('uploadCard');
    if (card) card.classList.toggle('collapsed');
}

// ---- 결과 표시 ----

function showResult(data) {
    resultSection.style.display = 'block';

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

    resultSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// 탭 전환
function switchTab(tabName) {
    const tabs = document.querySelectorAll('.tab');
    tabs.forEach(tab => {
        if (tab.dataset.tab === tabName) {
            tab.classList.add('active');
        } else {
            tab.classList.remove('active');
        }
    });

    const contents = document.querySelectorAll('.tab-content');
    contents.forEach(content => {
        if (content.id === tabName + 'Content') {
            content.classList.add('active');
        } else {
            content.classList.remove('active');
        }
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
        alert('복사에 실패했습니다.');
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
        alert('요약 내용을 입력해주세요.');
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
    } catch (error) {
        console.error('Save error:', error);
        alert('저장 중 오류가 발생했습니다: ' + error.message);
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
        alert(data.message);
    } catch (error) {
        console.error('Email error:', error);
        alert('이메일 발송 중 오류가 발생했습니다: ' + error.message);
    } finally {
        btn.innerHTML = originalHTML;
        btn.disabled = false;
    }
}

// ---- 리셋 ----

// 리셋 — 결과 화면을 닫고 업로드 영역으로 돌아감. 진행 중인 작업 카드는 유지.
function reset() {
    selectedFiles = [];
    audioDurations = [];
    resultData = null;
    if (fileInput) fileInput.value = '';

    // 버전 상태 초기화
    currentSummaryId = null;
    currentVersions = [];
    currentVersionNo = null;
    isViewingLatest = true;
    isDiffOpen = false;
    const versionBar = document.getElementById('versionBar');
    if (versionBar) versionBar.style.display = 'none';
    const diffView = document.getElementById('diffView');
    if (diffView) diffView.style.display = 'none';
    const oldNotice = document.getElementById('viewingOldNotice');
    if (oldNotice) oldNotice.remove();

    // 업로드 카드 펼치기
    expandUploadCard();

    // 결과 숨기기 (작업 큐 카드는 유지 — 다른 진행 중 작업이 있을 수 있음)
    resultSection.style.display = 'none';

    clearFile();
    window.scrollTo({ top: 0, behavior: 'smooth' });
}
