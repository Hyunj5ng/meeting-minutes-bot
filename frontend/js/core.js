// ============================================
// core.js — 상수, 전역 상태, 공용 유틸
// 모든 스크립트보다 먼저 로드되어야 한다 (index.html 로드 순서 참고)
// ============================================

// API 엔드포인트 설정 — 같은 서버에서 서빙되므로 상대 경로 사용
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

// ============================================
// 전역 상태
// ============================================

// 업로드 폼 상태
let selectedFiles = [];      // 업로드 대기 중인 파일들 (다중 선택 지원)
let audioDurations = [];     // 각 파일의 오디오 길이 (초). selectedFiles와 인덱스 동기화
let fileMetas = [];          // 각 파일의 회의 정보 {meetingTitle, attendees}. selectedFiles와 인덱스 동기화

// 결과 화면 상태
let resultData = null;
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

// DOM 요소 (로그인 후 main.js의 initDomElements에서 초기화)
let uploadArea, fileInput;
let convertBtn, resultSection, copyBtn, resetBtn;

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

function escapeHtml(s) {
    return String(s ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function escapeAttr(s) {
    return String(s ?? '')
        .replace(/&/g, '&amp;')
        .replace(/"/g, '&quot;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
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

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
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
