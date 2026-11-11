# problem-extractor

수학 교과서·문제집 페이지 사진을 올리면 문제를 하나씩 나눠서 **발문 · 보기 · 수식(LaTeX) · 그림 · 단원 · 태그**로 구조화하고 SQLite DB에 저장하는 API예요.

- OCR과 구조화를 비전 모델 한 번의 호출로 처리해요 (JSON 스키마를 강제하는 구조화 출력 사용).
- 모델은 **Gemini(무료 등급 있음)** 와 **Claude(유료)** 중에 골라요. 기본은 Gemini예요.
- 그래프·도형·표는 영역을 찾아 원본 해상도로 잘라 따로 저장하고, 바깥 여백은 자동으로 정리해요.
- 그림마다 **종류(그래프/도형/표…), 그림 속 식, 이름 붙은 점, 표 내용(Markdown)** 을 함께 뽑아요. 검색에도 쓰여요.
- 같은 사진을 다시 올리면 API를 다시 부르지 않고 저장된 결과를 돌려줘요 (SHA-256 기준).
- 사람이 고칠 수 있게 수정(PATCH)과 `reviewed`(검수 완료) 표시를 제공해요.

> ⚠️ **저작권 안내** — 이 프로젝트는 도구만 제공합니다. 교과서·문제집의 문제는 대부분 출판사의 저작물이에요. 입력한 자료와 추출 결과를 어떻게 쓰고 공유할지는 **사용자 책임**이며, 각자 저작권법을 지켜 주세요. 이 저장소에는 실제 출판물의 문제가 들어 있지 않아요. 샘플 이미지는 `scripts/make_sample.py`로 직접 그린 거예요.

## 3분 만에 시작하기

