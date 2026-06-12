// ============================================
// jobs.js — 다중 작업 큐 매니저 (최대 3개 동시 처리)
// 워크플로우: 업로드 → STT → 요약, 작업당 카드 1장
// ============================================

const MAX_CONCURRENT_JOBS = 3;
const jobsById = new Map();         // jobId -> job
let nextJobId = 1;

function genJobId() {
    return `job-${nextJobId++}`;
}

function getActiveJobs() {
    return [...jobsById.values()].filter(j =>
        ['queued', 'uploading', 'stt', 'summarizing'].includes(j.status)
    );
}

function getActiveJobCount() {
    return getActiveJobs().length;
}

async function handleConvert() {
    if (!selectedFiles.length) return;

    // AI 모델만 공통 — 프로젝트는 파일마다 선택 (하루에 여러 프로젝트 회의 가능)
    const gptSelect = document.getElementById('gptModelUpload');
    const mergeMode = !!(document.getElementById('mergeFilesCheckbox')?.checked) && selectedFiles.length >= 2;

    const commonOptions = {
        gptModel: gptSelect.value,
        gptModelName: gptSelect.options[gptSelect.selectedIndex].text.split(' - ')[0],
    };

    // 파일 메타 → 작업 옵션 (프로젝트: 기존 선택이면 id, 새로 만들기면 이름)
    const metaToOptions = (meta) => ({
        meetingTitle: meta.meetingTitle || '',
        attendees: meta.attendees || '',
        projectId: (meta.projectId && meta.projectId !== '__new__') ? meta.projectId : null,
        projectName: meta.projectId === '__new__' ? (meta.newProjectName || '').trim() : '',
    });

    if (mergeMode) {
        // 합치기 모드: 1개 job, 첫 번째 파일의 메타·프로젝트 사용
        const primaryMeta = fileMetas[0] || {};
        const job = makeJob([...selectedFiles], [...audioDurations], { ...commonOptions, ...metaToOptions(primaryMeta) }, true);
        jobsById.set(job.id, job);
        renderJobCard(job);
    } else {
        // 일반 모드: 파일마다 별도 job + 각자의 메타·프로젝트
        selectedFiles.forEach((f, i) => {
            const meta = fileMetas[i] || {};
            const job = makeJob([f], [audioDurations[i] || 0], { ...commonOptions, ...metaToOptions(meta) }, false);
            jobsById.set(job.id, job);
            renderJobCard(job);
        });
    }

    refreshJobQueueCount();

    // 폼 초기화 (파일만, 프로젝트/AI 모델은 유지 — 연속 업로드 편의)
    clearFile();

    runJobQueue();

    // 화면 이동 없음 — 처리는 우측 하단 도크에서 백그라운드로 진행된다.
    // 사용자는 새 파일을 더 올리거나 다른 화면으로 자유롭게 이동할 수 있다.
    ensureDockVisible();
    setDockExpanded(true);
    const startedCount = getActiveJobCount();
    showToast(
        startedCount > 1
            ? `${startedCount}개 회의록을 백그라운드에서 처리 중이에요. 완료되면 알려드릴게요.`
            : '백그라운드에서 처리를 시작했어요. 완료되면 알려드릴게요.',
        { type: 'info', duration: 5000 }
    );
}

function makeJob(files, durations, options, mergeMode) {
    const totalSize = files.reduce((s, f) => s + f.size, 0);
    const totalDuration = (durations || []).reduce((s, d) => s + (d || 0), 0);
    const primary = files[0];
    return {
        id: genJobId(),
        mergeMode,
        files,
        durations,
        totalSize,
        totalDuration,
        displayName: mergeMode && files.length > 1
            ? `${primary.name} 외 ${files.length - 1}개 (합침)`
            : primary.name,
        status: 'queued',         // queued | uploading | stt | summarizing | done | failed | canceled
        progress: 0,
        stage: null,
        transcriptId: null,
        transcript: null,
        summary: null,
        summaryId: null,
        timestamp: null,
        options,
        xhr: null,
        sttProgress: null,
        summaryProgress: null,
        error: null,
        cardEl: null,
    };
}

// 큐 러너: 활성 작업이 한도 미만이고 queued가 있으면 다음 작업 시작
function runJobQueue() {
    while (getActiveRunningCount() < MAX_CONCURRENT_JOBS) {
        const next = [...jobsById.values()].find(j => j.status === 'queued');
        if (!next) break;
        // 'queued' 상태에서 즉시 'uploading'으로 전환되지 않으면 같은 작업이 다시 잡힘
        next.status = 'uploading';
        startJob(next).catch(err => console.error(`Job ${next.id} 실패:`, err));
    }
}

