// API 엔드포인트 설정
// 같은 서버에서 서빙되므로 상대 경로 사용
const API_BASE_URL = '';

// 추정 상수 (time = base + rate * tokens/1000, +30% 여유는 계산 시 적용)
const ESTIMATION = {
    stt_ratio: 0.016,  // 오디오 1초당 STT 처리 0.016초 (1분 오디오 ≈ 1초)
    summary: {
        // { base: 고정 오버헤드(초), rate: 1k토큰당 추가시간(초) }
        // OpenAI
        'gpt-5.4-pro':          { base: 30, rate: 3.0 },  // 추론형, 느림
        'gpt-5.4':              { base: 22, rate: 2.0 },
        'gpt-5.4-nano':         { base: 15, rate: 0.8 },
        // Anthropic
        'claude-opus-4.6':      { base: 28, rate: 2.5 },
        'claude-sonnet-4.6':    { base: 25, rate: 1.2 },
        'claude-haiku-4.5':     { base: 8,  rate: 1.1 },
        // Google
        'gemini-2.5-pro':       { base: 20, rate: 2.0 },
        'gemini-2.5-flash':     { base: 10, rate: 1.0 },
        'gemini-2.5-flash-lite': { base: 5, rate: 0.5 },
        // DeepSeek
        'deepseek-r1':          { base: 25, rate: 2.5 },  // 추론형
        'deepseek-chat':        { base: 12, rate: 0.8 },
        'deepseek-v3.2':        { base: 10, rate: 0.7 },
        // Meta Llama
        'llama-3.3-70b':        { base: 18, rate: 1.5 },
        'llama-4-maverick':     { base: 15, rate: 1.2 },
        'llama-4-scout':        { base: 8,  rate: 0.5 },
    },
    summary_default: { base: 20, rate: 1.5 },
};

// 전역 변수
let selectedFile = null;
let transcriptData = null;
let resultData = null;
let audioDuration = 0; // 오디오 길이 (초)
let summaryHistory = []; // 여러 요약 결과 저장
let currentSummaryMarkdown = ''; // 현재 요약 마크다운 원본 (지금 화면에 표시되는 것)
let isEditMode = false;

// 버전 관리 상태
let currentSummaryId = null;          // 현재 화면에 있는 요약 ID
let currentVersions = [];             // [{version_no, source, content, created_at}, ...] (오름차순)
let currentVersionNo = null;          // 지금 보고 있는 버전 번호
let isViewingLatest = true;           // 최신 버전 보고 있는지 (편집 가능 여부 판단용)
let isDiffOpen = false;

// 대시보드 상태
let dashboardSearchTimer = null;
let currentView = 'create';           // 'create' | 'dashboard' | 'projects' | 'projectDetail' | 'personalContext'

// 프로젝트/컨텍스트 상태
let projectsCache = [];               // [{id, name, description, summary_count, context_count, ...}]
let currentProjectDetail = null;      // 현재 보고 있는 프로젝트 상세 (의존: summaries, contexts)
let projectModalMode = 'create';      // 'create' | 'edit'
let projectModalTargetId = null;      // edit 모드일 때 대상 id

// 인증 상태
let currentUser = null;
let accessToken = null;
let refreshToken = null;
let _isRefreshing = false;
let _refreshPromise = null;

// DOM 요소 (로그인 후 초기화)
let uploadArea, fileInput, fileInfo, fileName, fileSize;
let removeFileBtn, convertBtn, resultSection, copyBtn, resetBtn;

// ============================================
// RealisticProgress 클래스
// 점근 곡선: 95 * (1 - e^(-2.5 * elapsed/estimated))
// ============================================

class RealisticProgress {
    constructor(estimatedMs, onUpdate) {
        this.estimatedMs = Math.max(estimatedMs, 1000); // 최소 1초
        this.onUpdate = onUpdate;
        this.startTime = null;
        this.intervalId = null;
        this.completed = false;
    }

    start() {
        this.startTime = Date.now();
        this.intervalId = setInterval(() => {
            if (this.completed) return;
            const elapsed = Date.now() - this.startTime;
            const ratio = elapsed / this.estimatedMs;
            const progress = 95 * (1 - Math.exp(-2.5 * ratio));
            const remaining = Math.max(0, this.estimatedMs - elapsed);
            this.onUpdate(Math.min(progress, 95), remaining);
        }, 200);
    }

    complete() {
        this.completed = true;
        if (this.intervalId) clearInterval(this.intervalId);
        this.onUpdate(100, 0);
    }

    stop() {
        this.completed = true;
        if (this.intervalId) clearInterval(this.intervalId);
    }
}

// ============================================
// 유틸리티
// ============================================

