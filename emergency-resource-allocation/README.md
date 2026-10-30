# ReliefPlan AI

AI-assisted emergency resource allocation, scenario comparison and local decision records.

## Run the complete project

From the Disaster folder, double-click START_PROJECT.cmd. The application and API run at http://127.0.0.1:8008 in one process. See [the project demo](../PROJECT_DEMO.md) for the demonstration and expected behavior.

Manual start: python run.py. For a different port: python run.py --port 8009.

## Installation

Python 3.13 is the verified interpreter. Install requirements-tested.txt to reproduce the tested direct dependency versions. A prebuilt frontend is included in the review package. To rebuild it, run npm ci and npm run build inside frontend.

## Verification

Run python -m pytest tests -q. The suite contains 90 tests covering allocation, custom locations, prediction explanations, dispatch stages, simulations, exports, validation and fund bookkeeping. Fund tests include exact money values, pending pledges, idempotent receipts, concurrent expense limits and traceable corrections. Frontend checks: npm run build and npm run lint. With the server running, use python scripts/verify_custom_locations.py for the allocation workflow and python scripts/verify_funds.py for fund-ledger consistency checks.

## Custom locations and submission demo

Use **Load custom-location demo** on Describe to load Vijayawada, Guntur, Tenali, Mangalagiri, Amaravati and Machilipatnam with explicitly synthetic observations. Run analysis, inspect the map, compare allocation strategies, review shortages and test a water reduction. To add another place, click **Add location** in **Custom affected locations**. The focused dialog groups name/coordinates, population/vulnerability and damage observations. Coordinates can also be picked on the map. An optional entered affected count overrides the model-derived estimate. Children and elderly counts must not exceed the resident population when combined. Removal offers an Undo action.

Remove the example areas to analyze only custom places. Custom coordinates and features are used throughout the pipeline, including SHAP, CSV export, simulation and response records. Scenario names and all observations persist in SQLite after analysis; unfinished scenario inputs persist in the browser. Reopen any of the latest 50 saved scenarios using the selector.

Response cards follow Planned → Approved → Dispatched → Delivered. These are sequential, persistent local confirmations. The application does not reserve shared warehouse stock or contact delivery vehicles. Compare optimized allocation with demand-proportional and equal-quantity distribution. Different distributions can have identical total shortage.

## Dashboard interface

The submission dashboard uses a light workspace with a dark navigation sidebar on desktop and compact navigation on narrow screens. Scenario summaries, resource coverage rings, map priority labels and simulation bars show the actual computed values. Search response cards by location/resource, or filter by dispatch stage. Expand allocation policy, strategy comparison and saved model evaluation when needed. A quick guide, keyboard focus indicators, native accessible location dialog, readable validation errors and loading states guide the workflow. The UI uses local system fonts and has no external font dependency.

## Donations & funds

Open **Donations & funds** in the navigation. It is available without running a new analysis. This shared INR ledger records donations received outside the app, outstanding pledges, expenses and a fundraising target. Received funds minus active expenses gives the available balance. Pledges remain unavailable until manually marked received. Expenses cannot exceed the available balance, even when concurrent requests arrive. Amounts are stored as integer paise.

Optionally link an entry to an existing saved scenario and an affected area from that plan. Choose an expense category to see where money is used. Search/filter the ledger and export its full history as CSV. Incorrect entries can be voided with a reason; the records remain visible, and a donation cannot be voided if that would leave expenses unfunded. Donation/expense changes also appear in the decision audit.

Records and targets persist in the same local SQLite database as plans. The ledger starts empty on a fresh installation; it is not seeded with fictitious receipts. This module records manual bookkeeping only. It does not collect online payments, initiate UPI/bank transfers, issue tax receipts, reserve inventory, or turn money into stock automatically.

## Current implementation

server.py defines the validated HTTP API; api.py keeps uvicorn api:app compatible. core/planning.py prepares one scenario for both analysis and simulation. core/optimizer.py reserves a feasible service fraction before priority allocation. core/store.py persists plans and decisions in SQLite. frontend/src/ReviewApp.jsx is the active React UI. app/Home.py runs the Streamlit alternative using the same backend services.

## Data and scope

The supplied study and training records are synthetic. Custom observations are entered by the user; the model is not independently validated for real-world emergency use. It uses six damage and event features. Disaster selection changes daily consumption assumptions, and planning severity scales estimated residents needing assistance unless an affected count is entered. Out-of-training-range custom features are flagged. Priority scores are relative within a scenario, so a single location has no comparative ranking signal. Model metrics are the saved evaluation record. OpenStreetMap tiles require internet; the numerical pipeline runs locally. Custom places have no surveyed road connections; no routing, road closure inference or ETA is claimed. Allocations remain divisible planning quantities, which can contain fractions.

The React dashboard is the full submission interface. The Streamlit alternative can restore and inspect custom plans through the shared backend; its sidebar remains a basic example-area editor.

The earlier src modules and app/_pages_archive are retained for reference. The React review application is launched by run.py.

Repository: https://github.com/palli-pavan/dia
