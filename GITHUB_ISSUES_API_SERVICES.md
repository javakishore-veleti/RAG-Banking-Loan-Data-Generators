# GitHub Issues Plan — API Services & Local Development Platform

> Scope: local development platform (containers, scripts, commands) and
> the Entitlements API microservice, plus the container-image pattern
> for microservices. No LangChain / Strands agent endpoints yet — those
> are a later plan; the Entitlements service is what gates them.
>
> **Totals: 3 milestones, 5 epics, 18 features, 45 stories = 68 issues**
> (milestones are GitHub milestones, not issues; epics/features/stories
> are all GitHub issues, linked parent → child).
>
> **How to use this in GitHub:**
> 1. Create the 3 milestones (M008–M010) in the repo.
> 2. Create the 5 epic issues, label `epic`, assign each to its milestone.
> 3. Create the 18 feature issues, label `feature`, link to their epic.
> 4. Create the 45 story issues, label `story`, link to their feature.
> 5. Work milestone by milestone: M008 (local platform) → M009
>    (Entitlements API) → M010 (image pattern, template, portals).
>    Do not start M010 before M009 — the template and the image
>    workflow are copied from the Entitlements service.
>
> **Decisions already made (2026-11-12):**
> - Entitlements API is **FastAPI** (not Flask): async, built-in
>   validation, auto OpenAPI docs, JWT support.
> - Local infra (Postgres, Redis, ELK, RabbitMQ) runs as **Docker
>   containers** via docker-compose, managed by docker-all-*.sh.
> - Local apps and portals do **NOT** run as Docker containers —
>   they run via **.sh scripts** (start/stop/status per app/portal).
> - Docker **images** for microservices are built in CI **only on
>   main**, and published to AWS ECR by manual AWS-0xx workflows
>   (workflow_dispatch), just like the worker/indexer images.
> - Local Postgres: database `postgres`, user `postgres`, password
>   `postgres`; services get their own schema (Entitlements uses
>   schema `entitlements_db`). Multiple schemas, one server.
> - Schema changes use **Alembic** (Liquibase-style versioned
>   migrations, Python-native, uv-friendly). If literal Liquibase
>   is wanted instead, change F055 before building.
> - Roles (for now): Customer, Partner, Advisor, SuperAdvisor,
>   Customer Admin, Guest User. More roles come later; roles are
>   table-driven, not hard-coded.
> - Every microservice follows the Entitlements pattern:
>   `bin/start-app.sh` runs DB migrations, then starts the app.
> - Repo-root `package.json` is the local command front door:
>   `local:containers:all:*`, `local:middleware:apis:all:*`,
>   `local:portals:all:*` (each with start / stop / status).
>
> **Labels to create:** `epic`, `feature`, `story`, plus topical labels
> per issue — `api-services`, `entitlements`, `fastapi`, `local-dev`,
> `docker`, `docker-compose`, `postgres`, `redis`, `elk`, `rabbitmq`,
> `uv`, `migrations`, `alembic`, `ecr`, `package-json`, `microservices`,
> `portals`, `testing`, `docs`. Every issue gets its type
> label *and* its topical labels. The mapping lives in
> `scripts/create_issues.py` (`EPIC_LABELS` / `FEATURE_LABELS`);
> stories inherit their feature's labels.
>
> **Status as work progresses:** issues are closed as their code
> lands and is verified, via a close workflow (same pattern as
> `scripts/close_issues.py`). Nothing is closed without Kishore
> approving the list — closing is the status change itself.
> See `GITHUB_ISSUES.md` for the Datagen plan (127 issues) and
> `GITHUB_ISSUES_INDEXING.md` for the indexing plan (53 issues).

---

## Milestones (3)

| # | Milestone | Goal | Exit criteria |
|---|---|---|---|
| M008 | Local Development Platform | All local infra runs with one command; Python toolchain is uv | docker-all-up brings up Postgres, Redis, ELK, RabbitMQ; status shows all healthy; package.json container commands work |
| M009 | Entitlements API Service | FastAPI Entitlements service: signup, signin, obtain features, roles | Local signup → signin → GET /features works end to end; migrations apply on start; 6 roles seeded |
| M010 | Microservice Images, Pattern & Portals | Every microservice builds an image, follows one template, portals run locally | Entitlements image in ECR via manual AWS-012; second service bootstraps from the template; Loan-Advisor runs locally against local APIs |

---

## Epics (5)

| # | Epic | Milestone | Features |
|---|---|---|---|
| E015 | Local container platform | M008 | F047–F051 |
| E016 | Local developer commands | M008 | F052–F053 |
| E017 | Entitlements API | M009 | F054–F058 |
| E018 | Microservice template & local runners | M010 | F059–F061 |
| E019 | Container images & ECR publishing | M010 | F062–F064 |

