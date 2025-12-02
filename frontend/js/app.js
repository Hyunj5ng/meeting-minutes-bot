// API 엔드포인트 설정
const API_BASE_URL = 'http://localhost:8000';

// 전역 변수
let selectedFile = null;
let transcriptData = null;
let resultData = null;

// DOM 요소
const uploadArea = document.getElementById('uploadArea');
const fileInput = document.getElementById('fileInput');
const fileInfo = document.getElementById('fileInfo');
const fileName = document.getElementById('fileName');
const fileSize = document.getElementById('fileSize');
const removeFileBtn = document.getElementById('removeFile');
const convertBtn = document.getElementById('convertBtn');
const progressSection = document.getElementById('progressSection');
const reviewSection = document.getElementById('reviewSection');
const summaryProgressSection = document.getElementById('summaryProgressSection');
const resultSection = document.getElementById('resultSection');
const downloadBtn = document.getElementById('downloadBtn');
const resetBtn = document.getElementById('resetBtn');
const proceedBtn = document.getElementById('proceedBtn');
const cancelBtn = document.getElementById('cancelBtn');

// 초기화
document.addEventListener('DOMContentLoaded', () => {
    setupEventListeners();
});

// 이벤트 리스너 설정
function setupEventListeners() {
    // 파일 업로드 관련
    uploadArea.addEventListener('click', () => fileInput.click());
    uploadArea.addEventListener('dragover', handleDragOver);
    uploadArea.addEventListener('dragleave', handleDragLeave);
    uploadArea.addEventListener('drop', handleDrop);
    fileInput.addEventListener('change', handleFileSelect);
    removeFileBtn.addEventListener('click', clearFile);

    // 변환 버튼 (STT만)
    convertBtn.addEventListener('click', handleConvert);

    // 리뷰 섹션 버튼
    proceedBtn.addEventListener('click', handleSummarize);
    cancelBtn.addEventListener('click', reset);

    // 결과 관련
    downloadBtn.addEventListener('click', downloadResult);
    resetBtn.addEventListener('click', reset);

    // 탭 전환
    const tabs = document.querySelectorAll('.tab');
    tabs.forEach(tab => {
        tab.addEventListener('click', () => switchTab(tab.dataset.tab));
    });
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
function handleFile(file) {
    // 파일 형식 검증
    const allowedTypes = ['audio/mpeg', 'audio/wav', 'audio/m4a', 'audio/ogg', 'audio/flac', 'audio/aac'];
    const allowedExtensions = ['.mp3', '.wav', '.m4a', '.ogg', '.flac', '.aac'];

    const fileExtension = '.' + file.name.split('.').pop().toLowerCase();

    if (!allowedExtensions.includes(fileExtension)) {
        alert('지원하지 않는 파일 형식입니다.\n지원 형식: MP3, WAV, M4A, OGG, FLAC, AAC');
        return;
    }

    selectedFile = file;

    // 파일 정보 표시
    fileName.textContent = file.name;
    fileSize.textContent = formatFileSize(file.size);

    uploadArea.style.display = 'none';
    fileInfo.style.display = 'flex';
    convertBtn.disabled = false;
}

// 파일 크기 포맷팅
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

// 파일 제거
function clearFile() {
    selectedFile = null;
    fileInput.value = '';
    uploadArea.style.display = 'block';
    fileInfo.style.display = 'none';
    convertBtn.disabled = true;
}

// STT 변환 (1단계)
async function handleConvert() {
    if (!selectedFile) return;

    // UI 상태 변경
    document.querySelector('.upload-section').style.display = 'none';
    progressSection.style.display = 'block';

    // 진행 단계 초기화
    updateProgress(0);
    updateStepProgress(1, 0, 'active', '업로드 중...');
    updateStepProgress(2, 0, '', '대기 중...');

    try {
        // FormData 생성
        const formData = new FormData();
        formData.append('file', selectedFile);
        formData.append('whisper_model', document.getElementById('whisperModel').value);

        // 1단계: 업로드 (0-50%)
        updateStepProgress(1, 10, 'active', '파일 업로드 중...');
        updateProgress(10);

        await simulateProgress(1, 10, 40, 1000); // 1초 동안 10%에서 40%로
        updateProgress(40);

        // API 호출 시작
        updateStepProgress(1, 50, 'active', '서버로 전송 중...');
        updateProgress(45);

        const response = await fetch(`${API_BASE_URL}/transcribe-only`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || '처리 중 오류가 발생했습니다');
        }

        // 업로드 완료
        updateStepProgress(1, 100, 'completed', '완료!');
        updateProgress(50);

        // 2단계: STT (50-100%)
        updateStepProgress(2, 10, 'active', '음성 분석 중...');
        updateProgress(55);

        // 응답 대기 중 진행률 시뮬레이션
        const progressInterval = simulateStepProgress(2, 10, 90, 100);

        const data = await response.json();
        transcriptData = data;

        clearInterval(progressInterval);

        // STT 완료
        updateStepProgress(2, 100, 'completed', '완료!');
        updateProgress(100);

        // 리뷰 섹션으로 이동
        await new Promise(resolve => setTimeout(resolve, 500));
        showReview(data.transcript);

    } catch (error) {
        console.error('Error:', error);
        alert('오류가 발생했습니다: ' + error.message);
        reset();
    }
}

