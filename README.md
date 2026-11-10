# devsecops-lab-p9

Repository praktikum DevSecOps Pertemuan 9, **Container Security dengan Docker & Trivy** (STT Terpadu Nurul Fikri).

Isinya aplikasi Flask kecil yang dibungkus dengan Dockerfile hardened, lalu di-scan otomatis oleh Trivy di GitHub Actions.

| | |
|---|---|
| Nama | Firmansyah Dzakwan Arifien |
| NIM | 0110223282 |
| Kelas | Siang CS02 |
| Dosen | April Rustianto, S.Komp., M.T., CCIE |

## Struktur

```
.
├── app/
│   ├── app.py              aplikasi Flask (/ dan /health)
│   ├── requirements.in     dependency langsung
│   └── requirements.txt    hasil pip-compile, di-pin versi + hash SHA-256
├── Dockerfile.secure       Dockerfile hardened (multi-stage, non-root, dst.)
├── docker-compose.yml      hardening saat runtime (read-only, cap_drop, limit)
├── .dockerignore
├── .env.example            contoh variabel secret (file .env tidak di-commit)
└── .github/
    ├── dependabot.yml
    └── workflows/
        ├── security-scan.yml     build image + Trivy image scan
        └── dependency-scan.yml   Trivy filesystem scan (SCA, secret, misconfig)
```

## Menjalankan

```bash
# build + jalankan dengan hardening runtime
cp .env.example .env            # isi APP_SECRET
docker compose up -d --build
curl http://127.0.0.1:8080/
curl http://127.0.0.1:8080/health

# scan lokal
docker build -f Dockerfile.secure -t devsecops-lab-p9:v1 .
trivy image --severity CRITICAL,HIGH devsecops-lab-p9:v1
trivy config Dockerfile.secure
```

## Hardening checklist

Nomor `[H-xx]` juga ditulis sebagai komentar di `Dockerfile.secure` dan `docker-compose.yml`.

| No | Item | Diterapkan di | Cara cek |
|---|---|---|---|
| H-01 | Base image resmi & minimal (Alpine) | `FROM python:3.14-alpine` | `docker images` (91,5 MB vs 756 MB image Ubuntu) |
| H-02 | Tag versi + digest SHA-256 | `FROM ...@sha256:a18b...` | build selalu pakai image yang sama |
| H-03 | Multi-stage build | stage `builder` dan `runtime` | pip & cache tidak ada di image akhir |
| H-04 | User non-root, UID tetap, tanpa shell login | `adduser -u 10001 ... -s /sbin/nologin`, `USER 10001:10001` | `docker exec p9-web id` |
| H-05 | Hanya file yang perlu, kode read-only | `COPY` spesifik, `.dockerignore`, `--chmod=0444` | `ls -l /app` |
| H-06 | Tidak ada secret di image | secret lewat `APP_SECRET` saat runtime | `docker history`, `docker inspect` |
| H-07 | Dependency di-pin + hash, tanpa cache | `pip install --require-hashes --no-cache-dir` | build gagal bila hash tidak cocok |
| H-08 | Patch OS & buang tool yang tidak perlu | `apk upgrade`, `pip uninstall pip` | `python -m pip` → *No module named pip* |
| H-09 | Tanpa binary setuid/setgid | `find / -perm /6000 -exec chmod a-s` | `find / -xdev -perm /6000` → 0 |
| H-10 | HEALTHCHECK | `HEALTHCHECK CMD python -c ...` | `docker ps` → *(healthy)* |
| H-11 | Exec form, server production, port > 1024 | `ENTRYPOINT ["gunicorn"]`, port 8080 | header `Server: gunicorn` |
| H-12 | Root filesystem read-only | `read_only: true`, `/tmp` tmpfs `noexec` | `touch /etc/x` → *Read-only file system* |
| H-13 | Drop semua capability + no-new-privileges | `cap_drop: [ALL]`, `no-new-privileges:true` | `/proc/1/status` → `CapEff: 0`, `NoNewPrivs: 1` |
| H-14 | Batas resource | `mem_limit`, `cpus`, `pids_limit` | fork 100 proses → *can't fork* |
| H-15 | Image bisa ditelusuri & dipantau | label OCI, Trivy di CI, Dependabot | tab Actions & Security |

## CI/CD

Kedua workflow memakai Trivy dengan pola yang sama:

1. Scan semua severity, simpan sebagai SARIF, upload ke tab **Security → Code scanning**.
2. Scan ulang dengan `severity: CRITICAL,HIGH` dan `exit-code: 1` sebagai **gate fail-fast**. Kalau ada CVE kritis, job merah dan pull request tidak layak di-merge.

Beberapa hal sengaja dibuat berbeda dari contoh di panduan:

| Di panduan | Di repo ini | Alasan |
|---|---|---|
| `aquasecurity/trivy-action@master` | di-pin ke commit SHA rilis v0.36.0 | branch/tag bisa digeser. Tag trivy-action pernah di-force-push ke kode pencuri secret (CVE-2026-33634, Maret 2026). |
| versi Trivy mengikuti default action (v0.70.0) | `version: v0.76.2` | hasil CI sama dengan scan lokal |
| `codeql-action/upload-sarif@v3` | v4.39.3 (SHA) | versi terbaru |
| `actions/checkout@v4` | v7.0.1 (SHA) | versi terbaru |
| tanpa blok `permissions` | `security-events: write` | token default repo baru hanya read, sehingga upload SARIF ditolak |
| satu langkah Trivy SARIF + `exit-code: 1` | SARIF (semua severity) lalu gate terpisah | SARIF tetap lengkap dan tetap ter-upload, gate tetap tegas |
| `dependency-scan` hanya `vuln` | `vuln,secret,misconfig` | Dockerfile dan compose ikut diperiksa |

## Runtime security (Falco)

Hardening dan scanning bersifat pencegahan. Falco melengkapinya dengan deteksi saat container sudah berjalan.

```bash
docker run --rm -d --name falco --privileged \
  -v /var/run/docker.sock:/host/var/run/docker.sock \
  -v /dev:/host/dev -v /proc:/host/proc:ro -v /boot:/host/boot:ro \
  -v /lib/modules:/host/lib/modules:ro -v /usr:/host/usr:ro \
  -v "$PWD/falco/falco_rules.local.yaml:/etc/falco/falco_rules.local.yaml:ro" \
  falcosecurity/falco:latest
docker logs -f falco
```

`falco/falco_rules.local.yaml` berisi satu rule tambahan untuk pembacaan `/etc/passwd` di container. Rule bawaan Falco sengaja tidak mengawasi file ini karena memang boleh dibaca semua user.

Hasil uji (Falco 0.45.2, driver modern eBPF, WSL2 kernel 6.6):

| Aksi | Container `nginx` (root, default) | Container `p9-web` (hardened) |
|---|---|---|
| Shell dengan terminal (`docker exec -it`) | Notice: shell spawned | Notice: shell spawned (uid 10001) |
| `cat /etc/shadow` | Warning: sensitive file opened | gagal, *Permission denied* |
| `find / -name id_rsa*` | Warning: private key search | - |
| Menimpa file di `/var/log` | Warning: log files tampered | gagal, *Read-only file system* |
| Copy binary ke `/tmp` lalu dijalankan | Critical: binary not part of base image | gagal, `/tmp` noexec |
| `cat /etc/passwd` | Notice (custom rule) | Notice (custom rule) |
