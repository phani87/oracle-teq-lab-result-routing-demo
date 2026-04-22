# teq-lab-result-routing

A React + Flask demo that uses Oracle Transactional Event Queues (TxEventQ) to route lab results for provider notification, patient release, and follow-up task creation.

## Stack
- React
- Flask
- python-oracledb
- Oracle Database / TxEventQ

## Workflow
1. User selects a lab order
2. User submits a result
3. API writes the result row and enqueues an event into TxEventQ
4. Worker dequeues and applies routing rules
5. UI shows routing progress

## Run
Frontend is served by Flask from the built `frontend/dist` folder.
