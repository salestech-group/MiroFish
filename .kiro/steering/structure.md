# Project Structure

## Organization Philosophy

A **monorepo split by runtime** (`backend/` Python, `frontend/` Vue),
with each side organized **by layer**:

- Backend: `api/` (HTTP) → `services/` (logic) → `models/` (state) →
  `utils/` (cross-cutting helpers), with `config.py` as the single source
  of configuration.
- Frontend: `views/` (route-level pages) → `components/` (reusable UI) →
  `api/` (HTTP services) → `store/`, `router/`, `i18n/`, `assets/`.

The core workflow is **pipeline-shaped** (5 sequential steps), and the
codebase mirrors that: each step has a backend service or service group,
a Flask blueprint endpoint, a frontend Step component, and (where useful)
a route-level view.

## Directory Patterns

### Backend HTTP Layer
**Location**: `backend/app/api/`
**Purpose**: One Flask blueprint per pipeline domain — thin handlers
that validate input, dispatch to services, and return JSON. No business
logic.
**Files**: `graph.py` (`graph_bp`), `simulation.py` (`simulation_bp`),
`report.py` (`report_bp`).

### Backend Services
**Location**: `backend/app/services/`
**Purpose**: All business logic. Each file owns one responsibility
(graph build, profile generation, simulation runner, report agent, etc.).
**Pattern**: Long-running operations expose an async/background entrypoint
that returns a `Task` and runs work off the request thread. Direct calls
to Neo4j, OASIS subprocesses, or LLM streaming live here, not in `api/`.
### Backend State Models
**Location**: `backend/app/models/`
**Purpose**: In-memory, JSON-serializable state objects. `Project`
tracks per-project pipeline state and `group_id`; `Task` tracks
background-job status, progress, and result. These are the polling
contract with the frontend — change their shape with care.

### Backend Utilities
**Location**: `backend/app/utils/`
**Purpose**: Cross-cutting helpers usable from any service —
LLM client wrapper (`llm_client.py`), file parsing (`file_parser.py`),
retry (`retry.py`), logging (`logger.py`), locale (`locale.py`),
pagination helpers (`graph_paging.py`).
**Rule**: Utils never import from `services/` or `api/`.

### Backend Config
**Location**: `backend/app/config.py`
**Purpose**: Single file for LLM, Neo4j, embedding, chunking, OASIS,
and ReportAgent parameters. Read env vars here; consume the resulting
constants elsewhere. Avoid `os.getenv` calls scattered through services.

### Frontend Views (Routes)
**Location**: `frontend/src/views/`
**Purpose**: Page-level components mapped to routes (`Home.vue`,
`MainView.vue`, `Process.vue`, `SimulationView.vue`,
`SimulationRunView.vue`, `InteractionView.vue`, `ReportView.vue`).
**Pattern**: `Process.vue` is the workflow orchestrator (~50KB); it
composes the Step components and owns step transitions.

### Frontend Components
**Location**: `frontend/src/components/`
**Purpose**: Reusable UI. Step components (`Step1GraphBuild.vue`,
`Step2EnvSetup.vue`, `Step3Simulation.vue`, `Step4Report.vue`,
`Step5Interaction.vue`) implement one pipeline stage each;
`GraphPanel.vue` renders the D3 knowledge graph;
`HistoryDatabase.vue`, `LanguageSwitcher.vue` are general-purpose.

### Frontend API Services
**Location**: `frontend/src/api/`
**Purpose**: Axios services that wrap the backend blueprints —
`graph.js`, `simulation.js`, `report.js`, with `index.js` as the shared
client (5-min timeout, exponential retry).
**Rule**: Components and views call these services; they do not import
`axios` directly. New endpoints add a method on the matching service.

### Locales (shared)
**Location**: `/locales/` at repo root
**Purpose**: i18n source for both frontend (`vue-i18n`) and backend
(logger). Vite aliases `@locales` to this folder. Files: `en.json`,
`zh.json`, `languages.json`.

### Static Assets
**Location**: `static/` at repo root
**Purpose**: Images and demo assets referenced from READMEs (logos,
screenshots, video covers). Not bundled by Vite.

## Naming Conventions

- **Python files / modules / functions / vars**: `snake_case`
- **Python classes**: `PascalCase`
- **Python constants**: `UPPER_SNAKE_CASE`
- **Vue Single-File Components**: `PascalCase.vue`
- **Vue route views**: `<Name>View.vue` or domain noun
  (`Home.vue`, `Process.vue`, `MainView.vue`)
- **Vue step components**: `Step<N><Name>.vue` (matches the pipeline stage)
- **Frontend non-component JS**: `camelCase.js` (e.g.
  `pendingUpload.js`)
- **Locale files**: lowercase ISO code (`en.json`, `zh.json`) +
  `languages.json` for the language list
- **Booleans (Python and JS)**: prefix with `is_` / `has_` / `should_`
  where it improves clarity, but match local style first

## Import Organization

### Frontend (`frontend/src/`)
```js
// Vendor
import { ref, computed } from 'vue'
import axios from 'axios'

// Absolute (via @ alias)
import GraphPanel from '@/components/GraphPanel.vue'
import { fetchGraph } from '@/api/graph'

// Locales (shared with backend)
import en from '@locales/en.json'

// Relative (same feature only)
import { useStep } from './useStep'
```

**Path aliases** (`vite.config.js`):
- `@/` → `frontend/src/`
- `@locales` → repo-root `/locales/`

### Backend (`backend/app/`)
- Use absolute package imports (`from app.services.graph_builder import ...`).
- Layer dependency rule: `api → services → models / utils`. Services
  may import from `models` and `utils`; `models` and `utils` never
  import from `services` or `api`.
- All Neo4j/Graphiti access goes through `services/graphiti_adapter.py`.

## Code Organization Principles

- **Pipeline-aligned modules.** When adding a new pipeline-touching
  feature, place code in the same backend service group and the same
  frontend Step component as the stage it belongs to. Don't split a
  stage across multiple services unless responsibilities genuinely
  diverge.
- **Background tasks are uniform.** Any operation taking more than a
  few seconds returns a `Task` and is polled. Don't introduce ad-hoc
  status fields on `Project`; extend `Task`.
- **Per-project isolation.** Every graph operation must filter by
  `group_id`. Cross-project reads are out of scope and should be
  flagged in review.
- **IPC has one door.** Subprocess communication for the simulator goes
  through `services/simulation_ipc.py`. Do not call `subprocess` /
  pipe primitives elsewhere.
- **Configuration is centralized.** New tunables go in
  `backend/app/config.py` (and an `.env.example` line if env-driven),
  not as constants scattered through services.
---
_Document patterns, not file trees. New files following patterns shouldn't require updates_
