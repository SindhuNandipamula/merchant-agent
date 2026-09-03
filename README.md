# Merchant Agent & Autonomous Buyer Agent — Agentic Commerce
### Built for Razorpay AI Buildathon (Agentic Commerce Track)

**Merchant Agent** exposes a merchant storefront ("Bangalore Coffee Roasters") via a machine-callable **Model Context Protocol (MCP)** interface. Paired with an **Autonomous Buyer Agent**, this project demonstrates true **Agent-to-Agent (A2A) Commerce**: an AI buyer agent receives a natural-language goal and budget, reasons over the merchant's catalog, places orders, generates real Razorpay Payment Links, and polls for payment status — with zero human intervention.

Every action taken by both agents is **bounded** by strict merchant & buyer guardrails and **explainable** via dual-sided audit logs.

---

## 🏗 Architecture & Agent-to-Agent (A2A) Flow

```
┌─────────────────────────────────┐                       ┌─────────────────────────────────────┐
│      AUTONOMOUS BUYER AGENT     │                       │     MERCHANT AGENT MCP SERVER       │
│  (Goal & Budget Cap Reasoning)  │                       │      (Bangalore Coffee Roasters)    │
│                                 │  1. search_products() │                                     │
│  - Parses natural language goal │ ────────────────────► │  - Catalog discovery & filtering    │
│  - Selects basket within budget │  2. get_product()     │  - Real-time stock reservation      │
│  - Enforces buyer budget check  │ ────────────────────► │  - Stock Availability Guardrail     │
│  - Logs reasoning to            │  3. create_order()    │  - Max Order Value Limit Guardrail  │
│    buyer_audit_log.jsonl        │ ────────────────────► │  - Logs execution to                │
│                                 │  4. create_pay_link() │    audit_log.jsonl                  │
│                                 │ ────────────────────► │                                     │
│                                 │  5. get_order_status()│                                     │
│                                 │ ────────────────────► │                                     │
└────────────────┬────────────────┘                       └──────────────────┬──────────────────┘
                 │                                                           │
                 ▼                                                           ▼
    ┌──────────────────────────┐                               ┌──────────────────────────┐
    │  buyer_audit_log.jsonl   │                               │     audit_log.jsonl      │
    │  (Buyer Reasoning Log)   │                               │ (Merchant Execution Log) │
    └──────────────────────────┘                               └─────────────┬────────────┘
                                                                             │
                                                                             ▼
                                                               ┌──────────────────────────┐
                                                               │ Razorpay Test Mode API   │
                                                               │  (Payment Links API)     │
                                                               └──────────────────────────┘
```

---

## 🛠️ Machine-Callable MCP Tools Interface

| Tool Name | Input Parameters | Description |
|-----------|------------------|-------------|
| `search_products` | `query: str`, `max_price?: float`, `category?: str` | Search catalog matching keywords, price, or category. Returns matching products with live stock. |
| `get_product` | `product_id: str` | Retrieve complete details and live stock quantity for a single product. |
| `create_order` | `product_id: str`, `quantity: int`, `buyer_agent_id: str` | Reserves stock and creates order with status `pending_payment`. Refuses if stock is insufficient. |
| `create_payment_link` | `order_id: str`, `buyer_agent_id: str` | Triggers Razorpay Payment Links API in Test Mode. Returns short URL for payment. Refuses if total > `MERCHANT_MAX_ORDER_VALUE`. |
| `get_order_status` | `order_id: str`, `buyer_agent_id: str` | Polls Razorpay API to update and return order payment status (`pending_payment`, `paid`, `expired`). Refused orders return `refusal_reason`. |

---

## 🛡️ Dual-Sided Guardrails (Buyer & Merchant Safety)

1. **Merchant Stock Availability Guardrail (`create_order`)**
   - Refuses order creation if `requested_quantity > stock_qty`.
   - Returns structured refusal reason `INSUFFICIENT_STOCK`.

2. **Merchant Maximum Order Value Limit (`create_payment_link`)**
   - Configurable threshold: `MERCHANT_MAX_ORDER_VALUE` (default: **₹5,000 INR**).
   - Refuses automated Razorpay payment link generation for high-value orders (e.g. commercial espresso machines at ₹45,000). High-value transactions return status `refused_exceeds_limit` and require human authorization.

