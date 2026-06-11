// ============================================
// mypage.js — 내 페이지: 누적 사용 통계 + 메타 프롬프트 열람
// ============================================

let _systemPromptLoaded = false;

async function loadMyPage() {
    const statusEl = document.getElementById('myPageStatus');
    const grid = document.getElementById('statsGrid');
    const modelSection = document.getElementById('modelStatsSection');
    const emailEl = document.getElementById('myPageEmail');

    if (emailEl && currentUser) emailEl.textContent = currentUser.email || '';
    if (statusEl) statusEl.textContent = '불러오는 중...';

    try {
        const res = await authFetch(`${API_BASE_URL}/me/stats`);
        if (!res.ok) throw new Error('통계 조회 실패');
        const data = await res.json();
        const s = data.stats;

        document.getElementById('statSummaries').textContent = `${s.total_summaries}건`;
        document.getElementById('statSttMinutes').textContent = `${Math.round(s.stt_minutes)}분`;
        document.getElementById('statTotalCost').textContent = `$${s.total_cost.toFixed(2)}`;
        document.getElementById('statMonthlyCost').textContent = `$${(s.monthly_cost || 0).toFixed(2)}`;

        if (grid) grid.hidden = false;
        if (statusEl) {
            statusEl.textContent = `프로젝트 ${s.total_projects}개 · STT 비용 $${s.stt_cost.toFixed(2)} + LLM 비용 $${s.llm_cost.toFixed(2)}`;
        }

        // 모델별 사용 표
        const body = document.getElementById('modelStatsBody');
        if (body) {
            body.innerHTML = '';
            (s.models || []).forEach(m => {
                const tr = document.createElement('tr');
                const tdModel = document.createElement('td');
                tdModel.textContent = m.model;
                const tdCount = document.createElement('td');
                tdCount.textContent = `${m.count}회`;
                const tdCost = document.createElement('td');
                tdCost.textContent = `$${m.cost.toFixed(3)}`;
                tr.append(tdModel, tdCount, tdCost);
                body.appendChild(tr);
            });
            if (modelSection) modelSection.hidden = (s.models || []).length === 0;
        }
    } catch (err) {
        console.error(err);
        if (statusEl) statusEl.textContent = '통계를 불러오지 못했습니다: ' + err.message;
    }
}

// 메타(시스템) 프롬프트 토글 — 처음 열 때만 fetch
async function toggleSystemPrompt() {
    const view = document.getElementById('systemPromptView');
    const btn = document.getElementById('togglePromptBtn');
    if (!view || !btn) return;

    if (!view.hidden) {
        view.hidden = true;
        btn.textContent = '프롬프트 보기';
        return;
    }

    if (!_systemPromptLoaded) {
        btn.disabled = true;
        btn.textContent = '불러오는 중...';
        try {
            const res = await authFetch(`${API_BASE_URL}/meta/system-prompt`);
            if (!res.ok) throw new Error('프롬프트 조회 실패');
            const data = await res.json();
            const injected = (data.injected_sections || []).map(s => `- ${s}`).join('\n');
            view.textContent =
                data.system_prompt +
                (injected ? `\n\n────────────────────\n[매 호출마다 추가 주입되는 섹션]\n${injected}` : '');
            _systemPromptLoaded = true;
        } catch (err) {
            console.error(err);
            showToast('프롬프트를 불러오지 못했습니다: ' + err.message, { type: 'error' });
            btn.disabled = false;
            btn.textContent = '프롬프트 보기';
            return;
        }
        btn.disabled = false;
    }

    view.hidden = false;
    btn.textContent = '프롬프트 접기';
}