function getActiveRunningCount() {
    return [...jobsById.values()].filter(j =>
        ['uploading', 'stt', 'summarizing'].includes(j.status)
    ).length;
}

async function startJob(job) {
    try {
        await jobUploadAndSTT(job);
        if (job.status === 'canceled') return;
        await jobSummarize(job);
        if (job.status === 'canceled') return;

        job.status = 'done';
        job.progress = 100;
        if (job.summaryId) doneUnviewed.add(job.summaryId);
        updateJobCard(job, { status: '회의록 생성 완료! 이메일로도 보내드렸어요.', pct: 100, state: 'done', stage: 'summarize', stageDone: true });
        fetchUsageInfo();
        announceJobDone(job);
        // 이메일은 서버가 자동 발송 (수정하러 가기 딥링크 포함)
    } catch (error) {
        if (job.status === 'canceled') return;
        job.status = 'failed';
        job.error = error.message || '알 수 없는 오류';
        updateJobCard(job, { status: '실패', state: 'failed', error: job.error });
        showToast(`"${job.displayName}" 처리에 실패했어요: ${job.error}`, { type: 'error', duration: 8000 });
    } finally {
        refreshJobQueueCount();
        // 슬롯이 비었으니 큐에 대기 중인 다음 작업을 시작
        runJobQueue();
    }
}

function jobUploadAndSTT(job) {
    return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        job.xhr = xhr;
        job.status = 'uploading';
        job.stage = 'upload';
        const initStatus = job.mergeMode
            ? `업로드 시작... (${job.files.length}개 파트)`
            : '업로드 시작...';
        updateJobCard(job, { status: initStatus, pct: 0, state: 'running', stage: 'upload' });

        xhr.upload.addEventListener('progress', (e) => {
            if (!e.lengthComputable) return;
            const pct = (e.loaded / e.total) * 50; // 업로드는 전체의 0~50%
            updateJobCard(job, { status: '파일 업로드 중...', pct, state: 'running', stage: 'upload' });
        });

        xhr.upload.addEventListener('load', () => {
            job.status = 'stt';
            job.stage = 'stt';
            const sttLabel = job.mergeMode
                ? `음성→텍스트 변환 중... (${job.files.length}개 순차)`
                : '음성→텍스트 변환 중...';
            updateJobCard(job, { status: sttLabel, pct: 50, state: 'running', stage: 'stt', stageDone: 'upload' });

            // STT 진행률 50%→90%. 합치기 모드는 총 길이 기준이라 자연스럽게 길어짐.
            const estMs = job.totalDuration > 0
                ? job.totalDuration * ESTIMATION.stt_ratio * 1000
                : (job.totalSize / (1024 * 1024)) * 4000;
            const sttProgress = new RealisticProgress(Math.max(estMs, 3000), (pct) => {
                const mapped = 50 + (pct / 100) * 40;
                updateJobCard(job, { status: sttLabel, pct: mapped, state: 'running', stage: 'stt' });
            });
            sttProgress.start();
            job.sttProgress = sttProgress;
        });

        xhr.addEventListener('load', () => {
            if (job.sttProgress) job.sttProgress.complete();
            if (xhr.status >= 200 && xhr.status < 300) {
                const data = JSON.parse(xhr.responseText);
                job.transcriptId = data.transcript_id;
                job.transcript = data.transcript;
                job.timestamp = data.timestamp;
                resolve();
            } else {
                let errorMsg = '처리 중 오류가 발생했습니다';
                try {
                    const errorData = JSON.parse(xhr.responseText);
                    errorMsg = errorData.detail || errorMsg;
                } catch {}
                if (xhr.status === 429) {
                    errorMsg = errorMsg || '동시 처리 한도 초과';
                }
                reject(new Error(errorMsg));
            }
        });

        xhr.addEventListener('error', () => {
            if (job.sttProgress) job.sttProgress.stop();
            reject(new Error('네트워크 오류가 발생했습니다'));
        });

        xhr.addEventListener('abort', () => {
            if (job.sttProgress) job.sttProgress.stop();
            reject(new Error('취소됨'));
        });

        const formData = new FormData();

        if (job.mergeMode) {
            // /transcribe-merge: files[] 다중 + 길이/크기 쉼표 구분
            job.files.forEach(f => formData.append('files', f));
            formData.append('audio_durations', job.durations.map(d => d || 0).join(','));
            formData.append('file_sizes', job.files.map(f => f.size).join(','));
        } else {
            // 단일 파일: 기존 /transcribe-only
            formData.append('file', job.files[0]);
            formData.append('whisper_model', 'base');
            formData.append('audio_duration', job.durations[0] || 0);
            formData.append('file_size', job.files[0].size);
        }

        if (job.options.projectId) {
            formData.append('project_id', job.options.projectId);
        } else if (job.options.projectName) {
            formData.append('project_name', job.options.projectName);
        } else if (!job.mergeMode) {
            formData.append('project_name', '');
        }
        formData.append('meeting_title', job.options.meetingTitle);
        formData.append('attendees', job.options.attendees);

        const endpoint = job.mergeMode ? '/transcribe-merge' : '/transcribe-only';
        xhr.open('POST', `${API_BASE_URL}${endpoint}`);
        if (accessToken) xhr.setRequestHeader('Authorization', `Bearer ${accessToken}`);
        xhr.send(formData);
    });
}