function formatEta(ms) {
    const seconds = Math.ceil(ms / 1000);
    if (seconds <= 0) return '';
    const min = Math.floor(seconds / 60);
    const sec = seconds % 60;
    if (min > 0) return `약 ${min}분 ${sec}초 남음`;
    return `약 ${sec}초 남음`;
}

function formatElapsed(seconds) {
    const min = Math.floor(seconds / 60);
    const sec = seconds % 60;
    if (min > 0) return `${min}분 ${sec}초`;
    return `${seconds}초`;
}

// ============================================
// 스테퍼 헬퍼
// ============================================

function setStepState(stepNum, state) {
    const step = document.getElementById(`step${stepNum}`);
    if (step) step.setAttribute('data-state', state);
}

function updateStepUI(stepNum, percent, statusText, etaText) {
    const bar = document.getElementById(`step${stepNum}ProgressBar`);
    const pct = document.getElementById(`step${stepNum}Progress`);
    const status = document.getElementById(`step${stepNum}Status`);
    const eta = document.getElementById(`step${stepNum}Eta`);

    if (bar) bar.style.width = percent + '%';
    if (pct) pct.textContent = Math.round(percent) + '%';
    if (status) status.textContent = statusText;
    if (eta) eta.textContent = etaText || '';
}

// ============================================
// Accordion (업로드 카드 접기/펼치기)
// ============================================

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

// 초기화
document.addEventListener('DOMContentLoaded', () => {
    initAuth();
});

// ============================================
// 인증 관련
// ============================================

function initAuth() {
    accessToken = localStorage.getItem('access_token');
    refreshToken = localStorage.getItem('refresh_token');
    if (accessToken) {
        verifyToken();
    } else if (refreshToken) {
        tryRefreshToken();
    } else {
        showLoginSection();
    }
}

function initGoogleSignIn() {
    const clientId = document.querySelector('meta[name="google-client-id"]')?.content;
    if (!clientId) {
        console.error('Google Client ID가 설정되지 않았습니다');
        return;
    }

    google.accounts.id.initialize({
        client_id: clientId,
        callback: handleGoogleSignIn,
    });
    google.accounts.id.renderButton(
        document.getElementById('googleSignInBtn'),
        { theme: 'outline', size: 'large', text: 'signin_with', locale: 'ko' }
    );
}

async function handleGoogleSignIn(response) {
    try {
        const formData = new FormData();
        formData.append('token', response.credential);

        const res = await fetch(`${API_BASE_URL}/auth/google`, {
            method: 'POST',
            body: formData,
        });

        if (!res.ok) {
            const error = await res.json();
            throw new Error(error.detail || '로그인에 실패했습니다');
        }

        const data = await res.json();
        accessToken = data.access_token;
        refreshToken = data.refresh_token;
        currentUser = data.user;
        localStorage.setItem('access_token', accessToken);
        localStorage.setItem('refresh_token', refreshToken);

        showMainApp();
    } catch (error) {
        console.error('Google 로그인 오류:', error);
        alert('로그인에 실패했습니다: ' + error.message);
    }
}

async function verifyToken() {
    try {
        const res = await fetch(`${API_BASE_URL}/auth/me`, {
            headers: { 'Authorization': `Bearer ${accessToken}` },
        });

        if (res.ok) {
            const data = await res.json();
            currentUser = data.user;
            showMainApp();
        } else if (refreshToken) {
            tryRefreshToken();
        } else {
            clearAuthState();
            showLoginSection();
        }
    } catch {
        if (refreshToken) {
            tryRefreshToken();
        } else {
            clearAuthState();
            showLoginSection();
        }
    }
}

async function tryRefreshToken() {
    try {
        const formData = new FormData();
        formData.append('refresh_token', refreshToken);
        const res = await fetch(`${API_BASE_URL}/auth/refresh`, {
            method: 'POST',
            body: formData,
        });
        if (res.ok) {
            const data = await res.json();
            accessToken = data.access_token;
            localStorage.setItem('access_token', accessToken);
            verifyToken();
        } else {
            clearAuthState();
            showLoginSection();
        }
    } catch {
        clearAuthState();
        showLoginSection();
    }
}

async function tryRefreshTokenSilent() {
    try {
        const formData = new FormData();
        formData.append('refresh_token', refreshToken);
        const res = await fetch(`${API_BASE_URL}/auth/refresh`, {
            method: 'POST',
            body: formData,
        });
        if (res.ok) {
            const data = await res.json();
            accessToken = data.access_token;
            localStorage.setItem('access_token', accessToken);
            return true;
        }
        return false;
    } catch {
        return false;
    }
}

function clearAuthState() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    accessToken = null;
    refreshToken = null;
    currentUser = null;
}

