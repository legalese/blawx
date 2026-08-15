# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Blawx (v1.6.x-alpha, `BLAWX_VERSION` in `blawx/settings.py`) is a web-based Rules-as-Code tool: legal rules are drafted as Blockly block diagrams, compiled to **s(CASP)** (goal-directed answer set programming under SWI-Prolog), and executed with natural-language justifications. It is a single Django project/app (both named `blawx`, so code lives in `blawx/blawx/`) with a SQLite database. An immediate project goal is an **L4 → Blawx transpiler**; the sections below on semantics, syntax, and targeting exist to support that work.

## Commands

Docker is the only supported way to build and run:

```bash
docker build -t blawx .            # add --build-arg SU_PASSWORD=... to set admin password (default admin/blawx2022)
docker run -it -p 8000:8000 blawx  # serves http://localhost:8000; ./update.sh does both steps
```

- Rebuild with `--no-cache` when Blockly/npm-fetched frontend deps must be refreshed (they are downloaded in the Dockerfile, not vendored in the repo).
- Release images: `docker build -t lexpedite/blawx:<version> -t lexpedite/blawx:latest .`; bump `BLAWX_VERSION` in `blawx/settings.py` and add a `CHANGELOG.md` entry together.
- There is **no automated test suite** (`blawx/tests.py` is an empty stub) and no linter. Verification is manual: load an example project (front page → Load Example, sourced from `blawx/static/blawx/examples/*.yaml`) and run its tests in the UI, or POST to the run endpoint.
- Running outside Docker requires SWI-Prolog with the s(CASP) pack installed (see Dockerfile lines 29–41), `pip install -r blawx/requirements.txt`, `python manage.py makemigrations && python manage.py migrate --run-syncdb`, `python load_data.py` (loads docs + fixtures, creates "All users" group), then `python manage.py runserver`. Beware: some code hardcodes the Docker path `/app/blawx/...` (e.g. `views.exampleLoadView`).

## Architecture

