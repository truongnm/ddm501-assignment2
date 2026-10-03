# Build-design example. Record the resolved base-image digest in the release manifest.
FROM python:3.14-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.lock.txt /app/requirements.lock.txt
RUN pip install --no-cache-dir -r requirements.lock.txt
COPY src /app/src
COPY configs /app/configs
COPY run_experiments.py /app/run_experiments.py
RUN useradd --create-home runner && mkdir /app/artifacts && chown runner:runner /app/artifacts
USER runner
ENV PYTHONHASHSEED=501 OMP_NUM_THREADS=2 MPLCONFIGDIR=/app/artifacts/matplotlib
CMD ["python", "run_experiments.py", "--config", "configs/demo.json", "--out", "artifacts"]
