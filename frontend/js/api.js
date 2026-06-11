// ============================================
// api.js — 인증된 fetch 래퍼 + 사용량 조회
// ============================================

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
