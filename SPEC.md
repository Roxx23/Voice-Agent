# Project Spec: Voice Agent for Abandoned Cart Recovery

## Overview

An AI-powered voice agent that calls Shopify customers who abandoned their cart, engages them in conversation, handles objections, offers discounts, and guides them back to checkout. Calls are placed via **Vapi.ai**. Target market is **India**.

---

## System Architecture

```
┌────────────────────┐
│   Shopify Store     │
│  (Webhooks + API)   │
└────────┬───────────┘
         │ checkout abandoned
         ▼
┌────────────────────┐
│   FastAPI Backend   │
│  - Webhook listener │
│  - Call scheduler   │
│  - Session manager  │
│  - Discount engine  │
└────────┬───────────┘
         │ trigger call
         ▼
┌────────────────────┐
│      Vapi.ai        │
│  - Outbound call    │
│  - STT / TTS        │
│  - Voicemail detect │
└────────┬───────────┘
         │ conversation events
         ▼
┌────────────────────┐
│   LangGraph Agent   │
│  - Conversation FSM │
│  - Objection handler│
│  - Discount offers  │
│  - Cart context     │
└────────────────────┘
```

### Component Responsibilities

| Component       | Role                                                                 |
|-----------------|----------------------------------------------------------------------|
| **FastAPI**     | Receives Shopify webhooks, schedules calls, manages state, serves Vapi server URL |
| **Vapi.ai**    | Places outbound calls, handles audio pipeline (STT → TTS), voicemail detection |
| **LangGraph**  | Stateful conversation logic — greeting, objection handling, discount offers, closing |
| **Shopify API**| Source of cart data, customer info, discount code creation            |

### Key Design Decisions (v1)

- **Vapi manages the full voice pipeline** — no DIY STT/TTS wiring.
- **No interruption handling** — agent speaks full turn, then listens.
- **Voicemail detection** enabled via Vapi — leave short message and hang up.
- **Speed-optimized** — fast LLM (Groq/Llama), lean prompts, minimal round-trips.
- **India market** — call only logged-in customers with phone numbers on file. DND/TRAI compliance deferred to post-v1.

---

## Data Models

### AbandonedCart

```
{
  "cart_id": string,           // Shopify checkout ID
  "customer_name": string,
  "customer_phone": string,    // From Shopify customer record
  "customer_email": string,
  "items": [
    {
      "product_name": string,
      "variant": string,
      "quantity": int,
      "price": float,
      "image_url": string
    }
  ],
  "cart_total": float,
  "currency": "INR",
  "abandoned_at": datetime,
  "shopify_checkout_url": string
}
```

### CallSession

```
{
  "session_id": string,
  "cart_id": string,
  "customer_phone": string,
  "status": "scheduled" | "in_progress" | "completed" | "failed" | "voicemail",
  "scheduled_at": datetime,
  "started_at": datetime | null,
  "ended_at": datetime | null,
  "vapi_call_id": string | null,
  "outcome": "recovered" | "declined" | "no_answer" | "voicemail" | "error" | null,
  "discount_code": string | null,
  "discount_percent": int | null,
  "call_duration_seconds": int | null,
  "transcript": string | null
}
```

---

## Conversation Flow

```
START
  │
  ▼
[Greeting]
  "Hi {name}, this is {brand}. I noticed you left a few items in your cart — 
   {product_summary}. I wanted to check if there's anything I can help with."
  │
  ▼
[Listen for Intent]
  ├── Interested ──────────► [Product Recap] → [Close]
  ├── Objection ───────────► [Handle Objection]
  ├── Not Interested ──────► [Soft Close]
  └── Voicemail Detected ──► [Leave Message] → END
  │
  ▼
[Handle Objection]
  ├── Price too high ──────► [Offer Discount]
  ├── Found elsewhere ─────► [Highlight Unique Value]
  ├── Just browsing ───────► [Highlight Benefits]
  └── Shipping concerns ──► [Explain Shipping]
  │
  ▼
[Offer Discount]
  Generate unique code via Shopify Discount API
  "I can offer you {X}% off — code {CODE}. I'll send it to your phone right now."
  │
  ▼
[Close]
  Send SMS with cart link + discount code
  "Thanks {name}, I've sent the link to your phone. Have a great day!"
  │
  ▼
END
```