async function jobSummarize(job) {
    job.status = 'summarizing';
    job.stage = 'summarize';

    const transcriptLength = (job.transcript || '').length;
    const estimatedTokensK = transcriptLength / 1500;
    const coeff = ESTIMATION.summary[job.options.gptModel] || ESTIMATION.summary_default;
    const estimatedMs = (coeff.base + coeff.rate * estimatedTokensK) * 1000 * 1.3;

    const summaryProgress = new RealisticProgress(estimatedMs, (pct) => {
        const mapped = 90 + (pct / 100) * 10; // 90~100%
        updateJobCard(job, {
            status: `${job.options.gptModelName}로 회의록 생성 중...`,
            pct: mapped,
            state: 'running',
            stage: 'summarize',
            stageDone: 'stt',
        });
    });
    summaryProgress.start();
    job.summaryProgress = summaryProgress;

    try {
        const formData = new FormData();
        formData.append('transcript_id', job.transcriptId);
        formData.append('gpt_model', job.options.gptModel);
        formData.append('save_files', 'true');
        formData.append('return_file', 'false');

        const response = await authFetch(`${API_BASE_URL}/summarize`, { method: 'POST', body: formData });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || '처리 중 오류가 발생했습니다');
        }
        const data = await response.json();

        summaryProgress.complete();
        job.summary = data.summary;
        job.summaryId = data.summary_id;
    } catch (error) {
        summaryProgress.stop();
        throw error;
    }
}

// 작업 카드 UI 렌더링
function renderJobCard(job) {
    const list = document.getElementById('dockJobList');
    const tpl = document.getElementById('jobCardTemplate');
    if (!list || !tpl) return;

    const node = tpl.content.firstElementChild.cloneNode(true);
    node.dataset.jobId = job.id;
    node.querySelector('.job-card-filename').textContent = job.displayName;

    // 'queued' 초기 상태일 때 친절한 메시지 표시 (슬롯 비면 자동 시작)
    if (job.status === 'queued') {
        node.querySelector('.job-card-status').textContent = '대기 중 — 슬롯이 비면 자동으로 시작됩니다';
    }

    node.querySelector('[data-action="cancel"]').addEventListener('click', () => cancelJob(job));
    node.querySelector('[data-action="view"]').addEventListener('click', () => viewJobResult(job));
    node.querySelector('[data-action="retry"]').addEventListener('click', () => retryJob(job));

    list.appendChild(node);
    job.cardEl = node;
    ensureDockVisible();
}