// 리뷰 화면 표시
function showReview(transcript) {
    progressSection.style.display = 'none';
    reviewSection.style.display = 'block';

    // 변환된 텍스트 표시
    document.getElementById('reviewTranscriptText').textContent = transcript;

    // 스크롤을 리뷰 섹션으로 이동
    reviewSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// 회의록 생성 (2단계)
async function handleSummarize() {
    if (!transcriptData) return;

    // UI 상태 변경
    reviewSection.style.display = 'none';
    summaryProgressSection.style.display = 'block';

    // 진행 단계 초기화
    updateSummaryProgress(0);
    updateSummaryStepProgress(10, 'active', 'GPT로 회의록 생성 중...');

    try {
        // FormData 생성
        const formData = new FormData();
        formData.append('transcript', transcriptData.transcript);
        formData.append('gpt_model', document.getElementById('gptModelReview').value);
        formData.append('save_files', document.getElementById('saveFilesReview').checked);
        formData.append('return_file', 'false');

        updateSummaryProgress(20);

        // 진행률 시뮬레이션
        const progressInterval = simulateSummaryStepProgress(20, 80, 100);

        // API 호출
        const response = await fetch(`${API_BASE_URL}/summarize`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || '처리 중 오류가 발생했습니다');
        }

        const data = await response.json();
        resultData = {
            ...transcriptData,
            summary: data.summary
        };

        clearInterval(progressInterval);

        // 완료
        updateSummaryStepProgress(100, 'completed', '완료!');
        updateSummaryProgress(100);

        // 결과 표시
        await new Promise(resolve => setTimeout(resolve, 500));
        showResult(resultData);

    } catch (error) {
        console.error('Error:', error);
        alert('오류가 발생했습니다: ' + error.message);
        reset();
    }
}

// 전체 진행률 업데이트
function updateProgress(percentage) {
    const progressBar = document.getElementById('overallProgressBar');
    const progressText = document.getElementById('overallProgress');

    progressBar.style.width = percentage + '%';
    progressText.textContent = Math.round(percentage) + '%';
}

// 단계별 진행률 업데이트
function updateStepProgress(stepNumber, percentage, status, statusText) {
    const step = document.getElementById(`step${stepNumber}`);
    const stepStatus = step.querySelector('.step-status');
    const stepProgressBar = document.getElementById(`step${stepNumber}ProgressBar`);
    const stepProgressText = document.getElementById(`step${stepNumber}Progress`);

    step.className = 'step';
    if (status) {
        step.classList.add(status);
    }

    stepStatus.textContent = statusText;
    stepProgressBar.style.width = percentage + '%';
    stepProgressText.textContent = Math.round(percentage) + '%';
}

// 진행률 시뮬레이션 (부드러운 증가)
async function simulateProgress(stepNumber, fromPercent, toPercent, duration) {
    const steps = 20;
    const increment = (toPercent - fromPercent) / steps;
    const delay = duration / steps;

    for (let i = 0; i <= steps; i++) {
        const currentPercent = fromPercent + (increment * i);
        const stepProgressBar = document.getElementById(`step${stepNumber}ProgressBar`);
        const stepProgressText = document.getElementById(`step${stepNumber}Progress`);

        stepProgressBar.style.width = currentPercent + '%';
        stepProgressText.textContent = Math.round(currentPercent) + '%';

        await new Promise(resolve => setTimeout(resolve, delay));
    }
}

// 단계 진행률 시뮬레이션 (인터벌)
function simulateStepProgress(stepNumber, fromPercent, toPercent, duration) {
    const startTime = Date.now();
    const totalTime = duration;

    return setInterval(() => {
        const elapsed = Date.now() - startTime;
        const progress = Math.min(elapsed / totalTime, 1);
        const currentPercent = fromPercent + (toPercent - fromPercent) * progress;

        const stepProgressBar = document.getElementById(`step${stepNumber}ProgressBar`);
        const stepProgressText = document.getElementById(`step${stepNumber}Progress`);

        if (stepProgressBar && stepProgressText) {
            stepProgressBar.style.width = currentPercent + '%';
            stepProgressText.textContent = Math.round(currentPercent) + '%';
        }
    }, 100);
}

// 진행 단계 업데이트
function updateStep(stepNumber, status, statusText) {
    const step = document.getElementById(`step${stepNumber}`);
    const stepStatus = step.querySelector('.step-status');

    step.className = 'step';
    if (status) {
        step.classList.add(status);
    }

    stepStatus.textContent = statusText;
}