### Discount Strategy (v1)

| Attempt | Discount |
|---------|----------|
| First offer (on price objection) | 10% off |
| If customer hesitates | 15% off |
| Max (hard limit) | 15% off |

---

## Milestones

---

### Milestone 1: Shopify Integration

**Goal:** Connect to Shopify, fetch abandoned cart data, and generate discount codes.

| # | Task | Details |
|---|------|---------|
| 1.1 | Set up FastAPI project scaffold | Project structure, config, env vars, dependencies |
| 1.2 | Shopify webhook listener | Receive `checkouts/create` and `checkouts/update` events at a `/webhooks/shopify` endpoint. Verify HMAC signatures. |
| 1.3 | Abandoned cart detection | Logic to determine abandonment: checkout created but no corresponding order within 30 minutes. Store abandoned carts in a local database (SQLite for v1). |
| 1.4 | Cart data retrieval | Pull full cart details (items, prices, customer info) via Shopify Admin API. Extract customer phone from their Shopify profile. |
| 1.5 | Discount code generation | Generate unique single-use discount codes via Shopify Discount API (10% and 15% tiers). |
| 1.6 | Phone number validation | Filter out carts where the customer has no phone number on file. Basic Indian phone number format validation (+91 / 10-digit). |

**Deliverable:** A running FastAPI server that detects abandoned carts, stores them, fetches full cart details, and can generate discount codes. Testable via API calls and mock webhook payloads.

---

### Milestone 2: Conversation Agent (Text-Based)

**Goal:** Build the LangGraph conversation engine, testable entirely as text before any voice integration.

| # | Task | Details |
|---|------|---------|
| 2.1 | LangGraph state machine | Define the conversation graph: Greeting → Intent Detection → Objection Handling → Discount Offer → Close. Each node is a distinct state. |
| 2.2 | Prompt engineering | Write the system prompt grounding the agent in cart data. Agent must only reference actual products in the cart. It must never hallucinate product details. |
| 2.3 | Tool: Shopify cart lookup | LangGraph tool that fetches cart contents for the current call session. |
| 2.4 | Tool: Generate discount | LangGraph tool that creates a discount code and returns it to the agent. |
| 2.5 | Tool: Send SMS | LangGraph tool that sends the cart link + discount code to the customer via SMS (Twilio SMS or Vapi). |
| 2.6 | Voicemail message template | A short, fixed voicemail script: "Hi {name}, this is {brand}. You left some items in your cart. We've sent you a link with a special offer. Thanks!" |
| 2.7 | Text-based test endpoint | `POST /agent/chat` endpoint that accepts a message + session ID and returns the agent's response. For testing the full flow without voice. |
| 2.8 | Conversation guardrails | Agent must: stay on topic, not make up product info, not offer more than 15% discount, gracefully end if customer asks to stop. |

**Deliverable:** A fully functional text chatbot that simulates the entire recovery call. Testable via curl / Postman. Every conversation path exercised.

---

### Milestone 3: Vapi Voice Integration

**Goal:** Wire the conversation agent to Vapi so it can place real outbound phone calls.

| # | Task | Details |
|---|------|---------|
| 3.1 | Vapi account setup | Create Vapi account, configure API keys, set up a phone number for outbound calls (Indian number preferred). |
| 3.2 | Vapi assistant configuration | Create a Vapi assistant that uses our FastAPI server as the backend (Server URL mode). Configure voice settings: language (English + Hindi consideration), speed, voice persona. |
| 3.3 | Server URL endpoint | `POST /vapi/webhook` — the endpoint Vapi calls for conversation events. Handle `assistant-request`, `function-call`, `end-of-call-report`, `status-update`, and `speech-update` messages. |
| 3.4 | Outbound call trigger | `POST /calls/trigger` — given a cart ID, initiates an outbound call via Vapi API. Maps the cart to a call session. |
| 3.5 | Voicemail detection handling | Configure Vapi voicemail detection. When detected, deliver the voicemail script and end the call. Update call session status. |
| 3.6 | Call session lifecycle | Track call state transitions: scheduled → in_progress → completed/failed/voicemail. Store transcript from Vapi's end-of-call report. |
| 3.7 | End-to-end test call | Place a real test call to a personal number. Verify: greeting plays, agent responds to speech, discount code is generated and sent, call ends cleanly. |

