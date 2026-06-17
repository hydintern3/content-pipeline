# Frontend

Vue 3 + Vite + TypeScript workspace for `content_pipeline`.

## Development

Run the Flask API from the project root:

```powershell
python app.py
```

Then run the frontend dev server from this folder:

```powershell
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. Vite proxies `/api` requests to `http://127.0.0.1:5000`.

## Production

Build the frontend:

```powershell
npm run build
```

The build output goes to `frontend/dist`. Flask serves that folder automatically when it exists.
