# Merchant Agent & Autonomous Buyer Agent — Agentic Commerce
### Built for Razorpay AI Buildathon (Agentic Commerce Track)

**Merchant Agent** exposes a merchant storefront ("Bangalore Coffee Roasters") via a machine-callable **Model Context Protocol (MCP)** interface. Paired with an **Autonomous Buyer Agent**, this project demonstrates true **Agent-to-Agent (A2A) Commerce**: an AI buyer agent receives a natural-language goal and budget, reasons over the merchant's catalog, places orders, generates real Razorpay Payment Links, and polls for payment status — with zero human intervention.

Every action taken by both agents is **bounded** by strict merchant & buyer guardrails and **explainable** via dual-sided audit logs.

---

## Architecture & Agent-to-Agent (A2A) Flow

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

## Machine-Callable MCP Tools Interface

| Tool Name | Input Parameters | Description |
|-----------|------------------|-------------|
| `search_products` | `query: str`, `max_price?: float`, `category?: str` | Search catalog matching keywords, price, or category. Returns matching products with live stock. |
| `get_product` | `product_id: str` | Retrieve complete details and live stock quantity for a single product. |
| `create_order` | `product_id: str`, `quantity: int`, `buyer_agent_id: str` | Reserves stock and creates order with status `pending_payment`. Refuses if stock is insufficient. |
| `create_payment_link` | `order_id: str`, `buyer_agent_id: str` | Triggers Razorpay Payment Links API in Test Mode. Returns short URL for payment. Refuses if total > `MERCHANT_MAX_ORDER_VALUE`. |
| `get_order_status` | `order_id: str`, `buyer_agent_id: str` | Polls Razorpay API to update and return order payment status (`pending_payment`, `paid`, `expired`). Refused orders return `refusal_reason`. |

---

## Dual-Sided Guardrails (Buyer & Merchant Safety)

1. **Merchant Stock Availability Guardrail (`create_order`)**
   - Refuses order creation if `requested_quantity > stock_qty`.
   - Returns structured refusal reason `INSUFFICIENT_STOCK` and logs refusal event in `audit_log.jsonl`.

2. **Merchant Maximum Order Value Limit (`create_payment_link`)**
   - Configurable threshold: `MERCHANT_MAX_ORDER_VALUE` (default: **₹5,000 INR**).
   - Refuses automated Razorpay payment link generation for high-value orders (e.g. commercial espresso machines at ₹45,000). High-value transactions return status `refused_exceeds_limit` and require human authorization. Verified in **Scenario 4**.

3. **Buyer Hard Budget Cap Guardrail (`buyer_agent.py`)**
   - Code-enforced hard check: `item_total <= budget_cap` (evaluated for both single-item price and quantity multiplier totals).
   - Buyer agent refuses to call `create_order` if candidate product total exceeds the budget cap.
   - Refusals are logged with human-readable reason string and `"guardrail_triggered": true` in `buyer_audit_log.jsonl`. Verified in **Scenario 2** and **Scenario 3**.

---

## Agent-to-Agent Demo Scenarios (`buyer_agent_demo.py`)

Running `python buyer_agent_demo.py` executes 5 comprehensive demo scenarios showcasing autonomous agent commerce and safety:

- **Scenario 1: Successful Autonomous Purchase & Real-Time Status Polling**
  - Buyer agent parses goal ("coffee beans and brewing method under ₹2000"), checks budget, places order, generates live Razorpay Payment Link, and polls `get_order_status` every 5 seconds (up to 12 attempts / 1 minute).
  - Demonstrates real-time transition from `pending_payment` to `paid` when payment is completed in browser.
- **Scenario 2: Buyer Guardrail Refusal (Single Item Price Exceeds Budget)**
  - Goal requests ₹2,499 burr grinder with ₹1,000 budget cap. Buyer agent refuses execution before creating order.
