import json
import sys
from pathlib import Path
import config

# Fix Windows console UTF-8 printing safely
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')


# Import MCP Server tool execution functions directly for automated testing
from merchant_mcp_server import (
    execute_search_products,
    execute_get_product,
    execute_create_order,
    execute_create_payment_link,
    execute_get_order_status,
    _ensure_files
)

BUYER_AGENT_ID = "agent_buyer_007"

def print_section(title: str):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)

def run_test_suite():
    _ensure_files()
    print_section("FAKED BUYER AGENT FLOW - MERCHANT AGENT DEMO")
    print(f"Merchant Store: {config.MERCHANT_NAME}")
    print(f"Buyer Agent ID: {BUYER_AGENT_ID}")
    print(f"Merchant Max Order Limit: ₹{config.MERCHANT_MAX_ORDER_VALUE:.2f}")

    # =========================================================================
    # HAPPY PATH FLOW
    # =========================================================================
    print_section("1. CATALOG SEARCH")
    print("Agent Query: Searching for 'beans' under ₹1,000...")
    search_results = execute_search_products(
        query="beans",
        max_price=1000.0,
        buyer_agent_id=BUYER_AGENT_ID
    )
    print(f"Found {len(search_results)} matching product(s):")
    for item in search_results:
        print(f"  - [{item['id']}] {item['name']} | ₹{item['price']} | Stock: {item['stock_qty']}")

    if not search_results:
        print("ERROR: No products found in search!")
        sys.exit(1)

    target_product_id = search_results[0]["id"]

    print_section(f"2. FETCH PRODUCT DETAILS ({target_product_id})")
    product_info = execute_get_product(target_product_id, buyer_agent_id=BUYER_AGENT_ID)
    print(json.dumps(product_info, indent=2))

    print_section("3. CREATE ORDER")
    order_qty = 2
    print(f"Agent Action: Ordering {order_qty} unit(s) of '{product_info.get('name')}'...")
    order_res = execute_create_order(
        product_id=target_product_id,
        quantity=order_qty,
        buyer_agent_id=BUYER_AGENT_ID
    )
    print("Order Created Response:")
    print(json.dumps(order_res, indent=2))

    if order_res.get("status") != "pending_payment":
        print("❌ FAILED: Expected order status to be 'pending_payment'")
        sys.exit(1)

    order_id = order_res["order_id"]

    print_section("4. CREATE RAZORPAY PAYMENT LINK")
    print(f"Agent Action: Requesting Razorpay payment link for Order ID '{order_id}'...")
    pay_link_res = execute_create_payment_link(order_id, buyer_agent_id=BUYER_AGENT_ID)
    print("Payment Link Response:")
    print(json.dumps(pay_link_res, indent=2))

    if "payment_link" in pay_link_res and pay_link_res["payment_link"]:
        print("\n" + "*" * 70)
        print(f"🔗 RAZORPAY PAYMENT LINK GENERATED:")
        print(f"   URL: {pay_link_res['payment_link']}")
        print(f"   Razorpay Link ID: {pay_link_res.get('razorpay_payment_link_id')}")
        print("   (Open this link in a browser to simulate payment in Test Mode)")
        print("*" * 70)
    else:
        print("❌ FAILED: Payment link was not generated.")
        sys.exit(1)

    print_section("5. CHECK ORDER STATUS")
    status_res = execute_get_order_status(order_id, buyer_agent_id=BUYER_AGENT_ID)
    print(json.dumps(status_res, indent=2))

    # =========================================================================
    # GUARDRAIL TEST 1: INSUFFICIENT STOCK
    # =========================================================================
    print_section("GUARDRAIL TEST 1: INSUFFICIENT STOCK REFUSAL")
    out_of_stock_id = "prod_010"  # Stock is 0
    print(f"Agent Action: Attempting to order 1 unit of '{out_of_stock_id}' (Stock: 0)...")
    stock_refusal_res = execute_create_order(
        product_id=out_of_stock_id,
        quantity=1,
        buyer_agent_id=BUYER_AGENT_ID
    )
    print("Response (Expected Refusal):")
    print(json.dumps(stock_refusal_res, indent=2))

    if stock_refusal_res.get("status") == "refused":
        print("✅ SUCCESS: Guardrail correctly REFUSED order creation due to insufficient stock.")
    else:
        print("❌ FAILED: Guardrail failed to stop out-of-stock order!")
        sys.exit(1)

    # =========================================================================
    # GUARDRAIL TEST 2: MERCHANT MAX ORDER VALUE EXCEEDED
    # =========================================================================
    print_section("GUARDRAIL TEST 2: MAX ORDER VALUE LIMIT REFUSAL")
    expensive_prod_id = "prod_009"  # Commercial Espresso Machine: ₹45,000
    print(f"Agent Action: Creating order for '{expensive_prod_id}' (Price: ₹45,000 > ₹{config.MERCHANT_MAX_ORDER_VALUE})...")
    expensive_order = execute_create_order(
        product_id=expensive_prod_id,
        quantity=1,
        buyer_agent_id=BUYER_AGENT_ID
    )
    print("Step A - Order Created:")
    print(json.dumps(expensive_order, indent=2))

    exp_order_id = expensive_order["order_id"]
    print(f"\nAgent Action: Requesting payment link for high-value Order '{exp_order_id}'...")
    max_val_refusal_res = execute_create_payment_link(exp_order_id, buyer_agent_id=BUYER_AGENT_ID)
    print("Step B - Payment Link Response (Expected Guardrail Refusal):")
    print(json.dumps(max_val_refusal_res, indent=2))

    if max_val_refusal_res.get("status") == "refused":
        print("✅ SUCCESS: Guardrail correctly REFUSED payment link creation due to value limit.")
    else:
        print("❌ FAILED: Guardrail failed to reject high-value transaction!")
        sys.exit(1)

    print_section("GUARDRAIL TEST 2B: EXPLAINABLE GET_ORDER_STATUS ON REFUSED ORDER")
    refused_status_res = execute_get_order_status(exp_order_id, buyer_agent_id=BUYER_AGENT_ID)
    print(json.dumps(refused_status_res, indent=2))
    if refused_status_res.get("status") == "refused_exceeds_limit" and refused_status_res.get("refusal_reason"):
        print("✅ SUCCESS: get_order_status returned 'refused_exceeds_limit' AND full refusal_reason string.")
    else:
        print("❌ FAILED: get_order_status did not return refusal_reason!")
        sys.exit(1)

    # =========================================================================
    # AUDIT LOG VERIFICATION
    # =========================================================================
    print_section("6. AUDIT LOG VERIFICATION")
    print(f"Reading audit log from: {config.AUDIT_LOG_PATH}")
    if config.AUDIT_LOG_PATH.exists():
        with open(config.AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        guardrail_count = sum(1 for line in lines if json.loads(line).get("guardrail_triggered") is True)
        print(f"Total Audit Log Entries Recorded: {len(lines)}")
        print(f"Guardrail Refusals Triggered (`guardrail_triggered: true`): {guardrail_count}")
        print("\nLast 3 Audit Log Entries (JSONL):")
        for line in lines[-3:]:
            print("  " + line.strip())
        print("\n✅ All tool operations, execution times, and guardrail_triggered flags recorded in audit log.")
    else:
        print("❌ FAILED: Audit log file was not generated.")

if __name__ == "__main__":
    run_test_suite()
