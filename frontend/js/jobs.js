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

    // 프로젝트 + AI 모델은 모든 파일 공통
    const projectSelectEl = document.getElementById('projectSelect');
    const projectNameInput = document.getElementById('projectName');
    const selectedProjectVal = projectSelectEl ? projectSelectEl.value : '';
    const gptSelect = document.getElementById('gptModelUpload');
    const mergeMode = !!(document.getElementById('mergeFilesCheckbox')?.checked) && selectedFiles.length >= 2;

    const commonOptions = {
        projectId: (selectedProjectVal && selectedProjectVal !== '__new__') ? selectedProjectVal : null,
        projectName: (selectedProjectVal === '__new__' && projectNameInput) ? projectNameInput.value.trim() : '',
        gptModel: gptSelect.value,
        gptModelName: gptSelect.options[gptSelect.selectedIndex].text.split(' - ')[0],
        autoEmail: document.getElementById('autoEmailCheckbox')?.checked || false,
    };

    const queueCard = document.getElementById('jobQueueCard');
    if (queueCard) queueCard.style.display = 'block';

    if (mergeMode) {
        // 합치기 모드: 1개 job, 첫 번째 파일의 메타 사용
        const primaryMeta = fileMetas[0] || { meetingTitle: '', attendees: '' };
        const jobOptions = { ...commonOptions, meetingTitle: primaryMeta.meetingTitle, attendees: primaryMeta.attendees };
        const job = makeJob([...selectedFiles], [...audioDurations], jobOptions, true);
        jobsById.set(job.id, job);
        renderJobCard(job);
    } else {
        // 일반 모드: 파일마다 별도 job + 각자의 meta
        selectedFiles.forEach((f, i) => {
            const meta = fileMetas[i] || { meetingTitle: '', attendees: '' };
            const jobOptions = { ...commonOptions, meetingTitle: meta.meetingTitle, attendees: meta.attendees };
            const job = makeJob([f], [audioDurations[i] || 0], jobOptions, false);
            jobsById.set(job.id, job);
            renderJobCard(job);
        });
    }

    refreshJobQueueCount();

    // 폼 초기화 (파일만, 프로젝트/AI 모델은 유지 — 연속 업로드 편의)
    clearFile();

    runJobQueue();
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
        updateJobCard(job, { status: '회의록 생성 완료!', pct: 100, state: 'done', stage: 'summarize', stageDone: true });
        fetchUsageInfo();
        announceJobDone(job);

        // 자동 이메일 발송 (옵션 켜진 경우)
        if (job.options.autoEmail && job.summaryId) {
            try {
                const emailRes = await authFetch(`${API_BASE_URL}/summaries/${job.summaryId}/send-email`, { method: 'POST' });
                if (emailRes.ok) {
                    const emailData = await emailRes.json();
                    showJobToast(job, emailData.message);
                } else {
                    const emailError = await emailRes.json();
                    showJobToast(job, '이메일 발송 실패: ' + (emailError.detail || '알 수 없는 오류'));
                }
            } catch (emailErr) {
                console.error('Auto email error:', emailErr);
            }
        }
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
    const list = document.getElementById('jobQueueList');
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

    list.appendChild(node);
    job.cardEl = node;
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

    // 완료 시 결과 보기 버튼 노출, 취소 버튼 숨김
    const viewBtn = card.querySelector('[data-action="view"]');
    const cancelBtn = card.querySelector('[data-action="cancel"]');
    if (state === 'done') {
        if (viewBtn) viewBtn.hidden = false;
        if (cancelBtn) cancelBtn.hidden = true;
    } else if (state === 'failed' || state === 'canceled') {
        if (viewBtn) viewBtn.hidden = true;
        if (cancelBtn) {
            // 닫기(제거) 버튼으로 전환
            cancelBtn.hidden = false;
            cancelBtn.title = '카드 제거';
        }
    }
}

function refreshJobQueueCount() {
    const countEl = document.getElementById('jobQueueCount');
    if (countEl) countEl.textContent = String(getActiveJobCount());
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
    // 작업이 모두 사라지면 큐 카드 숨김
    if (jobsById.size === 0) {
        const queueCard = document.getElementById('jobQueueCard');
        if (queueCard) queueCard.style.display = 'none';
    }
    refreshJobQueueCount();
}

// 작업 완료 알림: 한가하면 결과를 바로 펼치고, 아니면 토스트로 안내
function announceJobDone(job) {
    const othersBusy = getActiveJobCount() > 0; // 본인은 이미 done이므로 남은 활성 작업만 집계됨
    const resultVisible = resultSection && resultSection.style.display !== 'none';

    // 사용자가 생성 화면에 있고, 다른 작업/열린 결과가 없으면 바로 보여준다
    if (currentView === 'create' && !othersBusy && !resultVisible && !isEditMode) {
        viewJobResult(job);
        showToast(`"${job.displayName}" 회의록이 완성됐어요.`, { type: 'success' });
        return;
    }

    showToast(`"${job.displayName}" 회의록이 완성됐어요.`, {
        type: 'success',
        duration: 10000,
        actionLabel: '결과 보기',
        onAction: () => {
            switchView('create');
            viewJobResult(job);
        },
    });
}

// 완료된 작업을 결과 페이지에 표시
async function viewJobResult(job) {
    if (job.status !== 'done' || !job.summary) return;

    resultData = {
        transcriptId: job.transcriptId,
        transcript: job.transcript,
        filename: job.displayName,
        fileSize: job.totalSize,
        audioDuration: job.totalDuration,
        timestamp: job.timestamp,
        summary: job.summary,
        summaryId: job.summaryId,
        gptModel: job.options.gptModel,
    };

    // 버전 상태 초기화 (방금 만들어진 v1=ai_initial)
    currentSummaryId = job.summaryId;
    currentVersions = [{
        version_no: 1,
        source: 'ai_initial',
        content: job.summary,
        created_at: new Date().toISOString(),
    }];
    currentVersionNo = 1;
    isViewingLatest = true;
    isDiffOpen = false;

    const titleEl = document.getElementById('resultTitle');
    if (titleEl) titleEl.textContent = '회의록 생성 완료!';
    setResultBackLink(false); // 작업 큐에서 연 결과는 목록 백링크 불필요
    showResult(resultData);
    renderVersionBar();
}

function showJobToast(job, message) {
    showToast(`${job.displayName} — ${message}`, { type: 'info', duration: 6000 });
}
