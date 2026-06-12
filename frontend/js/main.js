// ============================================
// main.js — 뷰 전환 + DOM/이벤트 초기화 + 부트스트랩
// 모든 스크립트 중 마지막에 로드된다 (index.html 로드 순서 참고)
// ============================================

// ---- 뷰 전환 (페이지 구조: 업로드 / 처리 중 / 목록 / 상세 / 프로젝트 / 컨텍스트 / 내 페이지) ----

function switchView(view) {
    const prevView = currentView;
    currentView = view;
    const views = {
        create: document.getElementById('createView'),
        dashboard: document.getElementById('dashboardView'),
        detail: document.getElementById('detailView'),
        context: document.getElementById('contextView'),
        projectDetail: document.getElementById('projectDetailView'),
        mypage: document.getElementById('myPageView'),
    };
    const navButtons = {
        create: document.getElementById('navCreate'),
        dashboard: document.getElementById('navDashboard'),
        context: document.getElementById('navContext'),
        mypage: document.getElementById('navMyPage'),
    };

    // 상세 페이지를 떠나면 상세 상태 정리
    if (prevView === 'detail' && view !== 'detail' && typeof clearDetailState === 'function') {
        clearDetailState();
    }

    // 모든 뷰 숨기기
    Object.values(views).forEach(el => { if (el) el.style.display = 'none'; });
    Object.values(navButtons).forEach(el => el?.classList.remove('active'));

    // 활성화
    if (views[view]) views[view].style.display = '';
    // 하위 페이지는 상위 네비를 켠 상태로 유지
    if (view === 'projectDetail' && navButtons.context) {
        navButtons.context.classList.add('active');
    } else if (view === 'detail' && navButtons.dashboard) {
        navButtons.dashboard.classList.add('active');
    } else if (navButtons[view]) {
        navButtons[view].classList.add('active');
    }

    // 진입 시 자동 로드
    if (view === 'dashboard') loadDashboard(dashboardQuery, dashboardPage);
    if (view === 'context') switchContextTab(currentContextTab);
    if (view === 'mypage') loadMyPage();

    window.scrollTo({ top: 0, behavior: 'smooth' });
}

// 컨텍스트 허브 하위 탭 (프로젝트 / 내 컨텍스트)
function switchContextTab(name) {
    currentContextTab = name;
    document.querySelectorAll('[data-context-tab]').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.contextTab === name);
    });
    document.getElementById('contextProjectsPane')?.classList.toggle('active', name === 'projects');
    document.getElementById('contextPersonalPane')?.classList.toggle('active', name === 'personal');
    if (name === 'projects') loadProjects();
    else loadPersonalContext();
}

