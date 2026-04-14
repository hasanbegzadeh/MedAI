# RadAI AI Tools Panel — OHIF v3.12 Extension

## Status: Scaffold Complete

The extension files are created but require building before loading in OHIF.

## Files

| File | Purpose |
|------|---------|
| `package.json` | NPM package definition |
| `src/index.js` | React component + OHIF extension definition |
| `webpack.config.js` | Build configuration |
| `dist/radai-ai-panel.js` | Runtime-injectable version (no build needed) |

## How to Build (when ready)

```bash
cd viewer/extensions/radai-ai-tools
npm install
npm run build
```

## How to Load (Runtime Injection — No Build)

The `dist/radai-ai-panel.js` file can be injected at runtime without rebuilding OHIF.

### Option A: Modify OHIF index.html

Add this to the OHIF `index.html` before `</body>`:

```html
<script src="/extensions/radai-ai-panel.js"></script>
```

Then volume-mount the script:

```yaml
# docker-compose.yml
ohif:
  volumes:
    - ./viewer/extensions/radai-ai-tools/dist/radai-ai-panel.js:/usr/share/nginx/html/extensions/radai-ai-panel.js:ro
```

### Option B: Nginx Injection

Add to `docker/nginx/nginx.conf`:

```nginx
location /extensions/ {
    alias /etc/nginx/extensions/;
}
```

Then mount the extension directory:

```yaml
nginx:
  volumes:
    - ./viewer/extensions/radai-ai-tools/dist:/etc/nginx/extensions:ro
```

## Features

- **Run TotalSegmentator** button — triggers AI analysis on current study
- **Progress bar** — real-time progress polling from backend
- **Job history** — lists completed segmentation jobs
- **Error display** — shows errors if job fails

## API Integration

The panel calls:
- `POST /api/v1/ai/studies/{studyId}/run` — Start AI job
- `GET /api/v1/ai/jobs/{jobId}` — Poll job status

Both endpoints require authentication (JWT token).
