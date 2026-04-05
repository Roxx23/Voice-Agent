# Voice Agent for Abandoned Cart Recovery — Brainstorm

## Project Overview

Build an AI-powered voice agent that automatically calls customers who have abandoned their shopping cart on a Shopify e-commerce store. The agent engages in natural conversation to recover the sale — identifying objections, offering incentives, and guiding the customer back to checkout.

---

## Core Architecture

The system is composed of four layers:

1. **Triggering** — Detecting abandoned carts via Shopify
2. **Orchestration** — AI agent logic managing conversation flow
3. **Voice/Telephony** — Placing and handling real phone calls
4. **Integration** — Connecting back to Shopify for cart data, discounts, and order status

---

## Technology Stack

### 1. Shopify Integration (Free)

- **Shopify Webhooks** — Listen for `checkouts/create` and `checkouts/update` events to detect abandonment (e.g., no order placed within 30–60 minutes).
- **Shopify Admin API** (REST or GraphQL) — Pull cart details, product info, customer name, phone number, and order history.
- **Shopify Discount API** — Programmatically generate unique discount codes the agent can offer during the call.

### 2. Agent Orchestration — LangGraph + LangChain + FastAPI (Free / Open Source)

- **LangGraph** — Models the conversation as a stateful graph. Ideal because a recovery call is inherently multi-step: greeting → identifying the issue → offering a discount → handling objections → closing.
- **LangChain** — Tool integrations (Shopify lookup, discount generation, call transfer) and prompt management.
- **FastAPI** — Backend server that receives Shopify webhooks, schedules calls, manages sessions, and exposes health/monitoring endpoints.

### 3. Voice & Telephony (Paid — Usage Based)

#### Option A: DIY with Twilio (More Control)

- **Twilio Programmable Voice** — Make outbound PSTN calls.
- Audio streamed over WebSockets to your FastAPI server.
- Free trial with ~$15 in credits, then ~$0.013/min.

#### Option B: High-Level Voice AI Platforms (Less Control, Faster to Build)

| Platform    | Free Tier         | Notes                                      |
|-------------|-------------------|--------------------------------------------|
| Vapi.ai     | Yes (limited)     | Full STT→LLM→TTS pipeline managed for you  |
| Bland.ai    | Trial credits     | Purpose-built for AI phone agents           |
| Retell.ai   | Trial credits     | Good real-time latency, easy integration    |

#### Option C: Cheaper Twilio Alternatives

- Vonage (Nexmo)
- Plivo

### 4. Speech Pipeline — STT + TTS (If Going DIY)

#### Speech-to-Text (STT)

| Provider        | Free Tier              | Latency  | Notes                        |
|-----------------|------------------------|----------|------------------------------|
| Deepgram        | $200 free credits      | ~300ms   | Best streaming STT           |
| Groq (Whisper)  | Free tier available    | ~200ms   | Extremely fast               |
| AssemblyAI      | Limited free tier      | ~400ms   | Good accuracy                |

#### Text-to-Speech (TTS)

| Provider        | Free Tier              | Quality  | Notes                        |
|-----------------|------------------------|----------|------------------------------|
| ElevenLabs      | ~10K chars/month       | High     | Most natural sounding        |
| Deepgram TTS    | Included in credits    | Good     | Low latency                  |
| Cartesia        | Free tier available    | High     | Fast streaming               |
| OpenAI TTS      | Pay-per-use            | High     | Simple API                   |

#### LLM (Brain of the Agent)

| Provider        | Free Tier              | Notes                        |
|-----------------|------------------------|------------------------------|
| Groq            | Free (Llama models)    | Extremely fast inference      |
| OpenAI          | Pay-per-use            | GPT-4o for best quality       |
| Together AI     | Free credits           | Open-source model hosting     |

---

## Conversation Flow (LangGraph State Machine)

```
START
  │
  ▼
[Greeting] ── "Hi {name}, this is {brand}. You left some items in your cart..."
  │
  ▼
[Identify Intent] ── Listen for customer response
  │
  ├── Interested → [Product Recap]
  ├── Objection  → [Handle Objection]
  ├── Not Interested → [Soft Close]
  └── Voicemail  → [Leave Message]
  │
  ▼
[Handle Objection]
  ├── Price too high    → [Offer Discount]
  ├── Found elsewhere   → [Price Match / Unique Value]
  ├── Just browsing     → [Highlight Benefits]
  └── Shipping concerns → [Explain Shipping Policy]
  │
  ▼
[Offer Discount] ── Generate unique code via Shopify API
  │
  ▼
[Close] ── "I've sent the discount to your phone/email. Can I help with anything else?"
  │
  ▼
[Send Follow-Up] ── SMS/email with cart link + discount code
  │
  ▼
END
```

---

## Cost Analysis