**Deliverable:** The agent can place a real phone call, have a conversation, offer a discount, send an SMS, and log the outcome.

---

### Milestone 4: Automation & Scheduling

**Goal:** Fully automate the pipeline — abandoned cart detected → call scheduled → call placed — with no manual intervention.

| # | Task | Details |
|---|------|---------|
| 4.1 | Call scheduling queue | When an abandoned cart is detected, schedule a call 30 minutes later. Use an async task queue (e.g., Celery with Redis, or a simple in-process scheduler like APScheduler for v1). |
| 4.2 | Time window enforcement | Only place calls between 9 AM – 9 PM IST. If the scheduled time falls outside this window, defer to the next valid window. |
| 4.3 | Deduplication | Never call the same customer for the same cart twice. If customer completes checkout before the scheduled call, cancel it. |
| 4.4 | Concurrency limits | Limit concurrent outbound calls (start with max 5 simultaneous) to stay within Vapi rate limits and avoid cost spikes. |
| 4.5 | Recovery detection | Poll or listen for Shopify `orders/create` webhook. If an order matches a previously abandoned cart, mark it as recovered and cancel any pending call. |
| 4.6 | Retry logic | If a call fails (no answer, network error): retry once, 2 hours later. If voicemail: no retry, send SMS instead. Max 1 call + 1 retry per cart. |

**Deliverable:** Drop a test abandoned cart into Shopify → system automatically detects it, waits 30 min, places the call at a valid hour, and logs the result. No manual steps.

---

### Milestone 5: Production Hardening & Monitoring

**Goal:** Make the system reliable, observable, and safe for real customer calls.

| # | Task | Details |
|---|------|---------|
| 5.1 | Persistent database | Migrate from SQLite to PostgreSQL. Ensure call sessions and cart data survive restarts. |
| 5.2 | Logging & observability | Structured logging for every call event. Log: cart detected, call scheduled, call started, outcome, errors. |
| 5.3 | Error handling | Graceful handling of: Shopify API failures, Vapi API failures, LLM timeouts, invalid phone numbers. No silent failures. |
| 5.4 | Admin API / Dashboard | Simple endpoints to view: pending calls, completed calls, recovery rate, total discounts issued, call transcripts. |
| 5.5 | Environment configuration | Externalize all config: Shopify credentials, Vapi API key, discount tiers, call timing windows, retry limits. |
| 5.6 | Deployment | Dockerize the application. Deploy to a cloud VM or Railway/Fly.io. Set up a public URL for Shopify webhooks and Vapi server URL. |
| 5.7 | Webhook security | Verify Shopify HMAC on all incoming webhooks. Authenticate Vapi webhook calls. HTTPS everywhere. |

**Deliverable:** A deployed, monitored system that can handle real abandoned carts from a live Shopify store with full logging and error recovery.

---

## Out of Scope (v1)

These are explicitly **not** in the first version:

- Interruption handling (barge-in)
- Hindi language support (English only for v1)
- DND/TRAI registry checks
- A/B testing of scripts
- Sentiment analysis
- WhatsApp integration
- Multi-store support
- Customer opt-out preferences UI
- Analytics dashboard frontend (API-only in v1)

---

## Tech Stack (Final)

| Layer          | Choice              | Why                                      |
|----------------|---------------------|------------------------------------------|
| Backend        | FastAPI (Python)    | Async, fast, good ecosystem              |
| Agent Logic    | LangGraph + LangChain | Stateful conversation graphs           |
| Voice/Telephony| Vapi.ai             | Managed pipeline, fast to integrate      |
| LLM            | Groq (Llama 3)      | Fastest inference, free tier             |
| Database       | SQLite → PostgreSQL | Simple start, migrate at M5              |
| Task Queue     | APScheduler (v1)    | Lightweight, in-process scheduling       |
| SMS            | Vapi or Twilio      | For sending cart links + discount codes  |
| Deployment     | Docker + cloud VM   | Portable, easy to deploy                 |

---

## Success Metrics

| Metric                 | Target (v1)  |
|------------------------|-------------|
| Call completion rate    | > 60%       |
| Cart recovery rate     | > 5%        |
| Avg call duration      | < 3 min     |
| Agent response latency | < 2 sec     |
| Error rate             | < 5%        |
