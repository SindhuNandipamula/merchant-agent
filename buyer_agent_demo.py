import json
import sys
import time
from pathlib import Path

import config
from buyer_agent import AutonomousBuyerAgent, BUYER_AUDIT_LOG_PATH
from merchant_mcp_server import _ensure_files, execute_get_order_status

# Fix Windows console UTF-8 printing safely
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def print_banner(title: str):
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)

def run_agent_demo():
    _ensure_files()
    print_banner("AGENT-TO-AGENT COMMERCE DEMO (RAZORPAY AI BUILDATHON)")
    print(f"Merchant Store: {config.MERCHANT_NAME}")
    print(f"Merchant Guardrail Max Order Limit: ₹{config.MERCHANT_MAX_ORDER_VALUE:.2f}")

    # =========================================================================
    # SCENARIO 1: SUCCESSFUL AUTONOMOUS PURCHASE
    # =========================================================================
    print_banner("=== SCENARIO 1: Successful Autonomous Purchase ===")
    user_goal1 = "Buy me coffee beans and a brewing method under ₹2000"
    user_budget1 = 2000.0

    buyer_agent1 = AutonomousBuyerAgent(
        buyer_agent_id="agent_buyer_alpha",
        budget_cap=user_budget1
    )

    result1 = buyer_agent1.run(goal=user_goal1)
    print("\n[BUYER AGENT RESULT]:")
    print(json.dumps(result1, indent=2))

    if result1.get("payment_links"):
        for pl in result1["payment_links"]:
            if pl.get("payment_link"):
                order_id = pl.get("order_id")
                print("\n" + "*" * 80)
                print(f"🔗 LIVE RAZORPAY PAYMENT LINK GENERATED FOR BUYER AGENT:")
                print(f"   Checkout URL: {pl['payment_link']}")
                print(f"   Razorpay Link ID: {pl.get('razorpay_payment_link_id')}")
                print("*" * 80)

                # Live demo polling loop: check order status every 3s (max 10 attempts)
                if order_id:
                    print(f"\n🔄 Polling Order Status for Order '{order_id}' every 3 seconds (max 10 attempts)...")
                    for attempt in range(1, 11):
                        status_res = execute_get_order_status(order_id, buyer_agent_id="agent_buyer_alpha")
                        current_status = status_res.get("status", "unknown")
                        print(f"   [Attempt {attempt:2d}/10] Order '{order_id}' Status: {current_status}")
                        if current_status == "paid":
                            print(f"\n🎉 PAYMENT CONFIRMED! Order '{order_id}' status transitioned from 'pending_payment' -> 'paid'.")
                            break
                        if attempt < 10:
                            time.sleep(3)

    # =========================================================================
    # SCENARIO 2: BUYER GUARDRAIL REFUSAL (SINGLE ITEM EXCEEDS BUDGET)
    # =========================================================================
    print_banner("=== SCENARIO 2: Buyer Guardrail Refusal (Single Item Exceeds Budget) ===")
    user_goal2 = "Buy me a handheld conical burr coffee grinder"
    user_budget2 = 1000.0  # Grinder is ₹2,499.00 > ₹1,000.00

    buyer_agent2 = AutonomousBuyerAgent(
        buyer_agent_id="agent_buyer_beta",
        budget_cap=user_budget2
    )

    print(f"Goal: '{user_goal2}' | Budget Cap: ₹{user_budget2:.2f}")
    result2 = buyer_agent2.run(goal=user_goal2)
    print("\n[BUYER GUARDRAIL REFUSAL RESULT]:")
    print(json.dumps(result2, indent=2))

    if result2.get("status") == "refused" and result2.get("guardrail_triggered") is True:
        print("\n✅ SUCCESS: Buyer guardrail correctly REFUSED tool execution on single item price check.")

    # =========================================================================
    # SCENARIO 3: BUYER GUARDRAIL REFUSAL (QUANTITY MULTIPLIER EXCEEDS BUDGET)
    # =========================================================================
    print_banner("=== SCENARIO 3: Buyer Guardrail Refusal (Quantity Multiplier Exceeds Budget) ===")
    user_goal3 = "Buy me 3 packs of Monsooned Malabar AA Coffee Beans"
    user_budget3 = 1200.0  # Beans are ₹550 each. 3x ₹550 = ₹1,650 > ₹1,200

    buyer_agent3 = AutonomousBuyerAgent(
        buyer_agent_id="agent_buyer_gamma",
        budget_cap=user_budget3
    )

    print(f"Goal: '{user_goal3}' | Budget Cap: ₹{user_budget3:.2f}")
    result3 = buyer_agent3.run(goal=user_goal3, target_quantity=3)
    print("\n[BUYER QUANTITY GUARDRAIL REFUSAL RESULT]:")
    print(json.dumps(result3, indent=2))

    if result3.get("status") == "refused" and result3.get("guardrail_triggered") is True:
        print("\n✅ SUCCESS: Buyer guardrail correctly REFUSED tool execution on quantity multiplier total check.")

    # =========================================================================
    # SCENARIO 4: SIDE-BY-SIDE EXPLAINABLE AUDIT LOGS
    # =========================================================================
    print_banner("=== SCENARIO 4: Side-by-Side Explainable Audit Logs ===")

    print(f"1. BUYER AGENT REASONING AUDIT LOG ({BUYER_AUDIT_LOG_PATH}):")
    if BUYER_AUDIT_LOG_PATH.exists():
        with open(BUYER_AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
            b_lines = f.readlines()
        
        b_refusals = sum(1 for l in b_lines if json.loads(l).get("guardrail_triggered") is True)
        print(f"   Total Buyer Reasoning Entries Recorded: {len(b_lines)}")
        print(f"   Buyer Guardrail Refusals (`guardrail_triggered: true`): {b_refusals}")
        print("\n   Latest Buyer Refusal Log Entry:")
        for line in reversed(b_lines):
            parsed = json.loads(line)
            if parsed.get("guardrail_triggered") is True:
                print("   " + line.strip())
                break
    else:
        print("   No buyer audit log found.")

    print(f"\n2. MERCHANT AGENT EXECUTION AUDIT LOG ({config.AUDIT_LOG_PATH}):")
    if config.AUDIT_LOG_PATH.exists():
        with open(config.AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
            m_lines = f.readlines()
        
        m_refusals = sum(1 for l in m_lines if json.loads(l).get("guardrail_triggered") is True)
        print(f"   Total Merchant Execution Entries Recorded: {len(m_lines)}")
        print(f"   Merchant Guardrail Refusals (`guardrail_triggered: true`): {m_refusals}")
        print("\n   Latest Merchant Refusal Log Entry:")
        for line in reversed(m_lines):
            parsed = json.loads(line)
            if parsed.get("guardrail_triggered") is True:
                print("   " + line.strip())
                break
    else:
        print("   No merchant audit log found.")

    print("\n🎉 AGENT-TO-AGENT COMMERCE DEMO COMPLETED SUCCESSFULLY!")

if __name__ == "__main__":
    run_agent_demo()
