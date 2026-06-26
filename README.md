# Qwerty-ftw — FRA Decision Support System

A Flask-based **Decision Support System (DSS)** for the **Forest Rights Act (FRA)** in India, focused on the **Baran district of Rajasthan**. The platform helps manage land rights claims by forest-dwelling communities, analyzes them against geospatial data, and determines eligibility for government schemes.

## Stack

- **Backend:** Python 3, Flask, Flask-RESTful, Flask-SQLAlchemy, Flask-SocketIO, Flask-JWT-Extended
- **Database:** SQLite
- **External APIs:** Bhuvan (NRSC/ISRO) — LULC data & WMS groundwater layers; Groq — AI chatbot
- **Real-time:** WebSocket via Flask-SocketIO
- **Other:** UTM coordinate conversion, Gunicorn

## Project Structure

```
Qwerty-ftw/
├── main.py                          # Flask app — routes, models, auth, file handling, WebSocket
├── dss.py                           # Decision Support System — LULC, eligibility, groundwater
├── chatBot.py                       # Chatbot conversation state manager
├── test.py                          # Bulk upload test script
├── requirements.txt                 # Python dependencies
├── .gitignore
├── baran_location_hierarchy.csv     # Administration hierarchy: District → Tehsil → RI → Halka → Village
├── instance/
│   └── fra.db                       # SQLite DB with FRA claims data
└── uploads/                         # Uploaded documents and proof images
```

## Features

### 1. Role-Based Authentication

Three user roles, each registering/logging in at their own endpoint:

| Role        | Endpoint              |
|-------------|-----------------------|
| DLC         | `/register/dlc`       |
| SDLC        | `/register/sdlc`      |
| Gram Sabha  | `/register/gram_sabha`|

Login returns a JWT token with the role embedded in its claims.

### 2. FRA Claims Management

- **Add a claim** — `POST /claims`
- **List all claims** — `GET /claims/all`
- **Claims by district** — `GET /claims/district/<district_name>`
- **Upload document** — `POST /upload` (saves to `uploads/{claim_id}/`)
- **Upload proof image** — `POST /upload_proof` (saves to `uploads/{claim_id}/proofs/`)
- **Retrieve proofs** — `GET /get_proofs/<claim_id>`
- **Bulk upload** — `POST /bulkupload` (accepts a ZIP, extracts to `uploads/bulk_uploads/`)

### 3. Decision Support System (DSS)

#### Land Use / Land Cover (LULC)
- **District LULC** — `GET /lulc/<distcode>` — fetches land-use statistics from Bhuvan API for a district
- **AOI LULC** — `POST /lulc/aoi` — LULC stats for an arbitrary polygon (Area of Interest)

#### Scheme Eligibility
Evaluates each claim against 5 government schemes using LULC and claim metadata:

| Scheme               | Criteria                                                                 |
|----------------------|--------------------------------------------------------------------------|
| **PM-KISAN**         | Purpose is agriculture AND land area ≤ 2 hectares                        |
| **Jal Jeevan Mission** | Water body percentage < 50%                                           |
| **Van Dhan Yojana**  | Caste is ST AND forest cover > 20%                                      |
| **MGNREGA**          | Land area < 1 ha AND soil quality < 60%                                 |
| **DAJGUA**           | Purpose is agriculture/dairy AND soil quality > 70%                     |

Endpoints:
- **Single claim eligibility** — `GET /eligibility/<claim_id>`
- **District eligibility summary** — `GET /eligibility/summary/<district>`
- **AOI detailed summary** — `POST /aoi-dss-summary` (claimant list + eligibility + LULC for a polygon)
- **AOI scheme counts** — `POST /aoi-scheme-summary` (aggregated eligible counts per scheme)

#### Groundwater Properties
- **LGeom lookup** — `GET`/`POST /lgeom?x=<lat>&y=<lon>` — queries the Bhuvan WMS `RJ_LGEOM` layer and returns geological formation info with a groundwater potential rating (High / Moderate / Low).

### 4. AI Chatbot

A WebSocket-based chatbot accessible at the root of the app. Uses **Groq API** (`openai/gpt-oss-20b` model) with a system prompt that grounds it as an FRA DSS assistant. Maintains per-session conversation history on the server.

- Connect → receives `connected` event
- Send message → `message` event; receives `response` event with AI reply (async, threaded)

### 5. Static Data

`baran_location_hierarchy.csv` contains the full administrative hierarchy of Baran district: District → Tehsil → RI (Circle) → Halka → Village. This powers location-based filtering of claims.

## Setup & Running

1. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

2. **Set environment variables**

   Create a `.env` file in the project root:

   ```
   APIKEY=your_groq_api_key
   ```

3. **Run the app**

   ```bash
   python main.py
   ```

   Starts on `http://0.0.0.0:3000` with debug mode.

## API Overview

| Method | Endpoint                         | Description                          |
|--------|----------------------------------|--------------------------------------|
| POST   | `/register/<role>`               | Register (dlc/sdlc/gram_sabha)       |
| POST   | `/login/<role>`                  | Login, returns JWT                   |
| POST   | `/claims`                        | Add a new FRA claim                  |
| GET    | `/claims/all`                    | List all claims                      |
| GET    | `/claims/district/<district>`    | Claims filtered by district          |
| GET    | `/lulc/<distcode>`               | District LULC statistics             |
| POST   | `/lulc/aoi`                      | AOI LULC statistics                  |
| GET    | `/eligibility/<claim_id>`        | Scheme eligibility for a claim       |
| GET    | `/eligibility/summary/<district>`| District-level eligibility summary   |
| POST   | `/aoi-dss-summary`               | AOI claim details + eligibility      |
| POST   | `/aoi-scheme-summary`            | AOI scheme counts                    |
| GET    | `/lgeom`                         | Groundwater properties at coordinate |
| POST   | `/lgeom`                         | Groundwater properties at coordinate |
| POST   | `/upload`                        | Upload claim document                |
| POST   | `/upload_proof`                  | Upload proof image                   |
| GET    | `/get_proofs/<claim_id>`         | Get proof images for a claim         |
| POST   | `/bulkupload`                    | Bulk upload ZIP                      |

## Notes

- **Security:** API tokens and JWT secret are currently hardcoded. JWT secret should move to `.env` and passwords should be hashed for production.
- **Database:** `instance/fra.db` is included with sample data for Baran district. The app auto-creates tables on startup.
- **Languages:** Claim data uses Hindi (Devanagari) for village names, purposes, and caste statuses. The eligibility rules handle both Hindi and English values.