3. **Buyer Hard Budget Cap Guardrail (`buyer_agent.py`)**
   - Code-enforced hard check: `item_total <= budget_cap` (evaluated for both single-item price and quantity multiplier totals).
   - Buyer agent refuses to call `create_order` if candidate product total exceeds the budget cap.
   - Refusals are logged with human-readable reason string and `"guardrail_triggered": true` in `buyer_audit_log.jsonl`. Verified in demo scenarios 2 and 3.

---

## 📋 Side-by-Side Explainable Audit Logs

### Buyer Agent Reasoning Log (`buyer_audit_log.jsonl`)
```json
{
  "timestamp": "2026-09-01T15:36:36.368102+00:00",
  "event_id": "bagt_a2b3c4d5",
  "buyer_agent_id": "agent_buyer_alpha",
  "goal": "Buy me coffee beans and a brewing method under ₹2000",
  "budget_cap": 2000.0,
  "step": "basket_selection",
  "reasoning": "Evaluated available products against budget cap of ₹2000.00. Selected basket: Wayanad Robusta Espresso Blend (250g) (₹420.0), Stainless Steel Pour-Over Dripper V60 (₹899.0). Total basket cost = ₹1319.00.",
  "decision": "purchase_basket: ['prod_003', 'prod_006']",
  "tool_calls": [{"tool": "get_product", "params": {"product_id": "prod_003"}}, {"tool": "get_product", "params": {"product_id": "prod_006"}}],
  "status": "SUCCESS"
}
```

### Merchant Execution Log (`audit_log.jsonl`)
```json
{
  "timestamp": "2026-09-01T15:36:36.415012+00:00",
  "event_id": "evt_9019a1b2",
  "tool_name": "create_payment_link",
  "buyer_agent_id": "agent_buyer_alpha",
  "inputs": {"order_id": "ord_1788276996_a37b"},
  "status": "SUCCESS",
  "guardrail_triggered": false,
  "outputs": {
    "order_id": "ord_1788276996_a37b",
    "total_amount": 420.0,
    "currency": "INR",
    "payment_link": "https://rzp.io/rzp/5FDLP2O",
    "razorpay_payment_link_id": "plink_TWpAZylAn2hHpx",
    "status": "pending_payment"
  },
  "refusal_reason": null,
  "execution_time_ms": 138.42
}
```

---

## 🚀 Running Instructions

### 1. Environment Setup
```bash
# Navigate to the project directory
cd merchant-agent

# Install required dependencies
pip install mcp razorpay python-dotenv pydantic

# Ensure Razorpay Test Keys are set in .env (see .env.example)
cp .env.example .env
```

### 2. Run Autonomous Agent-to-Agent Demo
Executes autonomous buyer reasoning, budget evaluation, order placement, Razorpay payment link creation, guardrail validation, and prints dual audit logs:

```bash
python buyer_agent_demo.py
```

### 3. Run Scripted Test Harness
```bash
python test_buyer_flow.py
```

### 4. Run Standalone MCP Server
To connect the Merchant Agent MCP server over stdio to Claude Desktop or Cursor/Antigravity:

```bash
python merchant_mcp_server.py
```

---

## 📁 Repository Deliverables Manifest

- `data/catalog.json` - Product catalog (10 items for Bangalore Coffee Roasters)
- `data/orders.json` - Local order persistence store
- `merchant_mcp_server.py` - FastMCP server implementing 5 tools, guardrails & execution audit logging
- `razorpay_client.py` - Razorpay Payment Links API integration wrapper
- `buyer_agent.py` - Autonomous buyer agent with cognitive reasoning loop & buyer budget guardrails
- `buyer_agent_demo.py` - Agent-to-Agent end-to-end demo harness & side-by-side audit logger
- `test_buyer_flow.py` - Scripted buyer test harness
- `config.py` - Environment configuration and merchant limits
- `audit_log.jsonl` - Append-only merchant audit log
- `buyer_audit_log.jsonl` - Append-only buyer reasoning audit log
- `.env.example` - Template for environment credentials
- `.gitignore` - Git ignore rules keeping secrets out of repository
- `README.md` - Technical documentation and architecture guide
