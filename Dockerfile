FROM ghcr.io/astral-sh/uv:python3.11-bookworm

WORKDIR /app

# 의존성 잠금 파일만 먼저 복사하여 Docker 레이어 캐시 활용
COPY pyproject.toml uv.lock ./

# 프로덕션 컨테이너에서는 dev 의존성 없이 .venv에 설치
RUN uv sync --frozen --no-dev

# 애플리케이션 소스 복사
COPY . .

# uv sync 로 생성된 .venv 의 bin 디렉터리를 PATH에 추가
ENV PATH="/app/.venv/bin:${PATH}"

EXPOSE 9655

CMD ["gunicorn", "--bind", "0.0.0.0:9655", "src.app.main:app"]