- **Scenario 3: Buyer Guardrail Refusal (Quantity Multiplier Exceeds Budget)**
  - Goal requests 3x coffee beans (₹1,650 total) with ₹1,200 budget cap. Buyer agent evaluates multiplier cost and refuses tool execution.
- **Scenario 4: Merchant Guardrail Refusal (Max Order Value Threshold Exceeded)**
  - Buyer agent (budget cap ₹50,000) places order for ₹45,000 Commercial Espresso Machine. Buyer permits, but Merchant MCP `create_payment_link` refuses execution due to ₹5,000 max order value limit.
- **Scenario 5: Side-by-Side Explainable Audit Logs**
  - Displays summary metrics and latest refusal entries from both `buyer_audit_log.jsonl` (buyer reasoning) and `audit_log.jsonl` (merchant execution).

---

## Side-by-Side Explainable Audit Logs

### Buyer Agent Reasoning Log (`buyer_audit_log.jsonl`)
```json
{
  "timestamp": "2026-09-04T09:54:45.670620+00:00",
  "event_id": "bagt_486ba33483",
  "buyer_agent_id": "agent_buyer_gamma",
  "goal": "Buy me 3 packs of Monsooned Malabar AA Coffee Beans",
  "budget_cap": 1200.0,
  "step": "evaluate_candidates",
  "reasoning": "Evaluated candidate 'Monsooned Malabar AA Coffee Beans (250g)' at ₹550.00 each for quantity 3. Total calculated cost ₹1650.00 exceeds buyer hard budget cap of ₹1200.00. Refusing to execute create_order tool call.",
  "decision": "refuse_order_budget_guardrail",
  "tool_calls": [],
  "status": "REFUSED",
  "guardrail_triggered": true,
  "refusal_reason": "REFUSAL: No valid purchase possible within budget cap of ₹1200.00; match 'Monsooned Malabar AA Coffee Beans (250g)' total cost is ₹1650.00 (3x ₹550.00)."
}
```

### Merchant Execution Log (`audit_log.jsonl`)
```json
{
  "timestamp": "2026-09-04T09:54:45.734665+00:00",
  "event_id": "evt_e3b83166cf",
  "tool_name": "create_payment_link",
  "buyer_agent_id": "agent_buyer_delta",
  "inputs": {"order_id": "ord_1788515685_7a7c", "total_amount": 45000.0},
  "status": "REFUSED",
  "guardrail_triggered": true,
  "outputs": null,
  "refusal_reason": "REFUSAL: Order total ₹45000.00 exceeds merchant maximum automated checkout threshold of ₹5000.00. High-value transactions require manual merchant approval.",
  "execution_time_ms": 22.9
}
```

---

## Running Instructions

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
Executes autonomous buyer reasoning, budget evaluation, order placement, Razorpay payment link creation, status polling loop, merchant guardrail validation, and prints dual audit logs:

```bash
python -u buyer_agent_demo.py
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

## Repository Deliverables Manifest

- `data/catalog.json` - Product catalog (10 items for Bangalore Coffee Roasters)
- `data/orders.json` - Local order persistence store
- `merchant_mcp_server.py` - FastMCP server implementing 5 tools, guardrails & execution audit logging
- `razorpay_client.py` - Razorpay Payment Links API integration wrapper
- `buyer_agent.py` - Autonomous buyer agent with cognitive reasoning loop & buyer budget guardrails
- `buyer_agent_demo.py` - Agent-to-Agent end-to-end demo harness (Scenarios 1-5) & side-by-side audit logger
- `test_buyer_flow.py` - Scripted buyer test harness
- `config.py` - Environment configuration and merchant limits
- `audit_log.jsonl` - Append-only merchant audit log
- `buyer_audit_log.jsonl` - Append-only buyer reasoning audit log
- `.env.example` - Template for environment credentials
- `.gitignore` - Git ignore rules keeping secrets out of repository
- `README.md` - Technical documentation and architecture guide
