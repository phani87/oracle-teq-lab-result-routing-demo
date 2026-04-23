# Oracle TxEventQ Lab Result Routing Demo

This demo shows how to use Oracle Transactional Event Queues (TxEventQ) with a React frontend, a Flask API, a Python worker, and Oracle Database.

## What it does

1. Select a lab order in the UI
2. Submit a lab result
3. The API stores the result and enqueues a message into `LAB_RESULT_TEQ`
4. The worker dequeues the message and applies routing rules
5. The UI shows routing progress

## Project structure

```text
teq-lab/
├── backend/
│   ├── app.py
│   ├── db.py
│   ├── worker.py
│   ├── requirements.txt
│   └── .env
└── frontend/
    ├── index.html
    ├── package.json
    └── src/
        ├── api.js
        ├── App.jsx
        ├── main.jsx
        └── styles.css
```

## Prerequisites

- Oracle Database with the required tables already created
- TxEventQ queue `LAB_RESULT_TEQ`
- Oracle Instant Client installed on the host
- Python 3
- Node.js and npm

## Backend setup

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create `backend/.env`:

```env
DB_USER=YOUR_DB_USER
DB_PASSWORD=YOUR_DB_PASSWORD
DB_DSN=HOST:1521/SERVICE_NAME
ORACLE_CLIENT_LIB_DIR=/home/opc/oracle/instantclient_23_26
QUEUE_NAME=LAB_RESULT_TEQ
POLL_INTERVAL_SECONDS=2
```

Set the Oracle library path before starting:

```bash
export LD_LIBRARY_PATH=/home/opc/oracle/instantclient_23_26:$LD_LIBRARY_PATH
```

## Frontend build

```bash
cd frontend
npm install
npm run build
```

## Run the demo

Start Flask:

```bash
cd backend
source venv/bin/activate
export LD_LIBRARY_PATH=/home/opc/oracle/instantclient_23_26:$LD_LIBRARY_PATH
python app.py
```

Start the worker in a second terminal:

```bash
cd backend
source venv/bin/activate
export LD_LIBRARY_PATH=/home/opc/oracle/instantclient_23_26:$LD_LIBRARY_PATH
python worker.py
```

## Open the app

```text
http://<host>:5000
```


## Notes

- Make sure port `5000` is open in OCI security rules and host firewall
- Do not commit `.env`
- The frontend is served by Flask from `frontend/dist`

