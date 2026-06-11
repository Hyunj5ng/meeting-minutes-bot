// ============================================
// dashboard.js — 내 회의록 목록/검색 + 항목 열기
// ============================================

async function loadDashboard(query) {
    const statusEl = document.getElementById('dashboardStatus');
    const listEl = document.getElementById('dashboardList');
    if (!listEl) return;

    statusEl.textContent = '불러오는 중...';
    listEl.innerHTML = '';

    try {
        const url = `${API_BASE_URL}/summaries?limit=100${query ? `&q=${encodeURIComponent(query)}` : ''}`;
        const res = await authFetch(url);
        if (!res.ok) throw new Error('목록 조회 실패');
        const data = await res.json();
        const records = data.records || [];

        if (records.length === 0) {
            statusEl.textContent = query
                ? `"${query}"에 해당하는 회의록이 없습니다.`
                : '아직 회의록이 없습니다. 첫 회의록을 만들어보세요!';
            return;
        }

        statusEl.textContent = `총 ${records.length}건`;
        renderDashboardList(records);
    } catch (err) {
        console.error(err);
        statusEl.textContent = '목록을 불러오지 못했습니다: ' + err.message;
    }
}

function renderDashboardList(records) {
    const listEl = document.getElementById('dashboardList');
    listEl.innerHTML = '';

    records.forEach(rec => {
        const item = document.createElement('div');
        item.className = 'dashboard-item';
        item.dataset.summaryId = rec.id;

        const title = rec.meeting_title || rec.filename || `요약 #${rec.id}`;
        const dateStr = rec.created_at ? formatDateKo(rec.created_at) : '';
        const editedBadge = rec.is_edited
            ? `<span class="edited-badge">수정됨 v${rec.version_count}</span>`
            : '';

        const metaChips = [];
        if (rec.project_name) metaChips.push(`<span class="meta-chip">${escapeHtml(rec.project_name)}</span>`);
        if (rec.gpt_model) metaChips.push(`<span class="meta-chip">${escapeHtml(rec.gpt_model)}</span>`);
        if (dateStr) metaChips.push(`<span class="meta-chip">${dateStr}</span>`);

        item.innerHTML = `
            <div class="dashboard-item-title">
                ${escapeHtml(title)}
                ${editedBadge}
                <button type="button" class="dashboard-item-delete" title="이 회의록 삭제" aria-label="삭제">
                    <svg width="15" height="15" viewBox="0 0 20 20" fill="none">
                        <path d="M4 6h12M8 6V4.5C8 4.22 8.22 4 8.5 4h3c.28 0 .5.22.5.5V6m2 0v9.5c0 .28-.22.5-.5.5h-7a.5.5 0 01-.5-.5V6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                </button>
            </div>
            <div class="dashboard-item-meta">${metaChips.join('')}</div>
            <div class="dashboard-item-preview">${escapeHtml(rec.summary_preview || '')}</div>
        `;

        item.addEventListener('click', () => openSummaryFromDashboard(rec.id));
        item.querySelector('.dashboard-item-delete').addEventListener('click', (e) => {
            e.stopPropagation();
            deleteSummaryFromDashboard(rec.id, title, item);
        });
        listEl.appendChild(item);
    });
}

// 대시보드에서 회의록 삭제 (버전 이력 + 검색 임베딩까지 함께 정리됨)
async function deleteSummaryFromDashboard(summaryId, title, itemEl) {
    if (!confirm(`"${title}" 회의록을 삭제할까요?\n버전 이력까지 함께 삭제되며 되돌릴 수 없습니다.`)) return;
    try {
        const res = await authFetch(`${API_BASE_URL}/summaries/${summaryId}`, { method: 'DELETE' });
        if (!res.ok) throw new Error('삭제 실패');
        itemEl.remove();
        // 총 건수 갱신
        const statusEl = document.getElementById('dashboardStatus');
        const listEl = document.getElementById('dashboardList');
        if (statusEl && listEl) {
            const remain = listEl.children.length;
            statusEl.textContent = remain > 0 ? `총 ${remain}건` : '아직 회의록이 없습니다. 첫 회의록을 만들어보세요!';
        }
        showToast('회의록을 삭제했어요.', { type: 'success' });
    } catch (err) {
        console.error(err);
        showToast('삭제 중 오류: ' + err.message, { type: 'error' });
    }
}

// 대시보드에서 항목 클릭 → 생성 뷰로 전환하여 결과 카드 표시
async function openSummaryFromDashboard(summaryId) {
    try {
        const [sumRes, verRes] = await Promise.all([
            authFetch(`${API_BASE_URL}/summaries/${summaryId}`),
            authFetch(`${API_BASE_URL}/summaries/${summaryId}/versions`),
        ]);
        if (!sumRes.ok) throw new Error('요약을 불러오지 못했습니다');
        if (!verRes.ok) throw new Error('버전 이력을 불러오지 못했습니다');

        const sumData = await sumRes.json();
        const verData = await verRes.json();
        const record = sumData.record;

        // 생성 뷰로 이동 (상단 업로드 카드는 접고 결과만 노출)
        switchView('create');
        collapseUploadCard();

        resultData = {
            summary: record.summary,
            summaryId: record.id,
            transcript: record.transcript || '',
            gptModel: record.gpt_model,
            meetingTitle: record.meeting_title,
            fileName: record.filename,
        };
        currentSummaryId = record.id;
        currentVersions = verData.versions || [];
        currentVersionNo = currentVersions.length > 0
            ? currentVersions[currentVersions.length - 1].version_no
            : null;
        isViewingLatest = true;
        isDiffOpen = false;

        // 결과 헤더 제목 갱신
        const titleEl = document.getElementById('resultTitle');
        if (titleEl) {
            titleEl.textContent = record.meeting_title || record.filename || '회의록';
        }

        setResultBackLink(true); // 목록에서 왔으니 돌아가는 길을 보여준다
        showResult(resultData);
        renderVersionBar();
    } catch (err) {
        console.error(err);
        showToast('회의록을 여는 데 실패했습니다: ' + err.message, { type: 'error' });
    }
}