---

## Features & Stories (18 features, 45 stories)

### E015 — Local container platform (M008)

**F047 — Postgres via docker-compose**
- S121. CICD/Local/Postgres/docker-compose.yaml: Postgres, port, volume, healthcheck.
- S122. Multiple schemas in one server: database `postgres`, user `postgres`, password `postgres`; schema-per-service convention (`entitlements_db` reserved).
- S123. Postgres reachable from the host and from containers (connection string documented).

**F048 — Redis via docker-compose**
- S124. CICD/Local/Redis/docker-compose.yaml: Redis with persistence, port, healthcheck.
- S125. Redis reachable from FastAPI services (cache / session use).

**F049 — ELK via docker-compose**
- S126. CICD/Local/ELK/docker-compose.yaml: Elasticsearch (single-node dev) + Kibana.
- S127. Logstash pipeline receives application logs.
- S128. Kibana shows service logs (smoke check).

**F050 — RabbitMQ via docker-compose**
- S129. CICD/Local/RabbitMQ/docker-compose.yaml: RabbitMQ with management UI, port, healthcheck.
- S130. Queue / exchange naming conventions documented (per-service queues).

**F051 — docker-all scripts**
- S131. CICD/Local/docker-all-up.sh starts all local containers.
- S132. CICD/Local/docker-all-down.sh stops and removes them.
- S133. CICD/Local/docker-all-status.sh reports each container's state.

### E016 — Local developer commands (M008)

**F052 — package.json container commands**
- S134. `local:containers:all:start` / `stop` / `status` map to the docker-all scripts.
- S135. Per-service container commands (e.g. `local:containers:postgres:start`).

**F053 — uv for Python**
- S136. uv setup with lockfiles per service; Python version pinned.
- S137. CI installs and tests with uv.

### E017 — Entitlements API (M009)

**F054 — FastAPI service skeleton**
- S138. Middleware/API-Services/entitlements_api: FastAPI app + uv project + Dockerfile (own image) + health endpoint.
- S139. Config via environment (DB URL, Redis URL, JWT secret).
- S140. CI runs its tests.

**F055 — entitlements_db schema & migrations**
- S141. `entitlements_db` schema in local Postgres: users, roles, entitlements tables.
- S142. Alembic migrations: versioned, up/down, applied automatically on start.
- S143. Seed data: the 6 roles (Customer, Partner, Advisor, SuperAdvisor, Customer Admin, Guest User).

**F056 — SignUp & SignIn**
- S144. POST /signup: validation, password hashing, default role.
- S145. POST /signin: credential check, JWT access + refresh tokens.
- S146. Token-verification dependency protecting endpoints.

**F057 — Obtain features**
- S147. GET /features returns the caller's entitlements (roles → features map).
- S148. Role → feature mapping stored in tables (admin-changeable, not hard-coded).
- S149. New roles can be added without code changes (role table driven).

**F058 — bin/start-app.sh (migrate then start)**
- S150. entitlements_api/bin/start-app.sh runs migrations, then starts Uvicorn.
- S151. Local run works via package.json `local:middleware:apis:all:start`.
- S152. Health + logs visible (ELK shows logs; docker-all-status shows the service).

### E018 — Microservice template & local runners (M010)

**F059 — Microservice template**
- S153. Template layout documented (bin/start-app.sh, uv, Dockerfile, health endpoint).
- S154. A second service bootstraps from the template (smoke check).

**F060 — package.json middleware & portals commands**
- S155. `local:middleware:apis:all:start` / `stop` / `status` run the .sh runners (not Docker).
- S156. `local:portals:all:start` / `stop` / `status` run the portal .sh runners (not Docker).

**F061 — Portals local startup**
- S157. Loan-Advisor runs locally against the local APIs (config points at localhost).
- S158. Signup → signin flow works end to end from the portal (Guest → Customer).

### E019 — Container images & ECR publishing (M010)

**F062 — CI builds images on main only**
- S159. ci.yaml builds microservice Docker images only on main branch.
- S160. PR / branch runs skip image builds (fast CI).

**F063 — AWS-012: build & publish Entitlements image to ECR**
- S161. Manual workflow (workflow_dispatch) builds the entitlements image.
- S162. Image pushed to ECR repo `<project>-entitlements`, same secrets pattern as worker/indexer.
- S163. Manual trigger only; no auto-publish on push.

**F064 — Image pattern per microservice**
- S164. Reusable build workflow (or per-service convention) documented.
- S165. The next microservice gets its image workflow by copying the pattern.
