# How You Build This: Claude Code Setup and Working Method

This is your operating manual. The companion file (ARGUS_REBUILD_SPEC.md) is what you hand to the builder. In this case the builder is Claude Code with you directing it.

> **Post-original sourcing note (2026-07-03):** this manual predates the loss of ARGUS access. Wherever it says to export goldens from ARGUS or to compare against ARGUS output (sections 4 and 7), read the **Golden-File Strategy in [CLAUDE.md](CLAUDE.md)** instead: **five OM-based goldens** spanning complexity, each validated annually at fiscal-year level within $500/line; a **monthly-resolution hand schedule for Clorox only** (base rent, steps, inflation timing, expense growth — not a full DCF) that adjudicates month-level timing questions the annual OM data cannot discriminate; and the manual's worked examples. The working method itself — one module at a time, the session loop, the things to refuse — is authoritative as written.

## 1. The honest framing

You have limited coding experience. That is fine for this project under one condition: you never write code and you never debug code by reading it. Your job is exactly the job you already do well: define requirements, review outputs against known-good numbers, and refuse to accept work that fails validation. Claude Code writes, tests, and fixes. You are the IC, not the analyst.

Time expectation: 6-12 weeks of consistent evening/weekend sessions to reach Phase 4 (validated engine + reports + Excel export). The UI phase is faster than the engine phase. If someone tells you a weekend, they have not built a recovery engine.

## 2. Tooling decision (made for you)

**Use Claude Code inside VS Code.** Not the web chat, not raw terminal.

Why VS Code over plain terminal: you get a file tree, you can open and eyeball Excel/CSV outputs, you can see test results in a panel, and the Claude Code extension shows you diffs before changes are applied. For a non-coder, seeing the file system is the difference between directing the work and being lost in it. The Claude Desktop app's Code tab also works and is acceptable if you prefer it; VS Code is recommended because you will be opening exported Excel files constantly.

Setup order:
1. Install VS Code (code.visualstudio.com)
2. Install Python 3.11+ (python.org; check "Add to PATH" on Windows)
3. Install Git (git-scm.com)
4. Install Node.js LTS (nodejs.org), then in a terminal: `npm install -g @anthropic-ai/claude-code`
5. In VS Code, install the "Claude Code" extension from the marketplace and sign in with your Anthropic account
6. GitHub: create a new PRIVATE repository named `ironclad` (or your name of choice). Private matters: your golden files will contain real deal data.

Note: verify current install steps at docs.claude.com if anything above fails; commands change.

## 3. Project setup (your first session, ~30 minutes)

1. Create a folder, e.g. `C:\dev\ironclad` (or `~/dev/ironclad` on Mac). Open it in VS Code.
2. Copy into it:
   - `ARGUS_REBUILD_SPEC.md` (rename nothing)
   - `reference/Argus_Training_Guide.pdf` (create the reference folder)
3. Open the Claude Code panel and give it this first prompt:

> Read ARGUS_REBUILD_SPEC.md in full. Then create a CLAUDE.md file for this repo that: summarizes the architecture and the phase gates, states the three iron rules (1: engine code never imports UI code, 2: no phase advances until its golden-file gate passes, 3: every calc module gets unit tests from the manual's worked examples, with page citations in test docstrings), and notes that reference/Argus_Training_Guide.pdf is the authoritative behavioral reference with page cites in the spec. Then initialize the repo structure exactly per spec section 2.2, set up a Python virtual environment with the dependencies from section 2.1, create the pydantic models for spec section 3, make JSON round-trip tests pass, and commit to git with a sensible message. Do not build any calculation logic yet.

4. When it finishes, tell it: `Push this to my GitHub repo` and follow its authentication instructions.

That is Phase 0. From then on, every session starts with Claude Code reading CLAUDE.md automatically, so it never loses the plot.

## 4. Your working method (this is the part that determines success)

**One phase at a time, one module at a time.** Never say "build the whole engine." Say "Implement Phase 1 lease base rent per spec section 3.12 and 4.1 step 4, including unit tests for every worked example on manual pages 391-394, then show me the test results."

**The golden files are your leverage.** Before Phase 1 gets far, do this:
1. Pick three real deals you have in ARGUS (or can borrow runs of): one simple single-tenant net lease, one multi-tenant office with base-year stops and rollover, one retail deal with percentage rent.
2. Export from ARGUS to Excel: Annual + Monthly Cash Flow, Lease Audit, Recovery Audit, Present Value, Resale, and the IRR/returns summary.
3. Drop them in `tests/golden/<dealname>/` and tell Claude Code: "Build the input JSON for golden property 1 from this ARGUS export, then write a pytest that compares our engine's cash flow to it line by line within $1/month."
This converts your ARGUS expertise directly into acceptance tests. It is the single highest-value thing you personally contribute. Without it you are trusting vibes; with it you are trusting diffs.

**Session loop (repeat until done):**
1. State the next spec section to implement.
2. Claude Code implements + writes tests + runs them.
3. You review: ask it to "export the current cash flow for golden property 2 to Excel and list every line that differs from the ARGUS export, with the delta." Open the Excel. You will spot wrong recovery math faster than any programmer alive.
4. Differences found: paste the specific tenant/month/line back and say "trace the calculation for this cell and explain the divergence against manual pages X-Y." Make it show its work.
5. Green: "Commit and push. Update CLAUDE.md progress notes. What is next per the roadmap?"

**Things to refuse:**
- Any offer to "move on and fix the recovery discrepancy later." Later never comes and it poisons everything downstream.
- Any UI work before Phase 3's gate. When you get bored of engine work (you will, around week 3), that boredom is the failure mode. The dashboard is the dessert.
- Scope creep from yourself. Multifamily, budgeting, hotels: v2. The spec's section 11 exists so you can point Claude Code at it when you get tempted.

**When you get stuck** (tests fail repeatedly, Claude Code loops): start a fresh Claude Code session (context gets cluttered), and open with "Read CLAUDE.md and tests/golden/README. The failing test is X. Reproduce, then diagnose from first principles against manual pages Y-Z before writing any code."

## 5. Costs and infrastructure

- Claude Code usage runs on your existing plan limits; heavy weeks on a big build like this may hit them. If it becomes the bottleneck, that is a signal the project is working, not failing.
- No servers needed for v1. The Streamlit app runs locally (`streamlit run ui/app.py`) and opens in your browser. It looks and behaves like a web app; it just runs on your machine. When you later want it hosted (access from anywhere, or to show partners), the same code deploys to Streamlit Community Cloud (private app) or a $10-20/month VM in under a day. Do not think about hosting until Phase 5 is done.
- Backups: GitHub is your backup. Commit every session. Golden files with sensitive deal data: keep the repo private, or keep goldens in a local-only folder listed in .gitignore if partners ever get repo access.

## 6. When to bring in a human developer

You likely will not need one through Phase 5. Bring one in (a week of contract work, not a hire) only if: (a) Phase 2 recovery/rollover math resists two full weeks of golden-file debugging, or (b) you outgrow Streamlit and want the React/desktop-grade front end. In either case, this spec plus your test suite is the handoff package, and it is a dramatically better handoff than 99% of contractors ever receive. That was the point of writing it this way.

## 7. Definition of done for v1

You open the app, import a rent roll from the Excel template, set market assumptions, click Calculate, see the dashboard, flip any report between total and $/SF, drill an audit trail on a recovery number, and export a formatted Excel package: and the numbers match what ARGUS would say within rounding. Everything else is decoration.
