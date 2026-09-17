
FROM python:3.10-slim

RUN apt update && apt install -y \
    git \
    espeak-ng \
    ffmpeg \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip wheel

RUN pip install setuptools==80.9.0

RUN python -c "import pkg_resources; print('pkg_resources OK')"

RUN pip install torch==2.5.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cpu

RUN pip install TTS

RUN pip install --force-reinstall "transformers==4.41.2"

# Kompatibilität mit scipy/librosa/TTS
RUN pip install --force-reinstall "numpy<2"

RUN python -c "import numpy; print('numpy', numpy.__version__)"
RUN python -c "import torch; print('torch', torch.__version__); print('cuda', torch.cuda.is_available())"
RUN python -c "import transformers; print('transformers', transformers.__version__)"