// 이메일 "수정하러 가기" 딥링크 (#summary/{id}) 처리
function handleHashDeepLink() {
    const m = (location.hash || '').match(/^#summary\/(\d+)$/);
    if (!m) return;
    const summaryId = parseInt(m[1], 10);
    history.replaceState(null, '', location.pathname);
    if (Number.isFinite(summaryId)) {
        openSummaryFromDashboard(summaryId);
    }
}

// ---- DOM 및 이벤트 초기화 ----

function initDomElements() {
    uploadArea = document.getElementById('uploadArea');
    fileInput = document.getElementById('fileInput');
    convertBtn = document.getElementById('convertBtn');
    resultSection = document.getElementById('resultSection');
    copyBtn = document.getElementById('copyBtn');
}

function setupEventListeners() {
    // 파일 업로드 관련
    uploadArea.addEventListener('click', () => fileInput.click());
    uploadArea.addEventListener('dragover', handleDragOver);
    uploadArea.addEventListener('dragleave', handleDragLeave);
    uploadArea.addEventListener('drop', handleDrop);
    fileInput.addEventListener('change', handleFileSelect);

    // 다중 파일 리스트 "전체 지우기"
    const clearAllBtn = document.getElementById('fileInfoClear');
    if (clearAllBtn) clearAllBtn.addEventListener('click', clearFile);

    // 변환 버튼
    convertBtn.addEventListener('click', handleConvert);

    // 상세 페이지 관련
    copyBtn.addEventListener('click', copyToClipboard);
    const detailProjectApplyBtn = document.getElementById('detailProjectApplyBtn');
    if (detailProjectApplyBtn) detailProjectApplyBtn.addEventListener('click', applyDetailProject);
    const detailDeleteBtn = document.getElementById('detailDeleteBtn');
    if (detailDeleteBtn) detailDeleteBtn.addEventListener('click', deleteCurrentSummary);

    // 로그아웃
    document.getElementById('logoutBtn').addEventListener('click', logout);

    // 탭 전환
    const tabs = document.querySelectorAll('.tab[data-tab]');
    tabs.forEach(tab => {
        tab.addEventListener('click', () => switchTab(tab.dataset.tab));
    });

    // 뷰 전환 네비
    const navCreate = document.getElementById('navCreate');
    const navDashboard = document.getElementById('navDashboard');
    const navContext = document.getElementById('navContext');
    const navMyPage = document.getElementById('navMyPage');
    if (navCreate) navCreate.addEventListener('click', () => switchView('create'));
    if (navDashboard) navDashboard.addEventListener('click', () => switchView('dashboard'));
    if (navContext) navContext.addEventListener('click', () => switchView('context'));
    if (navMyPage) navMyPage.addEventListener('click', () => switchView('mypage'));

    // 전역 처리 도크 컨트롤 바인딩
    if (typeof initDock === 'function') initDock();

    // 컨텍스트 허브 하위 탭
    document.querySelectorAll('[data-context-tab]').forEach(btn => {
        btn.addEventListener('click', () => switchContextTab(btn.dataset.contextTab));
    });

    // 대시보드 검색 (300ms 디바운스, 검색 시 1페이지로)
    const dashboardSearchInput = document.getElementById('dashboardSearch');
    if (dashboardSearchInput) {
        dashboardSearchInput.addEventListener('input', (e) => {
            const q = e.target.value.trim();
            if (dashboardSearchTimer) clearTimeout(dashboardSearchTimer);
            dashboardSearchTimer = setTimeout(() => loadDashboard(q, 1), 300);
        });
    }

    // 대시보드 페이지네이션
    const dashboardPrevBtn = document.getElementById('dashboardPrevBtn');
    const dashboardNextBtn = document.getElementById('dashboardNextBtn');
    if (dashboardPrevBtn) dashboardPrevBtn.addEventListener('click', () => loadDashboard(dashboardQuery, dashboardPage - 1));
    if (dashboardNextBtn) dashboardNextBtn.addEventListener('click', () => loadDashboard(dashboardQuery, dashboardPage + 1));

    // 내 페이지: 메타 프롬프트 토글
    const togglePromptBtn = document.getElementById('togglePromptBtn');
    if (togglePromptBtn) togglePromptBtn.addEventListener('click', toggleSystemPrompt);

    // 프로젝트 AI 메모리 재구축
    const projectMemoryRebuildBtn = document.getElementById('projectMemoryRebuildBtn');
    if (projectMemoryRebuildBtn) projectMemoryRebuildBtn.addEventListener('click', rebuildProjectMemory);

    // 버전 드롭다운 + diff 토글
    const versionSelect = document.getElementById('versionSelect');
    if (versionSelect) versionSelect.addEventListener('change', onVersionSelectChange);
    const toggleDiffBtn = document.getElementById('toggleDiffBtn');
    if (toggleDiffBtn) toggleDiffBtn.addEventListener('click', toggleDiff);

    // 결과 카드 → 내 회의록 목록 백링크
    const backToListBtn = document.getElementById('backToListBtn');
    if (backToListBtn) backToListBtn.addEventListener('click', () => switchView('dashboard'));

    // 프로젝트 AI 메모리 저장
    const projectMemorySaveBtn = document.getElementById('projectMemorySaveBtn');
    if (projectMemorySaveBtn) projectMemorySaveBtn.addEventListener('click', saveProjectMemory);

    // 프로젝트 생성/편집/삭제
    const newProjectBtn = document.getElementById('newProjectBtn');
    if (newProjectBtn) newProjectBtn.addEventListener('click', () => openProjectModal('create'));
    const backToProjectsBtn = document.getElementById('backToProjectsBtn');
    if (backToProjectsBtn) backToProjectsBtn.addEventListener('click', () => switchView('context'));
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
    // 모달 키보드: Esc 닫기, 프로젝트명 입력에서 Enter 저장
    document.addEventListener('keydown', (e) => {
        if (!projectModal || projectModal.style.display === 'none') return;
        if (e.key === 'Escape') closeProjectModal();
    });
    const projectModalName = document.getElementById('projectModalName');
    if (projectModalName) projectModalName.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { e.preventDefault(); saveProjectModal(); }
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

    // 프로젝트 캐시 워밍 (파일 카드의 프로젝트 셀렉트용)
    refreshProjectsCache();

    // 참석자 자동완성 (글로벌 트리거)
    initAttendeeAutocomplete();

    // 합치기 토글 변경 시 파일 카드 시각 표시 갱신
    const mergeToggle = document.getElementById('mergeFilesCheckbox');
    if (mergeToggle) mergeToggle.addEventListener('change', renderFileList);
}

// ---- 부트스트랩 ----

document.addEventListener('DOMContentLoaded', () => {
    initAuth();
});

// 처리 중인 작업이 있을 때 페이지 이탈 경고 (작업은 브라우저 메모리에서 진행됨)
window.addEventListener('beforeunload', (e) => {
    if (typeof getActiveJobCount === 'function' && getActiveJobCount() > 0) {
        e.preventDefault();
        e.returnValue = '';
    }
});
