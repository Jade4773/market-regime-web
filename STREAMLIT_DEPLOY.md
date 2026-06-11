# Streamlit Community Cloud 배포 순서

## 1. GitHub 저장소 만들기

이 폴더(`market_regime_web`)만 새 GitHub 저장소에 올립니다.

올려야 하는 주요 파일:

- `streamlit_app.py`
- `market_data.py`
- `market_rules.py`
- `user_store.py`
- `manage_users.py`
- `requirements.txt`
- `.streamlit/config.toml`

올리지 말아야 하는 파일:

- `.env`
- `data/users.json`
- `.venv/`
- `.streamlit/secrets.toml`

## 2. Streamlit에서 앱 만들기

Streamlit Community Cloud에 로그인한 뒤:

1. `Create app` 클릭
2. GitHub 저장소 선택
3. Main file path에 아래 값 입력

```text
streamlit_app.py
```

## 3. Secrets 설정

로컬에서 아래 명령으로 사용자 목록 JSON을 확인합니다.

```powershell
.\.venv\Scripts\python.exe manage_users.py json
```

Streamlit 앱 설정의 Secrets에 아래처럼 넣습니다.

```toml
USERS_JSON = '위 명령으로 나온 JSON 전체'
CACHE_SECONDS = "900"
```

## 4. 사용자 추가

로컬에서 사용자를 추가합니다.

```powershell
.\.venv\Scripts\python.exe manage_users.py add username
.\.venv\Scripts\python.exe manage_users.py json
```

새로 나온 JSON 전체를 Streamlit Secrets의 `USERS_JSON` 값으로 교체합니다.

## 참고

무료 Streamlit 앱은 사용량, 절전, 공개 저장소 여부 등 정책 제한을 받을 수 있습니다. 비밀번호를 쓰는 앱이므로 저장소에는 비밀번호 원문, `.env`, `data/users.json`을 올리지 마세요.