function updateJobCard(job, { status, pct, state, stage, stageDone, error }) {
    if (!job.cardEl) return;
    const card = job.cardEl;

    if (status !== undefined) card.querySelector('.job-card-status').textContent = status;
    if (pct !== undefined) {
        const fill = card.querySelector('.job-card-progress-fill');
        const pctEl = card.querySelector('.job-card-progress-pct');
        const clamped = Math.max(0, Math.min(100, pct));
        fill.style.width = clamped + '%';
        pctEl.textContent = Math.round(clamped) + '%';
    }
    if (state) card.dataset.state = state;

    // 단계별 표시: stage = 현재 활성 단계, stageDone = 끝난 단계 (또는 true면 stage까지 모두 완료)
    if (stage || stageDone) {
        const order = ['upload', 'stt', 'summarize'];
        const activeIdx = stage ? order.indexOf(stage) : -1;
        let doneIdx = -1;
        if (stageDone === true) doneIdx = activeIdx; // stage까지 완료
        else if (typeof stageDone === 'string') doneIdx = order.indexOf(stageDone);

        order.forEach((s, i) => {
            const stepEl = card.querySelector(`.job-card-step[data-step="${s}"]`);
            if (!stepEl) return;
            stepEl.dataset.active = (i === activeIdx && i > doneIdx) ? 'true' : 'false';
            stepEl.dataset.done = (i <= doneIdx) ? 'true' : 'false';
        });
    }

    if (error !== undefined) {
        const errEl = card.querySelector('.job-card-error');
        if (error) {
            errEl.hidden = false;
            errEl.textContent = error;
        } else {
            errEl.hidden = true;
        }
    }

    // 액션 버튼 상태: 진행/대기 → 취소 / 완료 → 보기 / 실패·취소 → 다시 시도 + 닫기
    const viewBtn = card.querySelector('[data-action="view"]');
    const retryBtn = card.querySelector('[data-action="retry"]');
    const cancelBtn = card.querySelector('[data-action="cancel"]');
    if (state === 'done') {
        if (viewBtn) viewBtn.hidden = false;
        if (retryBtn) retryBtn.hidden = true;
        if (cancelBtn) cancelBtn.hidden = true;
    } else if (state === 'failed' || state === 'canceled') {
        if (viewBtn) viewBtn.hidden = true;
        if (retryBtn) retryBtn.hidden = false;
        if (cancelBtn) {
            // 닫기(제거) 버튼으로 전환
            cancelBtn.hidden = false;
            cancelBtn.title = '카드 제거';
        }
    } else if (state === 'running' || state === 'pending') {
        // 재시도로 다시 진행 중이 된 경우 버튼 원상복구
        if (viewBtn) viewBtn.hidden = true;
        if (retryBtn) retryBtn.hidden = true;
        if (cancelBtn) {
            cancelBtn.hidden = false;
            cancelBtn.title = '취소';
        }
    }
}

function refreshJobQueueCount() {
    const active = getActiveJobCount();
    // 도크 알약/요약 상태 갱신 (비면 자동 숨김)
    updateDockSummary(active);
    // 내 회의록 네비 배지(완료·미열람) + 목록 상단 처리 중 배너
    updateDashboardBadge();
    if (typeof renderDashboardProcessingBanner === 'function') renderDashboardProcessingBanner();
}

function cancelJob(job) {
    // 완료/실패 카드의 닫기 동작: 카드 제거
    if (['done', 'failed', 'canceled'].includes(job.status)) {
        removeJobCard(job);
        return;
    }

    // 'queued' 상태에서 취소: 그냥 카드 제거 (아직 슬롯 점유 안 함)
    if (job.status === 'queued') {
        removeJobCard(job);
        return;
    }

    job.status = 'canceled';
    if (job.xhr) {
        try { job.xhr.abort(); } catch {}
    }
    if (job.sttProgress) job.sttProgress.stop();
    if (job.summaryProgress) job.summaryProgress.stop();
    updateJobCard(job, { status: '취소됨', state: 'canceled', error: null });
    refreshJobQueueCount();
    // 슬롯이 비었으니 대기 중인 다음 작업 시작
    runJobQueue();
}

function removeJobCard(job) {
    if (job.cardEl && job.cardEl.parentNode) {
        job.cardEl.parentNode.removeChild(job.cardEl);
    }
    jobsById.delete(job.id);
    refreshJobQueueCount();
}

// 작업 완료 알림: 회의록은 리스트에 읽지 않음으로 쌓이고, 이메일도 자동 발송됨
function announceJobDone(job) {
    showToast(`"${job.displayName}" 회의록이 완성됐어요. 이메일로도 보내드렸습니다.`, {
        type: 'success',
        duration: 10000,
        actionLabel: '바로 보기',
        onAction: () => viewJobResult(job),
    });
    // 내 회의록 목록을 보고 있으면 새 회의록이 바로 뜨도록 갱신
    if (currentView === 'dashboard' && typeof loadDashboard === 'function') {
        loadDashboard(dashboardQuery, dashboardPage);
    }
}

// 완료된 작업의 회의록 열기 — 상세/편집 페이지로 (서버 조회로 읽음 처리까지)
async function viewJobResult(job) {
    if (job.status !== 'done' || !job.summaryId) return;
    openSummaryFromDashboard(job.summaryId);
}

function showJobToast(job, message) {
    showToast(`${job.displayName} — ${message}`, { type: 'info', duration: 6000 });
}

// ============================================
// 처리 도크 (전역, 모든 화면 위) — 백그라운드 처리 ambient 표시
// ============================================

