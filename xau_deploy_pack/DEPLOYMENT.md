# XAU System v2.3 deployment pack

This pack gives you the runtime files needed to move from local testing to a 24/7 hosted setup.

## What is included

- `.env.example` — secrets and runtime variables
- `config.yaml` — strategy/runtime configuration
- `requirements.txt` — Python dependencies for deployment
- `start_live.sh` — startup script
- `xau-system.service` — systemd service file for Ubuntu VPS
- `Dockerfile` — container image build
- `docker-compose.yml` — simple container runtime

## Important boundary

The startup script is intentionally safe by default: it runs the project in the current CSV/paper command mode.

That means this pack is ready for:
- local paper testing
- VPS paper deployment
- alerts-only deployment

To make it fully live on OANDA, you still need to replace the startup command with your realtime loop / streaming adapter entrypoint once you wire that into the codebase.

## Folder layout expected on server

/opt/xau-system/
  xau_system/               # your project package
  requirements.txt
  .env
  config.yaml
  start_live.sh
  data/
  runtime/

## Ubuntu VPS setup

### 1. Install system packages

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git
```

### 2. Copy your project

```bash
sudo mkdir -p /opt/xau-system
sudo chown -R $USER:$USER /opt/xau-system
cd /opt/xau-system
# copy your xau_system project here
```

### 3. Add deployment files

Copy this pack into `/opt/xau-system/`.

### 4. Create environment file

```bash
cp .env.example .env
nano .env
```

### 5. First manual run

```bash
bash start_live.sh
```

### 6. Install as a service

```bash
sudo cp xau-system.service /etc/systemd/system/xau-system.service
sudo systemctl daemon-reload
sudo systemctl enable xau-system
sudo systemctl start xau-system
sudo systemctl status xau-system
```

### 7. View logs

```bash
tail -f /opt/xau-system/runtime/logs/systemd.out.log
tail -f /opt/xau-system/runtime/logs/systemd.err.log
```

## Docker option

```bash
cp .env.example .env
nano .env
docker compose up -d --build
```

## Your next live-safe progression

1. Practice account + CSV/paper command working
2. VPS deployment stable for several days
3. Telegram alerts verified
4. Replace startup command with realtime adapter
5. Practice OANDA first
6. Live alerts-only
7. Semi-auto smallest size
8. Full-auto only after validation gates pass
