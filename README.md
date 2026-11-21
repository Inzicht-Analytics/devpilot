# DevPilot

Supervised autonomous development agent — Milestone 1 foundation.

**Current functionality:** illustrative React dashboard, Python planning-only action policy and unit tests, proposed Supabase migration, and CI validation. No live agent execution or repository-writing capability is enabled.

## Repository layout
- `apps/dashboard` — React/Vite static task preview
- `services/agent` — deny-by-default Python policy
- `supabase/migrations` — proposed private database schema, **not applied**
- `docs` — architecture and security requirements
- `.github/workflows/ci.yml` — test/build checks with a committed dependency lockfile

## Local development
Node 22+ and Python 3.11+ are recommended.

```sh
cd apps/dashboard
npm ci
npm run dev
```

```sh
cd services/agent
python -m unittest discover -s tests -v
```

## Milestone 1 exit criteria
- [x] Private repository and feature branch
- [x] Dashboard, policy and database schema scaffold
- [x] GitHub Actions CI configured
- [x] Commit `apps/dashboard/package-lock.json` and use `npm ci` in CI
- [ ] CodeRabbit review completed and findings addressed
- [ ] New CI checks pass on final commit

## Approval rules
Do not merge before CI passes, CodeRabbit review is complete, and the owner explicitly approves. Do not deploy to production without explicit approval. The database migration is a proposal only.

See [architecture](docs/architecture.md) and [security policy](docs/security.md).