// 요약 전체 진행률 업데이트
function updateSummaryProgress(percentage) {
    const progressBar = document.getElementById('summaryOverallProgressBar');
    const progressText = document.getElementById('summaryOverallProgress');

    progressBar.style.width = percentage + '%';
    progressText.textContent = Math.round(percentage) + '%';
}

// 요약 단계 진행률 업데이트
function updateSummaryStepProgress(percentage, status, statusText) {
    const step = document.getElementById('summaryStep');
    const stepStatus = step.querySelector('.step-status');
    const stepProgressBar = document.getElementById('summaryStepProgressBar');
    const stepProgressText = document.getElementById('summaryStepProgress');

    step.className = 'step';
    if (status) {
        step.classList.add(status);
    }

    stepStatus.textContent = statusText;
    stepProgressBar.style.width = percentage + '%';
    stepProgressText.textContent = Math.round(percentage) + '%';
}

// 요약 진행률 시뮬레이션 (인터벌)
function simulateSummaryStepProgress(fromPercent, toPercent, duration) {
    const startTime = Date.now();
    const totalTime = duration;

    return setInterval(() => {
        const elapsed = Date.now() - startTime;
        const progress = Math.min(elapsed / totalTime, 1);
        const currentPercent = fromPercent + (toPercent - fromPercent) * progress;

        const stepProgressBar = document.getElementById('summaryStepProgressBar');
        const stepProgressText = document.getElementById('summaryStepProgress');

        if (stepProgressBar && stepProgressText) {
            stepProgressBar.style.width = currentPercent + '%';
            stepProgressText.textContent = Math.round(currentPercent) + '%';
        }

        // 전체 진행률도 업데이트
        updateSummaryProgress(currentPercent);
    }, 100);
}

// 결과 표시
function showResult(data) {
    progressSection.style.display = 'none';
    summaryProgressSection.style.display = 'none';
    resultSection.style.display = 'block';

    // 마크다운 설정
    marked.setOptions({
        breaks: true,
        gfm: true,
        headerIds: false,
        mangle: false
    });

    // 회의록을 마크다운으로 렌더링
    const summaryElement = document.getElementById('summaryText');
    summaryElement.innerHTML = marked.parse(data.summary);

    // 원본 텍스트 표시 (일반 텍스트)
    document.getElementById('transcriptText').textContent = data.transcript;

    // 스크롤을 결과로 이동
    resultSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// 탭 전환
function switchTab(tabName) {
    // 탭 버튼 활성화
    const tabs = document.querySelectorAll('.tab');
    tabs.forEach(tab => {
        if (tab.dataset.tab === tabName) {
            tab.classList.add('active');
        } else {
            tab.classList.remove('active');
        }
    });

    // 탭 컨텐츠 표시
    const contents = document.querySelectorAll('.tab-content');
    contents.forEach(content => {
        if (content.id === tabName + 'Content') {
            content.classList.add('active');
        } else {
            content.classList.remove('active');
        }
    });
}

// 결과 다운로드
async function downloadResult() {
    if (!transcriptData || !resultData) return;

    try {
        // FormData 생성
        const formData = new FormData();
        formData.append('transcript', transcriptData.transcript);
        formData.append('gpt_model', document.getElementById('gptModelReview').value);
        formData.append('save_files', 'true');
        formData.append('return_file', 'true');

        // 다운로드 버튼 상태 변경
        const originalText = downloadBtn.innerHTML;
        downloadBtn.innerHTML = '<svg class="animate-spin" width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M10 2V6M10 14V18M18 10H14M6 10H2" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg> 다운로드 중...';
        downloadBtn.disabled = true;

        // API 호출
        const response = await fetch(`${API_BASE_URL}/summarize`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            throw new Error('다운로드 중 오류가 발생했습니다');
        }

        // 파일 다운로드
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `meeting_minutes_${new Date().toISOString().slice(0, 10)}.txt`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);

        // 버튼 복원
        downloadBtn.innerHTML = originalText;
        downloadBtn.disabled = false;

    } catch (error) {
        console.error('Download error:', error);
        alert('다운로드 중 오류가 발생했습니다: ' + error.message);
        downloadBtn.innerHTML = originalText;
        downloadBtn.disabled = false;
    }
}

// 리셋
function reset() {
    selectedFile = null;
    transcriptData = null;
    resultData = null;
    fileInput.value = '';

    document.querySelector('.upload-section').style.display = 'block';
    progressSection.style.display = 'none';
    reviewSection.style.display = 'none';
    summaryProgressSection.style.display = 'none';
    resultSection.style.display = 'none';

    clearFile();

    // 스크롤을 맨 위로
    window.scrollTo({ top: 0, behavior: 'smooth' });
}
