<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# Session addendum — 2026-06-12 — branch `pypi-packaging`

Branch `pypi-packaging` off `master` @ 0b98571. Two commits, full pytest green and
both wall tests green at each. **Nothing was uploaded to PyPI.** Not merged, not
pushed.

## Name determination (case 1: the name is free)

Command and output, verbatim:

```text
$ python -m pip index versions orp
ERROR: No matching distribution found for orp
```

No matching distribution exists, so per the determination rule the PyPI name is
**`orp`** — distribution name, import package, and console command all `orp`.

## Commits

| Commit | Content | Tests |
|---|---|---|
| a3decd4 | Publishable pyproject (dynamic version from `orp.__version__`, PEP 639 license expression, metadata, URLs incl. canonical `OpenSourcePatents/OpenReentry` casing also fixed on the site page), gates missing-data exit 3, wheel/venv proof. | 311 |
| (this) | README Install section atop Quickstart (pip line + gates source-checkout note); this addendum. site/index.html keeps its clone-based install instructions deliberately — the page flips to pip only after the upload is actually live, so the public page never claims an install path that does not work yet. | 311 |

## Packaging decisions of record

1. **License metadata:** `license = "GPL-3.0-or-later"` (SPDX expression) +
   `license-files = ["LICENSE"]`, build backend `setuptools>=77`. The OSI license
   classifier was requested but is intentionally absent: setuptools rejects license
   classifiers alongside an expression —
   `setuptools.errors.InvalidConfigError: License classifiers have been superseded
   by license expressions (see https://peps.python.org/pep-0639/)` — observed on the
   first build attempt. The current-spec declaration wins; PyPI renders the license
   from the expression.
2. **Version single-sourcing:** `[project] dynamic = ["version"]` +
   `[tool.setuptools.dynamic] version = { attr = "orp.__version__" }`; the static
   `version = "0.0.1"` line is gone, `orp/__init__.py` is the one source.
3. **Package data:** the five vehicle YAMLs verified inside BOTH artifacts
   (`orp/data/vehicles/*.yaml` in the wheel; `orp-0.0.1/orp/data/vehicles/*.yaml`
   in the sdist). The vehicle loader already resolves package-relative
   (`Path(__file__)...`), not repo-relative.
4. **Gates from an installed package:** repo-root `data/flights/` is deliberately
   not shipped (MACHINE-DIGITIZED flight datasets belong to the source tree).
   `orp gates` now detects the missing data, prints one honest line pointing at a
   source checkout, and exits **3** — distinct from 0 (all pinned) and 1 (unexpected
   deviation). Tested by monkeypatch and confirmed for real from the wheel venv.
5. `.gitignore` already contained `dist/`, `build/`, and `*.egg-info/` — no change.

## Wheel/venv smoke transcript

Build (`python -m build`, after the classifier fix):

```text
Successfully built orp-0.0.1.tar.gz and orp-0.0.1-py3-none-any.whl
```

Fresh venv (`python -m venv %TEMP%\orp_wheel_venv`), wheel installed with its
declared `[plot]` extra (orp run renders the five figures, which need matplotlib):

```text
matplotlib==3.11.0
numpy==2.4.6
orp==0.0.1
PyYAML==6.0.3
```

From `%TEMP%` (outside the repo), wheel alone:

```text
$ orp vehicles            -> exit 0, 45 lines, all five vehicles listed, e.g.:
apollo  (Apollo Command Module): 7 properties, 7 distinct source citation(s); weakest link: ASSERTED

$ orp run --vehicle apollo --planet earth --frame planet-relative --bank-deg 60 --out %TEMP%\orp_wheel_run
Run complete: 4378 samples, terminated by GROUND_HIT at t=437.700 s.
Peak deceleration: 11.2043 g
Peak heat rate: 870448 W/m^2
Final state: altitude -5.5 m, velocity 75.95 m/s, latitude -1.23649 deg, longitude 9.62559 deg, flight-path angle -79.2518 deg, heading 242.1849 deg
Run provenance (weakest link): NOT_VALIDATED
Outputs written to C:\Users\cjdow\AppData\Local\Temp\orp_wheel_run
-> exit 0; directory holds the five figures + trajectory.csv + session.yaml + provenance.txt
(numbers identical to the source-checkout run)

$ orp gates
orp gates: the flight-replay gates need a source checkout (data/flights/ is not shipped in the package); clone https://github.com/OpenSourcePatents/ORP and run from the repo root.
-> exit 3
```

## Ordering note (deliberate)

The README now carries the pip install line (it ships inside the package and reads
correctly the moment the upload happens); the public site keeps clone-based
instructions until the PyPI upload is actually live, and flips only then.
