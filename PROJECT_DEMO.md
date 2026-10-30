# Project demonstration — 28 October 2026

Start **START_PROJECT.cmd**, keep the console open and visit http://127.0.0.1:8008.

1. On Describe, click **Load custom-location demo**. This loads Vijayawada, Guntur, Tenali, Mangalagiri, Amaravati and Machilipatnam with synthetic sample observations, without Areas A–G.
2. Click **Run AI analysis**. Show 10,500 residents and 3,900 entered affected residents. Water demand is 23,400 litres, available stock is 15,000 litres and coverage is 64.10%.
3. Show both places on the map. Click a ranking row and **Explain prediction**. Predicted damage and relative allocation priority are different measures.
4. Inspect the shortage alerts and the three allocation strategies. All strategies respect the same total stock; their distribution and minimum area coverage can differ.
5. On Response plan, approve one recommendation, mark it dispatched and confirm delivered. Reload and show its saved status. These are local operator records.
6. On What-if & audit, run the default -30% water shock. Water stock becomes 10,500 litres, coverage becomes 44.87%, and water shortage rises from 8,400 to 12,900 litres. The original plan stays saved.
7. Return to Describe and click **Add location**. In the dialog, enter a different place with name, latitude/longitude, population, density, separate minor/major/destroyed building counts and magnitude. Optionally enter affected population. Click **Add affected location**, then run analysis again. Select the previous scenario and click **Open saved scenario** to demonstrate restoration.

The refreshed UI groups location inputs, provides Undo for removal, and shows coverage rings and before/after bars. Response cards support search and dispatch-stage filters. Allocation policy, strategy comparison and model evaluation expand when selected.

## Donations and fund demonstration

Open **Donations & funds**. For a review demonstration, clearly label all sample entries as demonstration records. Set a target, record a received donation and a separate pending pledge, then add an expense linked to a saved scenario/affected area. Show that only received money is available to spend. Mark the pledge received, inspect the updated balance, filter the ledger and export CSV. Reload to show persistence. Use the correction action to void an incorrect entry with a reason; it remains in the history.

This is a manual local ledger. It does not take a payment, transfer funds or update warehouse stock.

## Implemented in this update

- Add, edit and remove custom places; remove or restore example areas.
- Validated coordinates, unique identities/names and coherent demographic counts.
- User observations pass through prediction, demand, priority, optimization, SHAP, simulation, exports and response cards.
- Map coordinate picker and automatic bounds for all result locations.
- Named saved scenarios and browser draft persistence.
- Strategy comparisons, per-location coverage and replenishment quantities.
- Sequential persisted dispatch confirmations and audit records.
- Synthetic-training-range warnings and visible priority components.
- A ready-to-load six-place demonstration.

## Kept outside this deadline

Live road routing, vehicle integration, shared warehouse stock reservation, integer package optimization, multi-incident concurrency and new real-world model training. The working project uses scenario-level stock and divisible allocation quantities. Basemap tiles require internet. No authentication was added.

## Verification

From emergency-resource-allocation, run `python -m pytest tests -q` (90 tests), `python scripts/verify_custom_locations.py` and `python scripts/verify_funds.py` while the app is running. Scenario name is optional; a blank name is generated from the disaster type. The packaged frontend is ready to run without Node.js. Rebuild only after frontend source changes.
