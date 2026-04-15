# SPIMUN 2026 — MUN Conference Website

> **St. Peter's International Model United Nations 2026**  
> Hosted at St. Peter's International School, Palmela, Portugal — March 20–21, 2026  
> Live at [spimunconference.org](https://spimunconference.org)

A full-stack conference website built and self-hosted on a **Raspberry Pi**, publicly served via **Cloudflare Tunnel**. No cloud hosting, no monthly fees.

---

## Features

- Multi-page website with smooth-scroll navigation
- Hero section with background image and animated emblem
- Conference schedule (Day 1 & Day 2 timelines)
- 3 committee cards with issue descriptions, PDF downloads, and chairs toggle
- Dynamic gallery managed by admins — unlimited photos, add/remove from portal
- Staff/Secretariat section with show/hide toggle
- FAQ accordion
- Rules of Procedure PDF viewer
- Articles & News system — publish Canva PDFs or text articles
- "Follow Us" section with Instagram & TikTok links
- Contact form via Web3Forms
- Delegate login & registration system
- Admin portal with full conference management

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Plain HTML, CSS, JavaScript (single file) |
| Backend | Python 3 + Flask |
| Web server | Nginx |
| Database | JSON files (no external DB needed) |
| Tunnel | Cloudflare Tunnel (`cloudflared`) |
| Hardware | Raspberry Pi 4 |
| PDF processing | PyMuPDF (`fitz`) |

---

## Project Structure

```
/var/www/html/
├── index.html          # Main website
├── portal.html         # Delegate & admin portal
├── articles.html       # Article listing (tile grid)
├── article.html        # Single article view
├── server.py           # Flask backend (port 5001)
├── hero.avif           # Hero background image
├── photos/             # Staff, committee, gallery photos
├── article-images/     # Article cover images
├── article-files/      # Uploaded PDFs + converted page images
├── gallery/            # Admin-uploaded gallery photos
└── data/
    ├── users.json       # Delegate accounts
    ├── tokens.json      # Auth tokens
    ├── articles.json    # Published articles
    ├── gallery.json     # Gallery photo list
    └── announcement.json
```

---

## Setup on Raspberry Pi

### 1 — Install dependencies

```bash
sudo apt update
sudo apt install nginx -y
pip3 install flask flask-cors pymupdf --break-system-packages
```

### 2 — Deploy files

```bash
sudo cp index.html portal.html articles.html article.html /var/www/html/
sudo cp server.py /var/www/html/
sudo mkdir -p /var/www/html/photos /var/www/html/data
sudo mkdir -p /var/www/html/article-images /var/www/html/article-files /var/www/html/gallery
sudo chown -R www-data:www-data /var/www/html/
```

### 3 — Configure Nginx

Replace `/etc/nginx/sites-enabled/default` with:

```nginx
server {
    listen 80 default_server;
    listen [::]:80 default_server;

    root /var/www/html;
    index index.html;
    server_name _;

    client_max_body_size 100m;

    location / {
        try_files $uri $uri/ =404;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:5001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

```bash
sudo nginx -t && sudo systemctl reload nginx
```

### 4 — Create systemd service for Flask backend

```bash
sudo nano /etc/systemd/system/spimun-api.service
```

```ini
[Unit]
Description=SPIMUN API Server
After=network.target

[Service]
WorkingDirectory=/var/www/html
ExecStartPre=/bin/bash -c 'fuser -k 5001/tcp || true'
ExecStart=/usr/bin/python3 /var/www/html/server.py
Restart=always
RestartSec=3
User=root

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable spimun-api
sudo systemctl start spimun-api
```

### 5 — Set up Cloudflare Tunnel

```bash
# Install cloudflared
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64 -o cloudflared
sudo mv cloudflared /usr/local/bin/
sudo chmod +x /usr/local/bin/cloudflared

# Authenticate and create tunnel
cloudflared tunnel login
cloudflared tunnel create spimun

# Create config
sudo mkdir -p /etc/cloudflared
sudo nano /etc/cloudflared/config.yml
```

```yaml
tunnel: YOUR-TUNNEL-ID
credentials-file: /etc/cloudflared/YOUR-TUNNEL-ID.json

ingress:
  - hostname: yourdomain.com
    service: http://localhost:80
  - service: http_status:404
```

```bash
sudo cp ~/.cloudflared/YOUR-TUNNEL-ID.json /etc/cloudflared/
cloudflared tunnel route dns spimun yourdomain.com
sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
```

### 6 — Enable auto-start on boot

```bash
sudo systemctl enable nginx
sudo systemctl enable cloudflared
sudo systemctl enable spimun-api
```

---

## Default Admin Account

```
Email:    admin@spimun.org
Password: spimun2026admin
```

**⚠️ Change this immediately after first login via the portal.**

---

## Admin Portal Features

| Tab | What you can do |
|---|---|
| 👥 Delegates | View all accounts, assign committee/country, add notes, change roles |
| 📰 Articles | Write articles or upload Canva PDFs — auto-converts to images |
| 🖼 Gallery | Upload/remove gallery photos with no limit |
| 📢 Announcement | Show a live gold banner on the main site |
| 🔑 Password | Change admin password |

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/register` | Create delegate account |
| POST | `/api/login` | Login, returns token |
| GET | `/api/me` | Get current user info |
| POST | `/api/logout` | Logout |
| GET | `/api/articles` | List published articles |
| GET | `/api/articles/:id` | Get single article |
| GET | `/api/gallery` | List gallery photos |
| GET | `/api/admin/delegates` | List all delegates (admin) |
| POST | `/api/admin/assign` | Assign committee/country (admin) |
| POST | `/api/admin/articles` | Create article (admin) |
| PUT | `/api/admin/articles/:id` | Update article (admin) |
| DELETE | `/api/admin/articles/:id` | Delete article (admin) |
| POST | `/api/admin/upload-pdf` | Upload Canva PDF (admin) |
| POST | `/api/admin/gallery` | Upload gallery photo (admin) |
| DELETE | `/api/admin/gallery/:id` | Remove gallery photo (admin) |
| GET/POST | `/api/admin/announcement` | Get/set announcement banner (admin) |

---

## Updating the Site

```bash
# Copy new HTML to Pi
scp index.html ivan@ivank.local:/home/ivan/
ssh ivan@ivank.local 'sudo cp ~/index.html /var/www/html/index.html'

# Restart backend after server.py changes
sudo systemctl restart spimun-api
```

---

## Troubleshooting

```bash
# Check all services
sudo systemctl status nginx cloudflared spimun-api

# Restart everything
sudo systemctl restart nginx cloudflared spimun-api

# View backend logs
sudo journalctl -u spimun-api -n 50

# Check nginx config
sudo nginx -t
```

---

## Built by

Ivan Kruchinin — Head of IT, SPIMUN 2026  
St. Peter's International School, Palmela, Portugal