**Data model** (`models.py`): a `RuleDoc` holds the legal source text (`rule_text`, in CLEAN markup; a `pre_save` signal compiles it to Akoma Ntoso XML via the `clean-law` package and builds an HTML navtree via `parse_an.py`). Each *section* of that text gets a `Workspace` (named after the section's Akoma Ntoso eId + `_section`, e.g. `sec_1_section`, plus `root_section`). A `BlawxTest` is a workspace holding a query plus a saved fact scenario and scenario-editor view. Workspaces and tests each store **two parallel representations**: `xml_content` (Blockly XML) and `scasp_encoding` (generated s(CASP) text).

**Code generation happens in the browser, never on the server.** `static/blawx/scasp_generator.js` is the authoritative block→s(CASP) mapping (a Blockly `Generator` named `sCASP`); on save, `buttons.js` POSTs both the workspace XML and the freshly generated s(CASP) to `/<user>/<rule>/<workspace>/update/`, and the server (`views.update_code`) stores both verbatim. Nothing server-side ever derives one representation from the other. (`blawx2scasp.js` is dead commented-out code; ignore it.) Block shapes/UI live in `blawx-blocks.js` (the `scasp_blockset` JSON plus programmatic patches), `mutators.js`, `attributes.js`, `drawers.js`; `util/blawx_block_library.xml` + `util/blawx_block_definitions.json` are the Blockly Developer Tools sources for regenerating them (workflow in `util/README.md`).

**Reasoner** (`reasoner.py`): `run_test` concatenates into a temp file: a `blawxrun/4` harness wrapping `scasp/2` (justification tree + model), then injected Prolog libraries — `passthrough.py` (`blawx_comparison`, `blawx_diseq`), `ldap.py` (NLG for `blawx_applies`), `dates.py` (`date_compare`/`duration_compare`/`date_add` + `blawx_now`/`blawx_today` stamped from the server clock at import time), `aggregates.py` (list count/sum/average/min/max, event-list helpers), `events.py` (date↔datetime coercions) — then every workspace's `scasp_encoding`, the test's, and the JSON fact scenario translated by `even_newer_json_2_scasp`. It runs via `swiplserver` (Prolog MQI). The query is whichever line of the test encoding starts with `?- `. Lines following a `% BLAWX CHECK DUPLICATES` marker are variable-renamed (`simplify_rule`) and deduplicated across all workspaces before loading — this is how the per-rule `holds`/conclusion bridge rules avoid being asserted once per section. `interview` is the same pipeline but additionally mines `chs(...)` assumptions out of the justification tree to return "Relevant Statements" (drives the scenario editor's interview loop); `get_ontology` queries the `blawx_category`/`blawx_attribute`/`blawx_relationship` (+`_nlg`) facts to serve the ontology as JSON. `simplifier.py` is an optional OpenAI paraphrase of explanations (needs `OPENAI_API_KEY`).

**Key HTTP API** (all in `urls.py`, session-auth):
- `/<user>/<rule>/<workspace>/update/` and `.../get/`, `/<user>/<rule>/all/get/` — workspace code
- `/<user>/<rule>/test/<test>/update/`, `.../run/`, `.../onto/`, `.../interview/` — tests and execution
- `/<user>/<rule>/export/` → a `.blawx` file; `/import/` accepts one. The `.blawx` format is concatenated Django `dumpdata` YAML: one `blawx.ruledoc`, then `blawx.workspace` and `blawx.blawxtest` entries. `manage.py loaddata` also accepts these (primary-key collisions matter; see INSTALL.md §Integration).

**In-app language documentation** is Django fixtures under `blawx/fixtures/docs/` (one YAML per page, markdown content) — `docs/blocks/**` is a per-block reference worth consulting before relying on any block's semantics.

## The Blawx language: what generated code looks like

Everything below is defined by `scasp_generator.js` and the injected libraries; a transpiler must reproduce these conventions exactly.

**Ontology declarations are load-bearing.** `new_category_declaration`, `new_attribute_declaration`, and `relationship_declaration` blocks emit, per predicate: (1) queryable ontology facts `blawx_category/1`, `blawx_attribute/3` (category, attribute, value-type), `blawx_relationship/N`, plus `*_nlg` facts carrying prefix/infix/postfix display strings; (2) `:- dynamic pred/N.`; (3) ~20 `#pred ... :: '...'` NLG annotations (for the bare predicate and for its `holds`/`according_to`/`blawx_defeated`/temporal wrappings); (4) a full set of per-predicate temporal frame axioms deriving `blawx_as_of`, `blawx_during`, `blawx_not_interrupted` from `blawx_initially`, `blawx_ultimately`, and `blawx_becomes` events (with `bot`/`eot` as beginning/end-of-time markers). Undeclared predicates therefore lack NLG, scenario-editor visibility, and temporal reasoning. Categories are unary, attributes binary (declared against a category, with a value type), relationships arity 3–10. Value types: `boolean`, `number`, `date`, `time`, `datetime`, `duration`, `list`, or a category name. **Boolean attributes are special-cased into unary predicates** (`likes_cats(X)` rather than `likes_cats(X,true)`).

**Rules.** The `attributed_rule` block (source = a `doc_selector` holding a section reference like `sec_1_section`) generates a defeasibility triple with the conclusion *flattened* — the predicate name becomes an argument:

```prolog
according_to(sec_1_section,mortal,A) :- human(A).
% BLAWX CHECK DUPLICATES
holds(sec_1_section,mortal,A) :- according_to(sec_1_section,mortal,A), not blawx_defeated(sec_1_section,mortal,A).
% BLAWX CHECK DUPLICATES
mortal(A) :- holds(sec_1_section,mortal,A).
```

The `not blawx_defeated(...)` guard appears only when the rule's "defeasible" checkbox is TRUE; with "subject to applicability" checked, each category condition `cat(X)` also gains `blawx_applies(Section,X)`. Negative conclusions use classical negation: `-mortal(A)`. Exceptions: the `overrules` block emits `blawx_defeated(Weaker,Concl...) :- holds(Stronger,Concl...)`; `opposes/2` declares conflicting conclusions (auto-emitted both ways for boolean attribute true/false). Plain facts are bare assertions; constraints are `false :- conditions.`; assumptions are `#abducible fact.` (the basis of hypothetical reasoning and the interview endpoint). Queries exist only in tests, as a single `?- goal.` line.

**Terms and operators.** Variables are capitalized text (`A`), silent variables underscore-prefixed (`_X`), anonymous is `_`; objects/categories/attributes must be valid unquoted lowercase Prolog atoms (blocks do no quoting or escaping). Object equality/disequality: `X = Y` / `blawx_diseq(X,Y)`. Arithmetic: `Var is Expr` with `+ - * /`; constraint comparison: `blawx_comparison(X,Op,Y)` with `Op ∈ eq|neq|gt|gte|lt|lte` (implemented over `#=`, `#>`, … so it works on unbound constrained vars). Lists: `[]`, `[H|T]`, `findall(Var,Goal,List)` (`collect_list` block), then `count_blawx_list`/`sum_blawx_list`/`average_blawx_list`/`min_blawx_list`/`max_blawx_list`.

**Dates and times** are functor-wrapped POSIX numbers: `date(Timestamp)`, `datetime(Timestamp)`, `time(SecondsSinceMidnight)`, `duration(Seconds)` (durations from the value block are days/hours/minutes/seconds only — no calendar months/years). Comparisons: `date_compare(A,Op,B)` (any date/datetime/time mix) and `duration_compare/3`, same `Op` atoms as above but `ne` not `neq`; addition: `date_add(Date,DurationOrTime,DatetimeOut)`. `blawx_now(datetime(T))`/`blawx_today(date(T))` are injected server-side. **Gotcha:** several date blocks generate calls to predicates that are defined nowhere (`days_between_datetimes`, `datetime_diff_duration`, `datetime_add_days`, `datetime_to_posix_timestamp`, `posix_timestamp_to_datetime`) and the `date_calculate`-family blocks emit multi-argument forms (`date(Y,M,D)`) the libraries don't match — treat all of these as broken and stick to the timestamp forms plus `date_add`/`date_compare`/`duration_compare`. Timestamps for literals are computed client-side with the browser's local timezone (`new Date(...)/1000`); the fact-scenario translator uses Python `datetime.timestamp()` — reproduce this, don't assume UTC.

## L4 ↔ Blawx expressiveness overlap (for the transpiler)

**Transpiles naturally:**
- L4 constitutive/decision logic (`DECIDE ... IF`, boolean `GIVEN/GIVETH ... MEANS`) → attributed rules; L4's isomorphic-encoding discipline maps directly onto Blawx's section-anchored workspaces + `doc_selector` attribution (RuleDoc CLEAN text supplies the §-structure).
- L4 record types → categories + typed attributes; enum types → categories or atoms; predicates over entities → attributes/relationships (arity ≤ 10).
- Defeasance: L4 "subject to / notwithstanding / despite" patterns → the defeasible flag + `overrules`/`opposes`/`blawx_defeated`, which is *more* expressive than vanilla L4 boolean logic here (Blawx resolves conflicts at the rule level with explanations intact).
- Date logic (`daydate`) → `date_add`/`date_compare`, within the limits above (seconds-resolution, no calendar-month arithmetic).
- Simple aggregation (sum/count/min/max/average over a comprehension) → `findall` + aggregate predicates.

**Requires compilation strategy:**
- Blawx is relational, not functional: every L4 function returning a value must be relationalized (result becomes an extra argument, calls become conjoined goals introducing fresh variables). No lambdas, no higher-order functions, no partial application; `map`/`filter`/`fold` must be flattened into recursion over `[H|T]` rules or into `findall` idioms.
- ADTs with payloads, `MAYBE`, and `CONSIDER/WHEN` pattern matching must be compiled away (e.g. constructor-tagged terms plus discriminating rules); Blawx blocks have no native ADT construct.
- Three-valued semantics: s(CASP) distinguishes provably-true / provably-false (`-p`) / unknown (`not p` = negation-as-failure), and the scenario editor leans on this plus `#abducible`. L4's two-valued `NOT` needs an explicit policy: classical `-p` for asserted falsity, `not p` for absence-of-proof — choosing wrong silently changes legal meaning.
- No string operations exist in the Blawx target at all; numbers go through CLP constraints (integers/rationals — mind division).

**No Blawx counterpart:** L4's regulative layer (`DEONTIC`, `PARTY MUST/MAY/SHANT ... WITHIN ... HENCE/LEST`, `FULFILLED/BREACH`, `#TRACE`, the state ledger). The nearest Blawx machinery is the event layer (`blawx_becomes`/`blawx_as_of`/`blawx_during`), which handles fluents changing truth value over time but has no obligation lifecycle, residuation, or trace semantics — deontics would have to be manually encoded as predicates over datetimes, or left out of scope.

**Blawx gives back for free** (if the transpiler emits proper declarations + `#pred` strings): natural-language justification trees for every answer, the ontology-driven scenario/interview UI, hypothetical reasoning over unknown facts, and a REST API per encoded rule.

## Targeting Blawx: practical transpiler notes

1. **Emit the `.blawx` fixture YAML** (ruledoc + workspaces + tests) as the primary target — it round-trips through `/import/`, `loaddata`, and the UI export. The `rule_text` should be CLEAN markup mirroring the L4 §-structure so section eIds (hence workspace names) come out right.
2. **Both representations must agree.** The reasoner executes only `scasp_encoding`; the editor renders only `xml_content`. s(CASP)-only output runs but shows empty canvases (and any UI save wipes it); XML-only output displays but doesn't run until someone re-saves each workspace. Generating correct s(CASP) is the semantic core; generating the matching Blockly XML (namespace `https://developers.google.com/blockly/xml`, including each block's `<mutation>` element — selectors carry their predicate names in mutations) is what keeps the result editable. The mortality example (`static/blawx/examples/mortality.yaml`) is the minimal reference pair.
3. Preserve the `% BLAWX CHECK DUPLICATES` marker line immediately before each `holds(...)` bridge and each conclusion bridge rule — dedup across workspaces depends on it.
4. Escape single quotes inside `#pred` NLG strings as `\'`; keep the `@(Var)` placeholders.
5. Rule identifiers used in `according_to`/`holds`/`blawx_defeated`/`blawx_applies` are the workspace/section names (`sec_1_section` etc.) as plain atoms — they must match the AKN eIds derived from `rule_text` or attribution and the UI's per-section display break.
