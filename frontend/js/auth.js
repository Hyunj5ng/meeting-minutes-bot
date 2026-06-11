// ============================================
// auth.js — Google 로그인 / 토큰 관리 / 화면 전환(로그인 ↔ 메인)
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
