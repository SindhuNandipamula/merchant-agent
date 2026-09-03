import os
import json
import time
import uuid
import sys
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional

import config
from merchant_mcp_server import (
    execute_search_products,
    execute_get_product,
    execute_create_order,
    execute_create_payment_link,
    execute_get_order_status
)

BUYER_AUDIT_LOG_PATH = config.BASE_DIR / "buyer_audit_log.jsonl"

def log_buyer_event(
    buyer_agent_id: str,
    goal: str,
    budget_cap: float,
    step: str,
    reasoning: str,
    decision: str,
    tool_calls: List[Dict[str, Any]],
    status: str = "SUCCESS",
    guardrail_triggered: bool = False,
    refusal_reason: Optional[str] = None,
    outputs: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Appends structured buyer agent reasoning and decision events to buyer_audit_log.jsonl.
    Schema matches merchant audit_log.jsonl for side-by-side consistency:
    includes timestamp, event_id, buyer_agent_id, goal, budget_cap, step, reasoning, decision,
    tool_calls, status, guardrail_triggered, outputs, refusal_reason.
    """
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_id": f"bagt_{uuid.uuid4().hex[:10]}",
        "buyer_agent_id": buyer_agent_id,
        "goal": goal,
        "budget_cap": budget_cap,
        "step": step,
        "reasoning": reasoning,
        "decision": decision,
        "tool_calls": tool_calls,
        "status": status,  # "SUCCESS", "REFUSED", "ERROR"
        "guardrail_triggered": guardrail_triggered,
        "outputs": outputs,
        "refusal_reason": refusal_reason
    }
    with open(BUYER_AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry) + "\n")
    return log_entry


class AutonomousBuyerAgent:
    """
    LLM / Cognitive Autonomous Buyer Agent.
    Interacts with the Merchant Agent MCP Server to fulfill user purchasing goals
    while enforcing strict code-level buyer budget guardrails and logging reasoning trails.
    """

    def __init__(self, buyer_agent_id: str = "agent_buyer_autonomous", budget_cap: float = 2000.0):
        self.buyer_agent_id = buyer_agent_id
        self.budget_cap = budget_cap

    def run(self, goal: str, target_quantity: int = 1) -> Dict[str, Any]:
        print(f"\n🤖 [BUYER AGENT] Starting Goal Execution: '{goal}'")
        print(f"💰 [BUYER AGENT] Hard Budget Cap: ₹{self.budget_cap:.2f}")

        # Check if quantity is specified in goal text (e.g. "Buy me 3 packs of...")
        # Requires explicit unit keywords so budget numbers like ₹2000 aren't misparsed
        qty_match = re.search(r'\b(\d+)\s+(?:pack|packs|unit|units|item|items|x)\b', goal, re.IGNORECASE)
        if qty_match and int(qty_match.group(1)) > 0:
            target_quantity = int(qty_match.group(1))

        # Step 1: Formulate Search Strategy & Query Merchant MCP Catalog
        reasoning_step1 = (
            f"Parsed purchasing goal: '{goal}' with requested quantity {target_quantity}. "
            f"Formulating catalog search under hard budget cap of ₹{self.budget_cap:.2f}."
        )
        print(f"💭 Reasoning: {reasoning_step1}")
        
        log_buyer_event(
            buyer_agent_id=self.buyer_agent_id,
            goal=goal,
            budget_cap=self.budget_cap,
            step="search_formulation",
            reasoning=reasoning_step1,
            decision="search_catalog",
            tool_calls=[{"tool": "search_products", "params": {"query": "", "max_price": None}}],
            status="SUCCESS",
            guardrail_triggered=False
        )

        # Search merchant catalog without capping max_price so buyer can inspect actual product prices
        all_candidates = execute_search_products(
            query="",
            max_price=None,
            buyer_agent_id=self.buyer_agent_id
        )

        # Filter candidates matching keywords from goal if specific item requested
        goal_lower = goal.lower()
        matched_candidates = []

        if "grinder" in goal_lower:
            matched_candidates = [p for p in all_candidates if "grinder" in p.get("name", "").lower() or "grinder" in p.get("category", "").lower()]
        elif "malabar" in goal_lower:
            matched_candidates = [p for p in all_candidates if "malabar" in p.get("name", "").lower()]
        elif "beans" in goal_lower:
            matched_candidates = [p for p in all_candidates if p.get("category") == "coffee_beans"]
        else:
            matched_candidates = [p for p in all_candidates if p.get("stock_qty", 0) > 0]

        if not matched_candidates:
            matched_candidates = [p for p in all_candidates if p.get("stock_qty", 0) > 0]

        # Step 2: Autonomous Reasoning & Candidate Evaluation
        for item in matched_candidates:
            unit_price = item.get("price", 0.0)
            total_cost = unit_price * target_quantity

            # =========================================================================
            # CODE-ENFORCED BUYER BUDGET GUARDRAIL CHECK
            # =========================================================================
            if total_cost > self.budget_cap:
                refusal_msg = (
                    f"REFUSAL: No valid purchase possible within budget cap of ₹{self.budget_cap:.2f}; "
                    f"match '{item.get('name')}' total cost is ₹{total_cost:.2f} ({target_quantity}x ₹{unit_price:.2f})."
                )
                reasoning_guardrail = (
                    f"Evaluated candidate '{item.get('name')}' at ₹{unit_price:.2f} each for quantity {target_quantity}. "
                    f"Total calculated cost ₹{total_cost:.2f} exceeds buyer hard budget cap of ₹{self.budget_cap:.2f}. "
                    f"Refusing to execute create_order tool call."
                )
                print(f"💭 Reasoning: {reasoning_guardrail}")
                print(f"🛡️ [BUYER GUARDRAIL TRIGGERED]: {refusal_msg}")

                log_buyer_event(
                    buyer_agent_id=self.buyer_agent_id,
                    goal=goal,
                    budget_cap=self.budget_cap,
                    step="evaluate_candidates",
                    reasoning=reasoning_guardrail,
                    decision="refuse_order_budget_guardrail",
                    tool_calls=[],
                    status="REFUSED",
                    guardrail_triggered=True,
                    refusal_reason=refusal_msg,
                    outputs={"attempted_product": item.get("name"), "unit_price": unit_price, "quantity": target_quantity, "total_cost": total_cost}
                )

                return {
                    "status": "refused",
                    "reason": refusal_msg,
                    "refusal_reason": refusal_msg,
                    "guardrail_triggered": True,
                    "attempted_product": item.get("name"),
                    "total_cost": total_cost,
                    "budget_cap": self.budget_cap
                }

        # Step 3: Basket Selection for Compound Goals (e.g. beans + brewing method)
        beans = [p for p in matched_candidates if p.get("category") == "coffee_beans" and p.get("stock_qty", 0) > 0]
        equipment = [p for p in matched_candidates if p.get("category") == "equipment" and p.get("stock_qty", 0) > 0]

        selected_items = []
        current_total = 0.0

        if beans:
            best_bean = min(beans, key=lambda x: x["price"])
            selected_items.append((best_bean, 1))
            current_total += best_bean["price"]

        if equipment:
            for eq in sorted(equipment, key=lambda x: x["price"]):
                if current_total + eq["price"] <= self.budget_cap:
                    selected_items.append((eq, 1))
                    current_total += eq["price"]
                    break

        if not selected_items and matched_candidates:
            cheapest = min(matched_candidates, key=lambda x: x["price"])
            if cheapest["price"] <= self.budget_cap:
                selected_items.append((cheapest, target_quantity))
                current_total = cheapest["price"] * target_quantity

        if not selected_items:
            reasoning_fail = f"REFUSAL: No products found within budget cap of ₹{self.budget_cap:.2f}."
            print(f"🛡️ [BUYER GUARDRAIL TRIGGERED]: {reasoning_fail}")
            log_buyer_event(
                buyer_agent_id=self.buyer_agent_id,
                goal=goal,
                budget_cap=self.budget_cap,
                step="evaluate_candidates",
                reasoning=reasoning_fail,
                decision="abort",
                tool_calls=[],
                status="REFUSED",
                guardrail_triggered=True,
                refusal_reason=reasoning_fail
            )
            return {"status": "refused", "reason": reasoning_fail, "guardrail_triggered": True}

        item_descriptions = ", ".join([f"{item['name']} (₹{item['price']})" for item, qty in selected_items])
        reasoning_step2 = (
            f"Evaluated available products against budget cap of ₹{self.budget_cap:.2f}. "
            f"Selected basket: {item_descriptions}. Total basket cost = ₹{current_total:.2f} <= ₹{self.budget_cap:.2f}."
        )
        print(f"💭 Reasoning: {reasoning_step2}")

        log_buyer_event(
            buyer_agent_id=self.buyer_agent_id,
            goal=goal,
            budget_cap=self.budget_cap,
            step="basket_selection",
            reasoning=reasoning_step2,
            decision=f"purchase_basket: {[i[0]['id'] for i in selected_items]}",
            tool_calls=[{"tool": "get_product", "params": {"product_id": item[0]["id"]}} for item in selected_items],
            status="SUCCESS",
            guardrail_triggered=False
        )

        # Step 4: Execute Orders via Merchant MCP
        completed_orders = []
        payment_links = []

        for item, qty in selected_items:
            item_total = item["price"] * qty

            # Final Code Guardrail Verification
            if item_total > self.budget_cap:
                refusal_msg = f"REFUSAL: Calculated item total ₹{item_total:.2f} exceeds buyer budget cap ₹{self.budget_cap:.2f}."
                log_buyer_event(
                    buyer_agent_id=self.buyer_agent_id,
                    goal=goal,
                    budget_cap=self.budget_cap,
                    step="order_guardrail_check",
                    reasoning=refusal_msg,
                    decision="refuse_order",
                    tool_calls=[],
                    status="REFUSED",
                    guardrail_triggered=True,
                    refusal_reason=refusal_msg
                )
                return {"status": "refused", "reason": refusal_msg, "guardrail_triggered": True}

            print(f"🛒 [BUYER AGENT] Placing order for '{item['name']}' (Qty: {qty})...")
            order_res = execute_create_order(
                product_id=item["id"],
                quantity=qty,
                buyer_agent_id=self.buyer_agent_id
            )

            if order_res.get("status") != "pending_payment":
                print(f"❌ Merchant refused order creation: {order_res.get('error')}")
                continue

            order_id = order_res["order_id"]
            completed_orders.append(order_res)

            print(f"💳 [BUYER AGENT] Requesting Razorpay Payment Link for Order '{order_id}'...")
            pay_res = execute_create_payment_link(order_id, buyer_agent_id=self.buyer_agent_id)
            payment_links.append(pay_res)

            print(f"🔄 [BUYER AGENT] Polling Order Status for Order '{order_id}'...")
            status_res = execute_get_order_status(order_id, buyer_agent_id=self.buyer_agent_id)
            print(f"📊 Order Status: {status_res.get('status')}")

        final_reasoning = (
            f"Successfully executed autonomous purchase flow for goal '{goal}'. "
            f"Generated {len(payment_links)} payment link(s). Total spent: ₹{current_total:.2f} <= ₹{self.budget_cap:.2f}."
        )
        log_buyer_event(
            buyer_agent_id=self.buyer_agent_id,
            goal=goal,
            budget_cap=self.budget_cap,
            step="completion",
            reasoning=final_reasoning,
            decision="completed_successfully",
            tool_calls=[{"tool": "get_order_status", "params": {"order_id": o.get("order_id")}} for o in completed_orders],
            status="SUCCESS",
            guardrail_triggered=False,
            outputs={"total_spent": current_total, "payment_links": [p.get("payment_link") for p in payment_links]}
        )

        return {
            "status": "success",
            "goal": goal,
            "budget_cap": self.budget_cap,
            "total_spent": current_total,
            "orders": completed_orders,
            "payment_links": payment_links
        }
