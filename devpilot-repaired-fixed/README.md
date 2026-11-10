# DevPilot — Agentic DevOps Control Center

This package contains the React/Vite frontend and FastAPI backend. It supports local file storage and Amazon S3 file storage. EC2 deployment is a separate optional feature and is only enabled when the EC2/SSM settings are configured.

## Windows + Docker Desktop setup

1. Extract this project to a folder such as `D:\\devpilot-repaired`.
2. Open `backend` and copy `.env.example` to `.env` if `.env` does not already exist.
3. Edit `backend/.env` and confirm:
   - `STORAGE_MODE=s3`
   - `AWS_REGION=ap-south-1`
   - `S3_BUCKET_NAME=devpilot-shoaib-storage-2026` (or your actual bucket)
   - `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` are a current, active IAM access key pair, if using static credentials.
4. Ensure the bucket already exists in the same AWS region. The IAM identity needs `s3:ListBucket` on the bucket and `s3:GetObject`, `s3:PutObject`, and `s3:DeleteObject` on its objects.
5. Start Docker Desktop. From the project root run:

```powershell
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 backend
```

6. Open:
   - Frontend: http://localhost:5173
   - Backend health: http://localhost:8765/api/health
   - AWS/S3 status: http://localhost:8765/api/aws/health
   - API documentation: http://localhost:8765/docs

The backend container reads `backend/.env` directly. The Compose file intentionally does not hard-code AWS access keys or overwrite the bucket/region from that file. The `.env` file is excluded from Git.

## AWS credential troubleshooting

If `/api/aws/health` reports `InvalidAccessKeyId`, AWS is rejecting the access key being supplied to the backend. Code changes cannot make an inactive, deleted, mistyped, or revoked key valid. Create/activate a new IAM access key in AWS if necessary, update the two credential values in `backend/.env`, then recreate only the backend container:

```powershell
docker compose up -d --force-recreate backend
```

Never paste credentials into chat, screenshots, GitHub, or frontend source. Prefer an IAM role/profile over long-lived access keys where supported. Do not add access keys to `docker-compose.yml`.

## Storage behavior

- Uploads support multiple files and folders, with relative folder paths preserved.
- Uploads use the currently opened folder prefix.
- The backend validates paths and enforces `MAX_UPLOAD_MB` per file (default 100 MB).
- Multi-file uploads attempt to clean up objects created by the request if a later upload fails.
- S3 listing uses pagination and folder delimiters.
- S3 objects are uploaded with server-side AES-256 encryption.
- Local mode is available by setting `STORAGE_MODE=local`.
- S3 and EC2 deployment health are reported separately. S3 file storage does not require EC2 deployment settings.

## Docker data safety

Persistent application data is stored in:
- `backend/data` — SQLite database
- `backend/storage` — local storage mode
- `data/repositories` — cloned Git repositories

These are bind-mounted from the project folder. Do not delete Docker volumes, Docker's WSL VHDX files, or these folders when troubleshooting.

The backend mounts the Docker socket so it can inspect Docker status. Access to the Docker socket is privileged; only run this project on a machine you control.

## Verify backend tests

With Python dependencies installed:

```powershell
python -m pip install -r backend/requirements.txt
python -m pip install pytest
python -m pytest backend/tests -q
```

## Feature scope and honest status

- React dashboard, FastAPI API, SQLite persistence, GitHub repository discovery/sync, incident evidence capture, local runbook retrieval, and approval audit records are implemented.
- Agent routing is deterministic and local; it is not an LLM agent.
- Incident analysis is rule/signature based; it is not a full telemetry correlation engine.
- EC2 deployment uses Git checkout, S3 artifact upload, and SSM command execution when correctly configured. It is not enabled by S3 storage configuration alone.
- Prometheus/Grafana metrics and a vector database are not included in this package.
- Approval records do not execute privileged commands.
