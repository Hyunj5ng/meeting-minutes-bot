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
let currentSummaryMarkdown = ''; // 현재 요약 마크다운 원본
let isEditMode = false;

// 인증 상태
let currentUser = null;
let accessToken = null;

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
    if (accessToken) {
        verifyToken();
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
        currentUser = data.user;
        localStorage.setItem('access_token', accessToken);

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
        } else {
            localStorage.removeItem('access_token');
            accessToken = null;
            showLoginSection();
        }
    } catch {
        localStorage.removeItem('access_token');
        accessToken = null;
        showLoginSection();
    }
}

function logout() {
    localStorage.removeItem('access_token');
    accessToken = null;
    currentUser = null;
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

    // 사용량 바 즉시 표시
    document.getElementById('usageBar').style.display = 'flex';

    // DOM 요소 초기화
    initDomElements();
    setupEventListeners();
    fetchUsageInfo();
}

// 인증된 fetch 래퍼
async function authFetch(url, options = {}) {
    if (!options.headers) {
        options.headers = {};
    }
    if (accessToken) {
        options.headers['Authorization'] = `Bearer ${accessToken}`;
    }

    const res = await fetch(url, options);

    if (res.status === 401) {
        logout();
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
    formData.append('project_name', document.getElementById('projectName').value);
    formData.append('meeting_title', document.getElementById('meetingTitle').value);
    formData.append('attendees', document.getElementById('attendees').value);
    formData.append('keywords', document.getElementById('keywords').value);

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

        // 결과 표시
        await new Promise(resolve => setTimeout(resolve, 500));
        showResult(resultData);

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
            복사 완���!`;
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
