<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# Source inventory — MSL commanded bank schedule (AAS 13-419)

**Citation.** Mendeck, G. F., and McGrew, L. C., "Post-Flight EDL Entry Guidance
Performance for the 2011 Mars Science Laboratory Mission," AAS 13-419, 23rd
AAS/AIAA Space-Flight Mechanics Meeting, Lihue, HI, Feb. 2013.
**NTRS accession:** `20130009519` (confirmed 2026-06-10). A near-duplicate deposit
`20130009144` carries the same title; `20130009519` is the citation used here.

**Role in ORP.** Primary source for the MSL *commanded bank-angle profile* — the
replayed control input for any future MSL guided-entry gate. (Forward-only wall: this
is an input history to replay, never a target to solve for.)

## FROM THE TEXT (directly sourceable)
- Entry guidance derives from the Apollo "final phase" logic; range is controlled by
  rotating the lift vector, i.e. the **bank angle**. *(text)*
- Curiosity landed **2.2 km** from the target (Gale Crater, 2012-08-05). *(text)*

## IN FIGURES / TABLES (needs digitization before use)
- The **commanded vs flown bank-angle time history** is figure-based — not yet
  digitized. `fig`
- Bank-reversal logic / range-error response: figure/algorithm description. `fig`

## Status
Citation + accession pinned; the bank-command numbers themselves remain `fig`-only.
A Mars guided-entry gate that replays this schedule is future work; until the figure
is digitized, any MSL bank input stays NOT_VALIDATED.