async function logout() {
    // 서버 측 리프레시 토큰 무효화 (best-effort)
    if (accessToken) {
        try {
            await fetch(`${API_BASE_URL}/auth/logout`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${accessToken}` },
            });
        } catch { /* ignore */ }
    }
    clearAuthState();
    if (typeof google !== 'undefined' && google.accounts) {
        google.accounts.id.disableAutoSelect();
    }
    showLoginSection();
}

function showLoginSection() {
    document.getElementById('loginSection').style.display = 'flex';
    document.getElementById('appHeader').style.display = 'none';
    document.getElementById('mainContent').style.display = 'none';

    // Google Sign-In 버튼 초기화 (GSI 스크립트 로드 대기)
    if (typeof google !== 'undefined' && google.accounts) {
        initGoogleSignIn();
    } else {
        const checkGsi = setInterval(() => {
            if (typeof google !== 'undefined' && google.accounts) {
                clearInterval(checkGsi);
                initGoogleSignIn();
            }
        }, 100);
    }
}

function showMainApp() {
    document.getElementById('loginSection').style.display = 'none';
    document.getElementById('appHeader').style.display = 'block';
    document.getElementById('mainContent').style.display = 'flex';

    // 유저 정보 표시
    if (currentUser) {
        document.getElementById('userName').textContent = currentUser.name || currentUser.email;
        const pictureEl = document.getElementById('userPicture');
        if (currentUser.picture) {
            pictureEl.src = currentUser.picture;
            pictureEl.style.display = 'block';
        } else {
            pictureEl.style.display = 'none';
        }
    }

    // 사용량 바 + 뷰 전환 네비 즉시 표시
    document.getElementById('usageBar').style.display = 'flex';
    const viewNav = document.getElementById('viewNav');
    if (viewNav) viewNav.style.display = 'flex';

    // DOM 요소 초기화
    initDomElements();
    setupEventListeners();
    fetchUsageInfo();
}

// ============================================
// 뷰 전환 (생성 / 대시보드)
// ============================================

function switchView(view) {
    currentView = view;
    const views = {
        create: document.getElementById('createView'),
        dashboard: document.getElementById('dashboardView'),
        projects: document.getElementById('projectsView'),
        projectDetail: document.getElementById('projectDetailView'),
        personalContext: document.getElementById('personalContextView'),
    };
    const navButtons = {
        create: document.getElementById('navCreate'),
        dashboard: document.getElementById('navDashboard'),
        projects: document.getElementById('navProjects'),
        personalContext: document.getElementById('navPersonalContext'),
    };

    // 모든 뷰 숨기기
    Object.values(views).forEach(el => { if (el) el.style.display = 'none'; });
    Object.values(navButtons).forEach(el => el?.classList.remove('active'));

    // 활성화
    if (views[view]) views[view].style.display = '';
    // 프로젝트 상세는 "프로젝트" 네비를 켠 상태로 유지
    if (view === 'projectDetail' && navButtons.projects) {
        navButtons.projects.classList.add('active');
    } else if (navButtons[view]) {
        navButtons[view].classList.add('active');
    }

    // 진입 시 자동 로드
    if (view === 'dashboard') loadDashboard('');
    if (view === 'projects') loadProjects();
    if (view === 'personalContext') loadPersonalContext();

    window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ============================================
// 대시보드 (내 회의록 목록)
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
            </div>
            <div class="dashboard-item-meta">${metaChips.join('')}</div>
            <div class="dashboard-item-preview">${escapeHtml(rec.summary_preview || '')}</div>
        `;

        item.addEventListener('click', () => openSummaryFromDashboard(rec.id));
        listEl.appendChild(item);
    });
}

function escapeHtml(s) {
    return String(s ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function formatDateKo(isoStr) {
    try {
        const d = new Date(isoStr);
        const yy = d.getFullYear();
        const mm = String(d.getMonth() + 1).padStart(2, '0');
        const dd = String(d.getDate()).padStart(2, '0');
        const hh = String(d.getHours()).padStart(2, '0');
        const mi = String(d.getMinutes()).padStart(2, '0');
        return `${yy}-${mm}-${dd} ${hh}:${mi}`;
    } catch {
        return isoStr;
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
        const stepperCard = document.getElementById('stepperCard');
        if (stepperCard) stepperCard.style.display = 'none';

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

        showResult(resultData);
        renderVersionBar();
    } catch (err) {
        console.error(err);
        alert('회의록을 여는 데 실패했습니다: ' + err.message);
    }
}

// ============================================
// 버전 드롭다운 + diff
// ============================================

function renderVersionBar() {
    const bar = document.getElementById('versionBar');
    const select = document.getElementById('versionSelect');
    const badge = document.getElementById('versionBadge');
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

// ============================================
// 프로젝트 목록 / 상세
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

        // 첫 탭(회의록)으로 초기화
        switchProjectTab('meetings');
        switchView('projectDetail');
    } catch (err) {
        console.error(err);
        alert('프로젝트를 여는 데 실패했습니다: ' + err.message);
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
    if (meetTab) meetTab.classList.toggle('active', tabName === 'meetings');
    if (ctxTab) ctxTab.classList.toggle('active', tabName === 'context');
}

// ============================================
// 컨텍스트 엔트리 편집
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

    entries.forEach(e => {
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
}

function escapeAttr(s) {
    return String(s ?? '')
        .replace(/&/g, '&amp;')
        .replace(/"/g, '&quot;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

async function handleContextSave(scope, row) {
    const id = parseInt(row.dataset.entryId, 10);
    const term = row.querySelector('[data-field="term"]').value.trim();
    const correction = row.querySelector('[data-field="correction"]').value.trim();
    const note = row.querySelector('[data-field="note"]').value.trim();
    if (!term || !correction) {
        alert('표기와 올바른 표기는 비울 수 없습니다.');
        return;
    }
    try {
        const res = await authFetch(`${API_BASE_URL}/contexts/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ term, correction, note }),
        });
        if (!res.ok) throw new Error('저장 실패');
        // 시각적 피드백: badge "직접"으로 변경 + 노란 배경 해제
        row.classList.remove('is-auto');
        const badge = row.querySelector('.context-source-badge');
        if (badge) badge.textContent = '직접';
    } catch (err) {
        console.error(err);
        alert('저장 중 오류: ' + err.message);
    }
}

async function handleContextDelete(scope, row) {
    if (!confirm('이 컨텍스트를 삭제할까요?')) return;
    const id = parseInt(row.dataset.entryId, 10);
    try {
        const res = await authFetch(`${API_BASE_URL}/contexts/${id}`, { method: 'DELETE' });
        if (!res.ok) throw new Error('삭제 실패');
        row.remove();
        // 카운트 갱신
        if (scope === 'personal') {
            await loadPersonalContext();
        } else if (currentProjectDetail) {
            // 프로젝트 컨텍스트는 캐시 다시 안 받고 row만 제거
        }
    } catch (err) {
        console.error(err);
        alert('삭제 중 오류: ' + err.message);
    }
}

async function handleContextAdd(scope, container) {
    const term = container.querySelector('[data-field="term"]').value.trim();
    const correction = container.querySelector('[data-field="correction"]').value.trim();
    const note = container.querySelector('[data-field="note"]').value.trim();
    if (!term || !correction) {
        alert('표기와 올바른 표기는 비울 수 없습니다.');
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
        alert('추가 중 오류: ' + err.message);
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
    if (!name) { alert('프로젝트명을 입력해주세요.'); return; }

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
        alert('저장 중 오류: ' + err.message);
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
        alert('삭제 중 오류: ' + err.message);
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

// 인증된 fetch 래퍼 (401 시 자동 토큰 갱신 + 재시도)
async function authFetch(url, options = {}) {
    if (!options.headers) {
        options.headers = {};
    }
    if (accessToken) {
        options.headers['Authorization'] = `Bearer ${accessToken}`;
    }

    let res = await fetch(url, options);

    if (res.status === 401 && refreshToken) {
        // 동시 다발적 401 방지: 하나의 refresh만 실행
        if (!_isRefreshing) {
            _isRefreshing = true;
            _refreshPromise = tryRefreshTokenSilent();
        }
        const refreshed = await _refreshPromise;
        _isRefreshing = false;
        _refreshPromise = null;

        if (refreshed) {
            // 새 토큰으로 원본 요청 재시도
            options.headers['Authorization'] = `Bearer ${accessToken}`;
            res = await fetch(url, options);
        } else {
            clearAuthState();
            showLoginSection();
            throw new Error('세션이 만료되었습니다. 다시 로그인해주세요.');
        }
    } else if (res.status === 401) {
        clearAuthState();
        showLoginSection();
        throw new Error('세션이 만료되었습니다. 다시 로그인해주세요.');
    }

    if (res.status === 429) {
        const error = await res.json();
        throw new Error(error.detail || '사용량 한도를 초과했습니다.');
    }

    return res;
}

async function fetchUsageInfo() {
    try {
        const res = await authFetch(`${API_BASE_URL}/usage`);
        if (!res.ok) return;

        const data = await res.json();
        const usageBar = document.getElementById('usageBar');
        usageBar.style.display = 'flex';

        document.getElementById('dailyStt').textContent = Math.round(data.stt.daily.used);
        document.getElementById('dailySttLimit').textContent = data.stt.daily.limit;
    } catch (error) {
        console.warn('사용량 조회 실패:', error);
    }
}

// ============================================
// DOM 및 이벤트 초기화
// ============================================

function initDomElements() {
    uploadArea = document.getElementById('uploadArea');
    fileInput = document.getElementById('fileInput');
    fileInfo = document.getElementById('fileInfo');
    fileName = document.getElementById('fileName');
    fileSize = document.getElementById('fileSize');
    removeFileBtn = document.getElementById('removeFile');
    convertBtn = document.getElementById('convertBtn');
    resultSection = document.getElementById('resultSection');
    copyBtn = document.getElementById('copyBtn');
    resetBtn = document.getElementById('resetBtn');
}

function setupEventListeners() {
    // 파일 업로드 관련
    uploadArea.addEventListener('click', () => fileInput.click());
    uploadArea.addEventListener('dragover', handleDragOver);
    uploadArea.addEventListener('dragleave', handleDragLeave);
    uploadArea.addEventListener('drop', handleDrop);
    fileInput.addEventListener('change', handleFileSelect);
    removeFileBtn.addEventListener('click', clearFile);

    // 변환 버튼
    convertBtn.addEventListener('click', handleConvert);

    // 결과 관련
    copyBtn.addEventListener('click', copyToClipboard);
    resetBtn.addEventListener('click', reset);

    // 로그아웃
    document.getElementById('logoutBtn').addEventListener('click', logout);

    // 탭 전환
    const tabs = document.querySelectorAll('.tab');
    tabs.forEach(tab => {
        tab.addEventListener('click', () => switchTab(tab.dataset.tab));
    });

    // Accordion 토글
    const uploadCardHeader = document.getElementById('uploadCardHeader');
    if (uploadCardHeader) {
        uploadCardHeader.addEventListener('click', (e) => {
            const card = document.getElementById('uploadCard');
            if (card.classList.contains('collapsed')) {
                toggleUploadCard();
            }
        });
    }

    // 뷰 전환 네비
    const navCreate = document.getElementById('navCreate');
    const navDashboard = document.getElementById('navDashboard');
    const navProjects = document.getElementById('navProjects');
    const navPersonalContext = document.getElementById('navPersonalContext');
    if (navCreate) navCreate.addEventListener('click', () => switchView('create'));
    if (navDashboard) navDashboard.addEventListener('click', () => switchView('dashboard'));
    if (navProjects) navProjects.addEventListener('click', () => switchView('projects'));
    if (navPersonalContext) navPersonalContext.addEventListener('click', () => switchView('personalContext'));

    // 대시보드 검색 (300ms 디바운스)
    const dashboardSearchInput = document.getElementById('dashboardSearch');
    if (dashboardSearchInput) {
        dashboardSearchInput.addEventListener('input', (e) => {
            const q = e.target.value.trim();
            if (dashboardSearchTimer) clearTimeout(dashboardSearchTimer);
            dashboardSearchTimer = setTimeout(() => loadDashboard(q), 300);
        });
    }

    // 버전 드롭다운 + diff 토글
    const versionSelect = document.getElementById('versionSelect');
    if (versionSelect) versionSelect.addEventListener('change', onVersionSelectChange);
    const toggleDiffBtn = document.getElementById('toggleDiffBtn');
    if (toggleDiffBtn) toggleDiffBtn.addEventListener('click', toggleDiff);

    // 프로젝트 생성/편집/삭제
    const newProjectBtn = document.getElementById('newProjectBtn');
    if (newProjectBtn) newProjectBtn.addEventListener('click', () => openProjectModal('create'));
    const backToProjectsBtn = document.getElementById('backToProjectsBtn');
    if (backToProjectsBtn) backToProjectsBtn.addEventListener('click', () => switchView('projects'));
    const editProjectBtn = document.getElementById('editProjectBtn');
    if (editProjectBtn) editProjectBtn.addEventListener('click', () => {
        if (currentProjectDetail) openProjectModal('edit', currentProjectDetail.project);
    });
    const deleteProjectBtn = document.getElementById('deleteProjectBtn');
    if (deleteProjectBtn) deleteProjectBtn.addEventListener('click', deleteCurrentProject);
    const projectModalCancel = document.getElementById('projectModalCancel');
    if (projectModalCancel) projectModalCancel.addEventListener('click', closeProjectModal);
    const projectModalSave = document.getElementById('projectModalSave');
    if (projectModalSave) projectModalSave.addEventListener('click', saveProjectModal);
    // 모달 바깥 클릭으로 닫기
    const projectModal = document.getElementById('projectModal');
    if (projectModal) projectModal.addEventListener('click', (e) => {
        if (e.target === projectModal) closeProjectModal();
    });

    // 프로젝트 상세 탭
    document.querySelectorAll('[data-project-tab]').forEach(btn => {
        btn.addEventListener('click', () => switchProjectTab(btn.dataset.projectTab));
    });

    // 컨텍스트 추가 (개인/프로젝트 공통: data-action="add")
    document.querySelectorAll('.context-editor').forEach(editor => {
        const addBtn = editor.querySelector('.context-add [data-action="add"]');
        if (addBtn) {
            addBtn.addEventListener('click', () => {
                handleContextAdd(editor.dataset.scope, editor.querySelector('.context-add'));
            });
        }
    });

    // 회의 생성 폼: 프로젝트 드롭다운
    const projectSelect = document.getElementById('projectSelect');
    if (projectSelect) projectSelect.addEventListener('change', onProjectSelectChange);

    // 초기 프로젝트 옵션 채우기
    populateProjectSelect();

    // 참석자 자동완성
    initAttendeeAutocomplete();
}

// ============================================
// 참석자 자동완성 (최근 사용 + 칩)
// ============================================

let attendeeSuggestionCache = [];      // 최근 사용 참석자 (서버에서 받아온 전체 목록)
let attendeeSuggestionProjectId = null; // 캐시가 어떤 project_id 기준인지
let attendeeFetchAbort = null;
const ATTENDEE_CHIP_LIMIT = 8;

function initAttendeeAutocomplete() {
    const input = document.getElementById('attendees');
    const container = document.getElementById('attendeeSuggestions');
    if (!input || !container) return;

    // 입력 변화 시 칩 갱신
    input.addEventListener('input', renderAttendeeChips);
    input.addEventListener('focus', () => {
        loadRecentAttendees().then(renderAttendeeChips);
    });

    // 프로젝트 변경 시 캐시 무효화 + 재로드
    const projectSelect = document.getElementById('projectSelect');
    if (projectSelect) {
        projectSelect.addEventListener('change', () => {
            attendeeSuggestionCache = [];
            attendeeSuggestionProjectId = null;
            loadRecentAttendees().then(renderAttendeeChips);
        });
    }

    // 페이지 진입 직후 한 번 미리 로드
    loadRecentAttendees().then(renderAttendeeChips);
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

function renderAttendeeChips() {
    const input = document.getElementById('attendees');
    const container = document.getElementById('attendeeSuggestions');
    if (!input || !container) return;

    const rawValue = input.value;
    const alreadyAdded = new Set(
        parseAttendeeInput(rawValue).map(n => n.toLowerCase())
    );
    const typing = getCurrentTypingFragment(rawValue).toLowerCase();

    // 필터링: 타이핑 중이면 부분 일치, 아니면 전체
    let matches = attendeeSuggestionCache;
    if (typing) {
        matches = matches.filter(name => name.toLowerCase().includes(typing));
    }

    // 이미 추가된 이름은 뒤로, 나머지는 앞 — UX상 보이긴 하되 흐리게
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
        chip.addEventListener('click', () => addAttendeeFromChip(name));
        container.appendChild(chip);
    });
}

function addAttendeeFromChip(name) {
    const input = document.getElementById('attendees');
    if (!input) return;

    const existing = parseAttendeeInput(input.value);
    if (existing.some(n => n.toLowerCase() === name.toLowerCase())) return;

    input.value = [...existing, name].join(', ') + ', ';
    input.focus();
    renderAttendeeChips();
}

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
        handleFile(files[0]);
    }
}

// 파일 선택 핸들러
function handleFileSelect(e) {
    const files = e.target.files;
    if (files.length > 0) {
        handleFile(files[0]);
    }
}

// 파일 처리
async function handleFile(file) {
    const allowedExtensions = ['.mp3', '.wav', '.m4a', '.ogg', '.flac', '.aac'];
    const fileExtension = '.' + file.name.split('.').pop().toLowerCase();

    if (!allowedExtensions.includes(fileExtension)) {
        alert('지원하지 않는 파일 형식입니다.\n지원 형식: MP3, WAV, M4A, OGG, FLAC, AAC');
        return;
    }

    selectedFile = file;

    try {
        audioDuration = await getAudioDuration(file);
        console.log(`오디오 길이: ${Math.round(audioDuration)}초 (${Math.floor(audioDuration / 60)}분 ${Math.round(audioDuration % 60)}초)`);
    } catch (error) {
        console.warn('오디오 길이 계산 실패, 파일 크기 기반으로 추정합니다:', error);
        audioDuration = 0;
    }

    fileName.textContent = file.name;
    fileSize.textContent = formatFileSize(file.size);

    uploadArea.style.display = 'none';
    fileInfo.style.display = 'flex';
    convertBtn.disabled = false;
}

function getAudioDuration(file) {
    return new Promise((resolve, reject) => {
        const audio = new Audio();
        const url = URL.createObjectURL(file);

        audio.addEventListener('loadedmetadata', () => {
            URL.revokeObjectURL(url);
            resolve(audio.duration);
        });

        audio.addEventListener('error', () => {
            URL.revokeObjectURL(url);
            reject(new Error('오디오 메타데이터 로드 실패'));
        });

        audio.src = url;
    });
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

function clearFile() {
    selectedFile = null;
    fileInput.value = '';
    uploadArea.style.display = 'block';
    fileInfo.style.display = 'none';
    convertBtn.disabled = true;
}

// ============================================
// 메인 워크플로우: 업로드 → STT → 요약
// ============================================

async function handleConvert() {
    if (!selectedFile) return;

    // 스테퍼 표시 + 업로드 카드 접기
    const stepperCard = document.getElementById('stepperCard');
    stepperCard.style.display = 'block';
    collapseUploadCard();
    resultSection.style.display = 'none';

    // 스텝 초기화
    setStepState(1, 'active');
    setStepState(2, 'pending');
    setStepState(3, 'pending');
    updateStepUI(1, 0, '업로드 준비 중...', '');
    updateStepUI(2, 0, '대기 중...', '');
    updateStepUI(3, 0, '대기 중...', '');

    // FormData 생성
    const formData = new FormData();
    formData.append('file', selectedFile);
    formData.append('whisper_model', 'base');
    formData.append('audio_duration', audioDuration || 0);
    formData.append('file_size', selectedFile.size);

    // 프로젝트 처리: 기존 프로젝트 선택 시 project_id, 신규 입력 시 project_name
    const projectSelectEl = document.getElementById('projectSelect');
    const projectNameInput = document.getElementById('projectName');
    const selectedProjectVal = projectSelectEl ? projectSelectEl.value : '';
    if (selectedProjectVal && selectedProjectVal !== '__new__') {
        formData.append('project_id', selectedProjectVal);
    } else if (selectedProjectVal === '__new__' && projectNameInput) {
        formData.append('project_name', projectNameInput.value.trim());
    } else {
        formData.append('project_name', '');
    }

    formData.append('meeting_title', document.getElementById('meetingTitle').value);
    formData.append('attendees', document.getElementById('attendees').value);

    try {
        // === Step 1: XHR 업로드 + STT ===
        const sttResult = await doUploadAndSTT(formData);

        transcriptData = {
            ...sttResult,
            transcriptId: sttResult.transcript_id,
            fileSize: selectedFile.size,
            audioDuration: audioDuration
        };

        // === Step 3: 요약 ===
        await doSummarize();

        // 사용량 갱신
        fetchUsageInfo();

    } catch (error) {
        console.error('Error:', error);
        alert('오류가 발생했습니다: ' + error.message);
        reset();
    }
}

// Step 1 + 2: XHR 업로드 (실제 진행률) + STT (추정 진행률)
function doUploadAndSTT(formData) {
    return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();

        // Step 1: 실제 업로드 진행률
        xhr.upload.addEventListener('progress', (e) => {
            if (e.lengthComputable) {
                const percent = (e.loaded / e.total) * 100;
                updateStepUI(1, percent, '파일 업로드 중...', '');
            }
        });

        xhr.upload.addEventListener('load', () => {
            // 업로드 완료 → Step 1 완료
            setStepState(1, 'completed');
            updateStepUI(1, 100, '업로드 완료!', '');

            // Step 2: STT 시작
            setStepState(2, 'active');
            const estimatedSttMs = audioDuration > 0
                ? audioDuration * ESTIMATION.stt_ratio * 1000
                : (selectedFile.size / (1024 * 1024)) * 4000; // fallback: 1MB당 4초

            // 최소 3초로 설정 (너무 빠르면 프로그레스가 의미없음)
            const sttProgress = new RealisticProgress(Math.max(estimatedSttMs, 3000), (pct, remaining) => {
                updateStepUI(2, pct, '음성을 텍스트로 변환 중...', formatEta(remaining));
            });
            sttProgress.start();

            // sttProgress를 xhr에 저장해서 응답 시 complete 호출
            xhr._sttProgress = sttProgress;
            xhr._sttStartTime = Date.now();
        });

        xhr.addEventListener('load', () => {
            if (xhr._sttProgress) xhr._sttProgress.complete();

            if (xhr.status >= 200 && xhr.status < 300) {
                const data = JSON.parse(xhr.responseText);

                const elapsed = xhr._sttStartTime ? Math.round((Date.now() - xhr._sttStartTime) / 1000) : 0;
                setStepState(2, 'completed');
                updateStepUI(2, 100, `변환 완료! (${formatElapsed(elapsed)})`, '');

                resolve(data);
            } else {
                let errorMsg = '처리 중 오류가 발생했습니다';
                try {
                    const errorData = JSON.parse(xhr.responseText);
                    errorMsg = errorData.detail || errorMsg;
                } catch {}
                reject(new Error(errorMsg));
            }
        });

        xhr.addEventListener('error', () => {
            if (xhr._sttProgress) xhr._sttProgress.stop();
            reject(new Error('네트워크 오류가 발생했습니다'));
        });

        xhr.open('POST', `${API_BASE_URL}/transcribe-only`);
        if (accessToken) {
            xhr.setRequestHeader('Authorization', `Bearer ${accessToken}`);
        }
        xhr.send(formData);
    });
}

// Step 3: 요약
async function doSummarize() {
    if (!transcriptData) return;

    setStepState(3, 'active');
    const gptModel = document.getElementById('gptModelUpload').value;
    const modelSelect = document.getElementById('gptModelUpload');
    const modelName = modelSelect.options[modelSelect.selectedIndex].text.split(' - ')[0];

    // 추정 시간 계산: base + rate * tokens/1000
    const transcriptLength = (transcriptData.transcript || '').length;
    // 한국어는 글자수/1500 ≈ 1k 토큰 (대략)
    const estimatedTokensK = transcriptLength / 1500;
    const coeff = ESTIMATION.summary[gptModel] || ESTIMATION.summary_default;
    const estimatedMs = (coeff.base + coeff.rate * estimatedTokensK) * 1000 * 1.3; // +30% 여유

    const summaryProgress = new RealisticProgress(estimatedMs, (pct, remaining) => {
        updateStepUI(3, pct, `${modelName}로 회의록 생성 중...`, formatEta(remaining));
    });
    summaryProgress.start();

    try {
        const formData = new FormData();
        formData.append('transcript_id', transcriptData.transcriptId);
        formData.append('gpt_model', gptModel);
        formData.append('save_files', 'true');
        formData.append('return_file', 'false');

        const startTime = Date.now();
        const response = await authFetch(`${API_BASE_URL}/summarize`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || '처리 중 오류가 발생했습니다');
        }

        const data = await response.json();

        summaryProgress.complete();
        const elapsed = Math.round((Date.now() - startTime) / 1000);
        setStepState(3, 'completed');
        updateStepUI(3, 100, `회의록 생성 완료! (${formatElapsed(elapsed)})`, '');

        resultData = {
            ...transcriptData,
            summary: data.summary,
            summaryId: data.summary_id,
            gptModel: gptModel
        };

        summaryHistory.push({
            summaryId: data.summary_id,
            transcriptId: data.transcript_id,
            gptModel: gptModel,
            summary: data.summary,
            timestamp: data.timestamp,
            createdAt: new Date().toISOString()
        });

        // 버전 상태 초기화 (방금 만들어진 v1=ai_initial)
        currentSummaryId = data.summary_id;
        currentVersions = [{
            version_no: 1,
            source: 'ai_initial',
            content: data.summary,
            created_at: new Date().toISOString(),
        }];
        currentVersionNo = 1;
        isViewingLatest = true;
        isDiffOpen = false;

        // 결과 표시
        await new Promise(resolve => setTimeout(resolve, 500));
        const titleEl = document.getElementById('resultTitle');
        if (titleEl) titleEl.textContent = '회의록 생성 완료!';
        showResult(resultData);
        renderVersionBar();

        // 이메일 자동 발송
        const autoEmail = document.getElementById('autoEmailCheckbox');
        if (autoEmail && autoEmail.checked && resultData.summaryId) {
            try {
                const emailRes = await authFetch(`${API_BASE_URL}/summaries/${resultData.summaryId}/send-email`, {
                    method: 'POST',
                });
                if (emailRes.ok) {
                    const emailData = await emailRes.json();
                    alert(emailData.message);
                } else {
                    const emailError = await emailRes.json();
                    alert('이메일 발송 실패: ' + (emailError.detail || '알 수 없는 오류'));
                }
            } catch (emailErr) {
                console.error('Auto email error:', emailErr);
                alert('이메일 자동 발송 중 오류: ' + emailErr.message);
            }
        }

    } catch (error) {
        summaryProgress.stop();
        setStepState(3, 'error');
        updateStepUI(3, 0, '오류 발생: ' + error.message, '');
        throw error;
    }
}

// 결과 표시
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

// ============================================
// 편집 기능 (F3)
// ============================================

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

// ============================================
// 이메일 발송 기능 (F4)
// ============================================

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

// 리셋
function reset() {
    selectedFile = null;
    transcriptData = null;
    resultData = null;
    audioDuration = 0;
    summaryHistory = [];
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

    // 스테퍼 숨기기 + 리셋
    const stepperCard = document.getElementById('stepperCard');
    if (stepperCard) stepperCard.style.display = 'none';
    [1, 2, 3].forEach(n => {
        setStepState(n, 'pending');
        updateStepUI(n, 0, '대기 중...', '');
    });

    // 결과 숨기기
    resultSection.style.display = 'none';

    clearFile();
    window.scrollTo({ top: 0, behavior: 'smooth' });
}