준비물: **Python 3.10 이상** ([python.org](https://www.python.org/downloads/)에서 설치, Windows는 설치 첫 화면에서 "Add python.exe to PATH" 체크) + 구글 계정

1. **내려받기**: 이 페이지 위쪽 초록색 **Code → Download ZIP**을 눌러 받고 압축을 풀어요. (git을 쓰면 `git clone https://github.com/submarine0226-max/problem-extractor`)
2. **실행**
   - Windows: 폴더 안의 **`start.bat`을 더블클릭**
   - macOS·Linux: 터미널에서 `./start.sh`
3. 처음 한 번은 필요한 것을 알아서 설치하고(1~3분), **무료 Gemini API 키**를 물어봐요. 열리는 [Google AI Studio](https://aistudio.google.com/apikey) 페이지에서 **Create API key**를 눌러 복사한 뒤 창에 붙여 넣으면 끝이에요. (카드 등록 필요 없음)
4. 브라우저가 자동으로 열려요. 사진을 끌어다 놓으면 문제가 추출돼요.

다음부터는 `start.bat`(또는 `./start.sh`)만 실행하면 바로 켜져요. 검은 창을 닫으면 서버가 꺼져요. 데이터는 폴더 안의 `data/`에 쌓여요.

<details>
<summary>Docker로 실행하기</summary>

```bash
cp .env.example .env          # GEMINI_API_KEY= 뒤에 키를 넣으세요
docker compose up -d          # http://localhost:8000
```

데이터는 `./data`에 저장돼요. 내 컴퓨터(127.0.0.1)에서만 열리게 묶어 뒀어요.
</details>

<details>
<summary>직접 설치하기 (개발용)</summary>

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate   /   macOS·Linux: source .venv/bin/activate
pip install -e ".[dev]"     # Gemini만 쓰면 pip install -e . 로 충분
cp .env.example .env        # GEMINI_API_KEY 를 채우세요
uvicorn problem_extractor.main:app --reload
```
</details>

### 자주 막히는 곳

| 증상 | 해결 |
|---|---|
| `start.bat`을 눌렀는데 "Python 3.10 이상이 필요해요" | Python을 설치하고(PATH 체크) 다시 실행 |
| 화면 위에 "API 키가 필요해요" 안내 | `.env` 파일의 `GEMINI_API_KEY=` 뒤에 키를 넣고 저장 → 화면의 **다시 확인** 버튼 (서버 재시작 필요 없음) |
| 사진을 올리면 429 오류 | 무료 한도에 걸린 거예요. 화면이 60초 뒤 자동으로 다시 시도해요 |
| "키가 잘못됐어요" | 키를 다시 복사해서 `.env`에 넣어 주세요 (앞뒤 공백 주의) |
| PowerShell에서 명령이 안 먹어요 | `start.bat`을 더블클릭하는 게 가장 쉬워요 |

## 웹 화면

서버가 켜지면 http://localhost:8000 에서 쓸 수 있어요.

- **올리기**: 사진을 끌어다 놓거나(여러 장 가능) 화면 캡처를 Ctrl+V로 붙여 넣어요. 한 장씩 차례로 보내고, 무료 한도(429)에 걸리면 60초 기다렸다가 자동으로 다시 시도해요.
- **문제**: 텍스트·태그·단원·유형·검수 상태로 검색하고, 수식은 KaTeX로 그려서 보여줘요. 지금 조건의 문제를 JSON으로 내보낼 수 있어요.
- **검수**: 문제를 누르면 원본에서 그 문제 영역을 잘라낸 이미지 옆에서 바로 고칠 수 있어요. 그림은 종류·설명·식·점·표를 고치거나, 원본 위에서 드래그해 **영역을 다시 지정**하거나, 놓친 그림을 **추가**할 수 있어요. 미리보기가 실시간으로 바뀌어요. `Ctrl+Enter` = 검수 완료하고 다음 문제, `Ctrl+S` = 저장.
- **페이지**: 처리한 페이지 목록, 원본 보기, 페이지 단위 삭제.

API만 쓰고 싶으면 http://localhost:8000/docs 의 Swagger UI를 쓰면 돼요.

### 화면만 Vercel에 올리기 (선택)

웹 화면을 `index.html` 한 파일로 묶어서 Vercel·Netlify 같은 곳에 올릴 수 있어요. 화면만 올라가고, **API 서버와 DB는 계속 내 컴퓨터에서 돌아요.**

```bash
python scripts/build_standalone.py     # dist/index.html 생성
```

1. `dist` 폴더를 Vercel에 끌어다 놓아 배포해요 (예: `https://my-problems.vercel.app`).
2. 서버의 `.env`에 `PX_CORS_ORIGINS=https://my-problems.vercel.app` 를 적고 서버를 다시 켜요.
3. 배포된 주소를 열면 `http://localhost:8000`의 서버로 요청을 보내요. Chrome이 "로컬 네트워크 접근"을 물으면 허용하세요. 서버 주소는 화면 오른쪽 위를 눌러 바꿀 수 있어요.

- 내 컴퓨터에서 서버가 켜져 있을 때만, 그리고 그 컴퓨터의 브라우저에서만 동작해요. 다른 사람이 주소를 열어도 그 사람 컴퓨터의 localhost를 찾으니 내 데이터는 보이지 않아요.
- Safari는 https 사이트에서 localhost 호출을 막아서 안 돼요. Chrome·Edge·Firefox를 쓰세요.

```bash
python scripts/make_sample.py                       # samples/sample_page.png 생성
curl -F "file=@samples/sample_page.png" http://localhost:8000/extract
```

## API

| 메서드 | 경로 | 설명 |
|---|---|---|
| `POST` | `/extract` | 사진(JPEG/PNG/WEBP) 한 장 업로드 → 추출·저장 후 결과 반환. `?force=true`면 같은 사진도 다시 추출 |
| `GET` | `/problems` | 문제 검색. `q`(텍스트), `tag`, `topic`, `problem_type`, `source_id`, `reviewed`, `limit`, `offset` |
| `GET` | `/problems/{id}` | 문제 하나 |
| `PATCH` | `/problems/{id}` | 검수하며 고친 필드만 보내기. 예: `{"answer": "5", "reviewed": true}` |
| `DELETE` | `/problems/{id}` | 문제와 그림 삭제 |
| `GET` | `/sources` | 처리한 페이지 목록 |
| `GET` / `DELETE` | `/sources/{id}` | 페이지 하나의 결과 조회 / 페이지와 그 문제 전체 삭제 |
| `GET` | `/figures/{id}` | 잘라낸 그림 PNG |
| `PATCH` | `/figures/{id}` | 그림 정보 수정. `bbox`를 보내면 원본에서 다시 잘라내요 |
| `DELETE` | `/figures/{id}` | 그림 삭제 |
| `POST` | `/problems/{id}/figures` | 모델이 놓친 그림을 `bbox`로 직접 추가 |
| `GET` | `/problems/{id}/image` | 원본에서 문제 영역만 잘라낸 PNG (검수용) |
| `GET` | `/sources/{id}/image` | 원본 페이지 PNG |

### 추출 결과 예시

```json
{
  "id": 3,
  "number": "4",
  "problem_type": "multiple_choice",
  "stem": "$x$에 대한 이차방정식 $x^2 + 2kx + k + 6 = 0$이 중근을 가질 때, 양수 $k$의 값은?",
  "choices": [{"label": "①", "text": "1"}, {"label": "②", "text": "2"}, "..."],
  "answer": null,
  "topic": "근의 공식",
  "tags": ["이차방정식", "판별식", "중근"],
  "points": 4,
  "confidence": "high",
  "figures": [
    {
      "id": 7,
      "kind": "graph",
      "description": "이차함수 y=x^2-4의 그래프와 x축의 교점 A, B",
      "equations": ["y=x^2-4"],
      "points": [{"label": "A", "coordinates": null}, {"label": "B", "coordinates": null}],
      "table_markdown": null,
      "url": "/figures/7?v=1a2b_2_0"
    }
  ],
  "reviewed": false
}
```

- `answer` / `solution`은 **페이지에 인쇄돼 있을 때만** 채워요. 모델이 직접 풀어서 채우지 않아요(틀린 정답이 DB에 쌓이는 걸 막기 위해서).
- `confidence`가 `low`이거나 `notes`가 있으면 검수가 꼭 필요한 문제예요.

## 설정 (.env)

| 변수 | 기본값 | 설명 |
|---|---|---|
| `PX_PROVIDER` | `gemini` | `gemini` 또는 `claude` |
| `GEMINI_API_KEY` | — | Google AI Studio API 키 (gemini일 때) |
| `ANTHROPIC_API_KEY` | — | Anthropic API 키 (claude일 때). `ant auth login`으로 로그인했다면 생략 가능 |
| `PX_MODEL` | 제공사별 기본값 | gemini: `gemini-3.5-flash-lite`, claude: `claude-opus-5-5`. 정확도가 아쉬우면 `gemini-3.8-flash` |
| `PX_EFFORT` | `medium` | claude 전용 사고 깊이: `low` / `medium` / `high` / `xhigh` / `max` |
| `PX_DATA_DIR` | `data` | DB와 이미지 저장 위치 |
| `PX_MAX_IMAGE_SIDE` | `2000` | 모델에 보낼 이미지 긴 변 최대 픽셀 |
| `PX_MAX_UPLOAD_MB` | `15` | 업로드 크기 제한 |
| `PX_CORS_ORIGINS` | — | 화면을 다른 주소(Vercel 등)에 올렸을 때 그 주소. 쉼표로 여러 개 |

### 어떤 제공사를 쓸까?

| | Gemini (기본) | Claude |
|---|---|---|
| 비용 | 무료 등급 있음 (분당·하루 요청 한도, 한도는 [AI Studio](https://aistudio.google.com/rate-limit)에서 확인) | 사용한 만큼 과금 |
| 데이터 | 무료 등급에서는 Google이 입력을 서비스 개선에 쓸 수 있어요 | API 입력은 학습에 쓰지 않아요 |
| 비고 | 한도를 넘으면 429를 돌려줘요 | 모델이 거절하면 서버가 다른 모델로 자동 재시도해요 |

개인 학습 자료가 아니라 민감한 자료라면 무료 등급의 데이터 정책을 꼭 확인하세요.

## 구조

```
problem_extractor/
  main.py       uvicorn 진입점
  api.py        FastAPI 라우트 (create_app 으로 extractor 주입 가능)
  service.py    업로드 → 전처리 → 추출 → 그림 크롭 → 저장
  extractors/    추출기 (base: 공통 프롬프트·오류, gemini.py, claude.py)
  schemas.py    추출 스키마(Pydantic) / API 모델
  images.py     EXIF 회전 보정, 축소, bbox 크롭
  db.py         SQLite (sources / problems / figures)
  web/          웹 화면 (index.html, app.js, style.css — 빌드 없이 그대로 서빙)
scripts/build_standalone.py   웹 화면을 dist/index.html 한 파일로 묶기
```

다른 OCR이나 모델을 쓰고 싶으면 `extractors/base.py`의 `Extractor` 프로토콜(`extract(image_bytes, media_type) -> PageExtraction`)을 구현해서 `create_app(extractor=...)`에 넘기면 돼요.

## 테스트

```bash
pytest
```

테스트는 가짜 extractor를 쓰기 때문에 API 키 없이 돌아가고 비용도 들지 않아요.

## 알려진 한계

- 그림 영역은 모델이 추정한 좌표라 어긋날 수 있어요. 여유를 두고 자른 뒤 빈 여백만 깎고, 옆 글자까지 잡혔으면 검수 화면의 **영역 다시 지정**으로 고쳐요.
- 그림 속 식·점·표는 그림에 **인쇄된 것만** 옮겨요. 그래프에서 좌표를 읽어 내거나 함수식을 추측하지는 않아요.
- 페이지에 문제가 아주 많으면 응답이 잘릴 수 있어요(422 반환). 페이지를 나눠서 찍어 주세요.
- 손글씨 필기가 많은 사진, 심하게 기울어진 사진은 정확도가 떨어져요.
- 아직 인증이 없어요. 기본 실행은 내 컴퓨터(127.0.0.1)에서만 열려요. `--host 0.0.0.0`으로 외부에 열거나 공개 서버에 올릴 거면 앞단에 인증을 붙여 주세요(누구나 내 API 키로 호출하고 DB를 지울 수 있게 돼요).
- 웹 화면의 수식 렌더링(KaTeX)은 CDN에서 불러와요. 인터넷이 없으면 수식이 원문 그대로 보여요.

## 라이선스

MIT
