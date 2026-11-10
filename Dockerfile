FROM python:3.11-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential pkg-config libcairo2-dev libpango1.0-dev ffmpeg \
    texlive-latex-base texlive-latex-extra texlive-fonts-recommended \
    texlive-science dvisvgm bubblewrap util-linux \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt cloud-sdk.lock ./
RUN pip install --no-cache-dir -r requirements.txt -c cloud-sdk.lock
RUN useradd --create-home --uid 1000 student && chown student:student /app
COPY --chown=student:student app.py app_settings.py generate_lesson.py lesson_tools.py cloud_lessons.py public_limits.py verify_host.py ./
COPY --chown=student:student styles.css system_prompt.txt suggestions.txt topic_viability.txt ./
COPY --chown=student:student .streamlit/config.toml .streamlit/config.toml
USER student
ENV PUBLIC_DEPLOYMENT=true
EXPOSE 7860
CMD ["sh", "-c", "python verify_host.py && python -m streamlit run app.py --server.address 0.0.0.0 --server.port 7860"]
