# Deploy Online

This Flask app is ready for platforms like Render, Railway, or Heroku-style hosts.

Required environment variables:

```env
OPENROUTER_API_KEY=your-openrouter-key
FLASK_SECRET_KEY=change-this-to-a-random-secret
```

Start command:

```bash
gunicorn app:app
```

Notes:

- Temporary chat memory is stored in RAM and clears when the server restarts.
- `users.json` is local file storage. On many free hosts, uploaded users may reset after redeploy or restart.