### Per-Call Estimate (DIY Stack)

| Component       | Cost per Minute  | 3-Min Call Cost |
|-----------------|------------------|-----------------|
| Telephony       | $0.013           | $0.04           |
| STT             | $0.01            | $0.03           |
| TTS             | $0.015           | $0.045          |
| LLM             | ~$0.005          | $0.015          |
| **Total**       | **~$0.043**      | **~$0.13**      |

### Monthly Projections

| Calls/Month | Est. Cost   |
|-------------|-------------|
| 100         | ~$13        |
| 500         | ~$65        |
| 1,000       | ~$130       |
| 5,000       | ~$650       |

### What's Free

- Shopify webhooks and API access
- LangGraph, LangChain, FastAPI (open source)
- Groq free tier (LLM + STT)
- ElevenLabs free tier (TTS, limited)
- Self-hosting on your own machine

### What's Never Free

- PSTN telephony minutes (placing real phone calls)
- High-volume STT/TTS usage beyond free tiers

### Lowest-Cost Starting Point

Twilio trial ($15 free) + Groq free tier + ElevenLabs free tier = **~100–200 test calls at zero cost**.

---

## Implementation Phases

### Phase 1 — Text-Based Agent (Week 1)

- [ ] Build LangGraph conversation flow
- [ ] Integrate Shopify Admin API for cart data
- [ ] Test as a text chatbot via FastAPI endpoints
- [ ] Add discount code generation logic

### Phase 2 — Voice Integration (Week 2)

- [ ] Set up Twilio account and outbound calling
- [ ] Implement WebSocket audio streaming with FastAPI
- [ ] Wire in STT (Deepgram or Groq Whisper)
- [ ] Wire in TTS (ElevenLabs or Cartesia)
- [ ] Handle real-time audio loop: caller → STT → LangGraph → TTS → caller

### Phase 3 — Automation & Triggers (Week 3)

- [ ] Shopify webhook listener for abandoned checkouts
- [ ] Call scheduling logic (delay 30–60 min after abandonment)
- [ ] Queue management (avoid calling during odd hours)
- [ ] Voicemail detection and message leaving

### Phase 4 — Production Hardening (Week 4)

- [ ] Retry logic and error handling
- [ ] Call logging and analytics dashboard
- [ ] A/B testing different scripts and discount levels
- [ ] Consent and compliance checks
- [ ] Do-not-call list management

---

## Compliance & Legal Considerations

> **This is critical — automated outbound calls are heavily regulated.**

- **India (TRAI/DND):** Must check DND registry before calling. Calls only between 9 AM–9 PM. Prior consent required.
- **US (TCPA):** Express written consent required for autodialed or prerecorded calls. Violations carry $500–$1,500 per call in penalties.
- **EU (GDPR):** Legitimate interest or explicit consent needed. Must provide opt-out mechanism.
- **General:** Always allow the customer to opt out during the call. Maintain a suppression list. Log consent records.

**Recommendation:** Consult a legal advisor before going live. Ensure Shopify checkout includes consent for follow-up calls.

---

## Key Risks & Mitigations

| Risk                          | Mitigation                                              |
|-------------------------------|--------------------------------------------------------|
| Latency feels unnatural       | Use streaming STT/TTS, keep LLM responses concise      |
| Agent hallucinates product info | Ground responses strictly in Shopify cart data          |
| Customer gets annoyed          | Limit to 1 call per abandoned cart, respect opt-outs   |
| Voicemail wastes money         | Detect voicemail early, leave short message, hang up   |
| Compliance violation           | Build DND checks into the pipeline, log everything     |

---

## Future Enhancements

- **Multilingual support** — Detect customer language, switch agent language dynamically
- **SMS fallback** — If call fails or goes to voicemail, send an SMS with cart link
- **Sentiment analysis** — Adjust tone and offers based on detected customer mood
- **Analytics dashboard** — Track recovery rate, call duration, discount usage, ROI
- **A/B testing** — Compare different opening lines, discount amounts, call timing
- **WhatsApp integration** — Voice notes or chat-based recovery for markets where WhatsApp dominates

---

## Quick Reference: Tech Stack Summary

| Layer            | Technology                          | Cost     |
|------------------|-------------------------------------|----------|
| Trigger          | Shopify Webhooks                    | Free     |
| Backend          | FastAPI                             | Free     |
| Agent Logic      | LangGraph + LangChain              | Free     |
| Telephony        | Twilio / Vapi / Bland              | Paid     |
| STT              | Deepgram / Groq Whisper            | Freemium |
| TTS              | ElevenLabs / Cartesia / Deepgram   | Freemium |
| LLM              | Groq (Llama) / OpenAI              | Freemium |
| Hosting          | Self-hosted / Railway / Fly.io     | Freemium |