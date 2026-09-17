# XTTS Web TTS

A self-hosted web interface for generating speech with **Coqui XTTS v2**.

The project provides:

* a web-based frontend for text-to-speech generation
* 58 pre-rendered XTTS speaker samples for voice preview
* a job queue with progress reporting
* a Docker-based XTTS service
* a backend API
* a watchdog for starting and stopping the XTTS services
* configurable speech parameters such as speed, temperature, top-k, top-p and repetition penalty

## Requirements

* Linux
* Docker
* Docker Compose
* A machine with enough RAM and CPU resources for XTTS v2
* A browser for the frontend

This project currently uses **CPU-based XTTS**.

## Project structure

```text
.
├── backend/
│   ├── app.py
│   └── Dockerfile
├── coqui/
│   ├── docker-compose.yml
│   └── docker/
│       ├── Dockerfile
│       ├── Dockerfile.watchdog
│       ├── Dockerfile.xtts
│       ├── watchdog.py
│       └── xtts_server.py
├── voices/
│   └── *.wav
├── XTTS_Frontend.html
├── cheatsheet.txt
└── .gitignore
```

## Installation

Clone the repository:

```bash
git clone <repository-url>
cd <repository-directory>
```

The Docker Compose configuration currently uses absolute host paths.

In `coqui/docker-compose.yml`, the following paths refer to the original project location:

```text
/mnt/data/tts/coqui
/mnt/data/tts/models
/mnt/data/tts/output
/mnt/data/tts/backend
/mnt/data/tts/voices
```

If you install the project somewhere else, **adapt these paths to your own installation** before starting the services.

The XTTS model itself is **not included in this repository**. It will be downloaded by Coqui TTS when the XTTS container is built/started.

## Starting the services

Change into the Compose directory:

```bash
cd coqui
```

Build the containers:

```bash
docker compose build
```

Start the XTTS service and backend:

```bash
docker compose up -d xtts backend
```

The watchdog can be started separately:

```bash
docker compose up -d watchdog
```

## Frontend configuration

Before opening `XTTS_Frontend.html`, edit the following lines:

```javascript
const BACKEND = "http://<ip-address>:8011";
const WATCHDOG = "http://<ip-address>:8012";
```

Replace `<ip-address>` with the IP address of the machine running the Docker containers.

For example:

```javascript
const BACKEND = "http://192.168.1.50:8011";
const WATCHDOG = "http://192.168.1.50:8012";
```

The frontend also contains one example audio preview using the same backend address. Replace `<ip-address>` there as well if necessary.

The frontend is a standalone HTML file and can be opened directly in a browser.

## Speaker samples

The `voices/` directory contains short WAV files generated with XTTS v2.

They are provided so that the speaker preview in the frontend works immediately without requiring the user to generate the samples first.

The samples were generated locally from the speaker voices available in the XTTS v2 model. They are **generated outputs**, not copies of the XTTS model files.

## XTTS model

The XTTS v2 model is not included in this repository because of its size and licensing conditions.

The project uses:

```text
tts_models/multilingual/multi-dataset/xtts_v2
```

Please read the applicable XTTS v2 / Coqui Public Model License terms before using the model or its outputs.

In particular, check the license conditions if you intend to use the system for commercial purposes.

## Docker services

### XTTS

The `xtts` container runs the XTTS v2 model and provides the synthesis API on port `8010` inside the Docker network.

### Backend

The `backend` container provides the web API and job queue.

It is exposed on:

```text
port 8011
```

### Watchdog

The watchdog provides simple start/stop and status control for the XTTS and backend containers.

It is exposed on:

```text
port 8012
```

The watchdog has access to the Docker socket because it needs to control the other containers. **Do not expose the watchdog directly to the Internet.**

## Output

Generated WAV files are stored in the configured output directory.

The backend also makes generated files available to the frontend through its `/output` endpoint.

## Configuration

The main XTTS parameters available in the frontend include:

* `speed` – speech speed
* `temperature` – variation/randomness
* `top_k` – number of candidate tokens considered
* `top_p` – probability threshold
* `repetition_penalty` – reduces unwanted repetitions

The included `cheatsheet.txt` contains example settings and a direct XTTS command-line example.

## License

This repository contains original project code and generated audio samples.

The XTTS v2 model is **not included** and is subject to its own license terms.

The XTTS v2 license therefore applies independently from the license of the code in this repository.

If you use, modify or redistribute this project, make sure that you comply with the applicable licenses of XTTS v2 and its dependencies.

## Disclaimer

This project is provided as-is.

The author does not guarantee that generated speech is suitable for every purpose. Users are responsible for complying with applicable laws, licenses and rights when using generated audio or voice models.