// 이번 세션에서 완료됐지만 아직 열어보지 않은 회의록 (내 회의록 배지 카운트)
const doneUnviewed = new Set();

function getDockEls() {
    return {
        dock: document.getElementById('procDock'),
        pill: document.getElementById('procDockPill'),
        pillText: document.getElementById('procDockPillText'),
        panel: document.getElementById('procDockPanel'),
        clearBtn: document.getElementById('procDockClear'),
    };
}

function ensureDockVisible() {
    const { dock } = getDockEls();
    if (dock) dock.hidden = false;
}

function setDockExpanded(expanded) {
    const { dock, pill, panel } = getDockEls();
    if (!dock || !panel || !pill) return;
    panel.hidden = !expanded;
    pill.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    dock.classList.toggle('is-expanded', expanded);
}

function toggleDock() {
    const { panel } = getDockEls();
    if (!panel) return;
    setDockExpanded(panel.hidden); // 접혀(숨김) 있으면 펼친다
}

// 도크 컨트롤 이벤트 바인딩 (main.js 부트스트랩에서 1회 호출)
function initDock() {
    const { pill } = getDockEls();
    const collapseBtn = document.getElementById('procDockCollapse');
    const clearBtn = document.getElementById('procDockClear');
    if (pill) pill.addEventListener('click', toggleDock);
    if (collapseBtn) collapseBtn.addEventListener('click', (e) => { e.stopPropagation(); setDockExpanded(false); });
    if (clearBtn) clearBtn.addEventListener('click', clearFinishedJobs);
}

// 도크 알약/요약 상태 갱신 — 카드가 하나도 없으면 도크 자체를 숨김
function updateDockSummary(active) {
    const { dock, pill, pillText, clearBtn } = getDockEls();
    if (!dock || !pill || !pillText) return;

    if (jobsById.size === 0) {
        dock.hidden = true;
        setDockExpanded(false);
        dock.classList.remove('is-active', 'is-idle');
        return;
    }
    dock.hidden = false;

    const finished = [...jobsById.values()].filter(j => ['done', 'failed', 'canceled'].includes(j.status));
    const hasActive = active > 0;
    dock.classList.toggle('is-active', hasActive);
    dock.classList.toggle('is-idle', !hasActive);

    if (hasActive) {
        pillText.textContent = `${active}개 처리 중`;
    } else {
        const doneCount = finished.filter(j => j.status === 'done').length;
        const failCount = finished.filter(j => j.status !== 'done').length;
        if (failCount > 0 && doneCount > 0) pillText.textContent = `완료 ${doneCount} · 실패 ${failCount}`;
        else if (failCount > 0) pillText.textContent = `${failCount}개 처리 실패`;
        else pillText.textContent = `${doneCount}개 완료`;
    }

    // "완료 항목 지우기": 끝난 작업이 있을 때만 노출
    if (clearBtn) clearBtn.hidden = finished.length === 0;
}

// 완료/실패/취소된 카드 일괄 제거
function clearFinishedJobs() {
    [...jobsById.values()]
        .filter(j => ['done', 'failed', 'canceled'].includes(j.status))
        .forEach(j => removeJobCard(j));
    refreshJobQueueCount();
}

// 내 회의록 네비 배지 — 완료했지만 아직 열어보지 않은 수
function updateDashboardBadge() {
    const badge = document.getElementById('navDashboardBadge');
    if (!badge) return;
    const n = doneUnviewed.size;
    badge.textContent = String(n);
    badge.hidden = n === 0;
}

// 회의록을 열었을 때 호출 — 배지에서 제거 + 도크의 해당 완료 카드 정리
function markSummaryViewed(summaryId) {
    const id = Number(summaryId);
    if (doneUnviewed.has(id)) {
        doneUnviewed.delete(id);
        updateDashboardBadge();
    }
    const job = [...jobsById.values()].find(j => Number(j.summaryId) === id && j.status === 'done');
    if (job) removeJobCard(job);
}

// 실패/취소 작업 재시도 — 파일이 메모리에 남아있어 재실행 가능
function retryJob(job) {
    if (!['failed', 'canceled'].includes(job.status)) return;
    job.status = 'queued';
    job.error = null;
    job.progress = 0;
    job.stage = null;
    job.xhr = null;
    job.transcriptId = null;
    job.transcript = null;
    job.summary = null;
    job.summaryId = null;
    updateJobCard(job, { status: '대기 중 — 곧 다시 시작합니다', pct: 0, state: 'pending', error: null });
    refreshJobQueueCount();
    runJobQueue();
}
