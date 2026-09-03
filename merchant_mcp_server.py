import json
import uuid
import time
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
import config
from razorpay_client import RazorpayClientWrapper
from mcp.server.fastmcp import FastMCP

# Fix Windows console UTF-8 output safely
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')


# Initialize Fast MCP Server
mcp = FastMCP(f"{config.MERCHANT_NAME} Storefront")

# Global Razorpay Client instance
razorpay_wrapper = RazorpayClientWrapper()

# Helper Functions for Data Persistence & Audit Logging

def _ensure_files():
    """Ensure data directory and state files exist."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not config.CATALOG_PATH.exists():
        raise FileNotFoundError(f"Catalog file missing at {config.CATALOG_PATH}")
    if not config.ORDERS_PATH.exists():
        with open(config.ORDERS_PATH, "w", encoding="utf-8") as f:
            json.dump({}, f, indent=2)

def _load_catalog() -> List[Dict[str, Any]]:
    _ensure_files()
    with open(config.CATALOG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def _save_catalog(catalog: List[Dict[str, Any]]):
    with open(config.CATALOG_PATH, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2)

def _load_orders() -> Dict[str, Any]:
    _ensure_files()
    try:
        with open(config.ORDERS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}

def _save_orders(orders: Dict[str, Any]):
    with open(config.ORDERS_PATH, "w", encoding="utf-8") as f:
        json.dump(orders, f, indent=2)

def log_audit_event(
    tool_name: str,
    buyer_agent_id: str,
    inputs: Dict[str, Any],
    status: str,
    outputs: Optional[Dict[str, Any]] = None,
    refusal_reason: Optional[str] = None,
    execution_time_ms: float = 0.0,
    guardrail_triggered: bool = False
):
    """
    Appends a structured event object to audit_log.jsonl.
    Satisfies buildathon requirement for bounded, explainable agent commerce.
    Includes real execution_time_ms (measured via time.perf_counter) and guardrail_triggered flag.
    """
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_id": f"evt_{uuid.uuid4().hex[:10]}",
        "tool_name": tool_name,
        "buyer_agent_id": buyer_agent_id,
        "inputs": inputs,
        "status": status,  # "SUCCESS", "REFUSED", "ERROR"
        "guardrail_triggered": guardrail_triggered,
        "outputs": outputs,
        "refusal_reason": refusal_reason,
        "execution_time_ms": round(execution_time_ms, 2)
    }
    with open(config.AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry) + "\n")
    return log_entry


# Core Tool Implementation Functions

def execute_search_products(
    query: str = "",
    max_price: Optional[float] = None,
    category: Optional[str] = None,
    buyer_agent_id: str = "unknown"
) -> List[Dict[str, Any]]:
    start_time = time.perf_counter()
    catalog = _load_catalog()
    results = []

    query_clean = query.strip().lower()
    for product in catalog:
        # Category filter
        if category and product.get("category", "").lower() != category.strip().lower():
            continue
        # Max price filter
        if max_price is not None and product.get("price", 0) > max_price:
            continue
        # Keyword search
        if query_clean:
            name = product.get("name", "").lower()
            desc = product.get("description", "").lower()
            tags = [t.lower() for t in product.get("tags", [])]
            if query_clean not in name and query_clean not in desc and not any(query_clean in t for t in tags):
                continue
        results.append(product)

    elapsed_ms = (time.perf_counter() - start_time) * 1000
    log_audit_event(
        tool_name="search_products",
        buyer_agent_id=buyer_agent_id,
        inputs={"query": query, "max_price": max_price, "category": category},
        status="SUCCESS",
        outputs={"matched_count": len(results), "product_ids": [p["id"] for p in results]},
        execution_time_ms=elapsed_ms,
        guardrail_triggered=False
    )
    return results


def execute_get_product(
    product_id: str,
    buyer_agent_id: str = "unknown"
) -> Dict[str, Any]:
    start_time = time.perf_counter()
    catalog = _load_catalog()
    
    for product in catalog:
        if product.get("id") == product_id:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            log_audit_event(
                tool_name="get_product",
                buyer_agent_id=buyer_agent_id,
                inputs={"product_id": product_id},
                status="SUCCESS",
                outputs=product,
                execution_time_ms=elapsed_ms,
                guardrail_triggered=False
            )
            return product

    elapsed_ms = (time.perf_counter() - start_time) * 1000
    refusal = f"REFUSAL: Product with ID '{product_id}' not found in catalog."
    log_audit_event(
        tool_name="get_product",
        buyer_agent_id=buyer_agent_id,
        inputs={"product_id": product_id},
        status="REFUSED",
        refusal_reason=refusal,
        execution_time_ms=elapsed_ms,
        guardrail_triggered=False
    )
    return {"error": refusal, "status": "failed"}


def execute_create_order(
    product_id: str,
    quantity: int,
    buyer_agent_id: str
) -> Dict[str, Any]:
    start_time = time.perf_counter()
    if quantity <= 0:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        refusal = "REFUSAL: Quantity must be a positive integer greater than 0."
        log_audit_event(
            tool_name="create_order",
            buyer_agent_id=buyer_agent_id,
            inputs={"product_id": product_id, "quantity": quantity},
            status="REFUSED",
            refusal_reason=refusal,
            execution_time_ms=elapsed_ms,
            guardrail_triggered=False
        )
        return {"error": refusal, "status": "refused"}

    catalog = _load_catalog()
    product = next((p for p in catalog if p.get("id") == product_id), None)

    if not product:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        refusal = f"REFUSAL: Product with ID '{product_id}' does not exist."
        log_audit_event(
            tool_name="create_order",
            buyer_agent_id=buyer_agent_id,
            inputs={"product_id": product_id, "quantity": quantity},
            status="REFUSED",
            refusal_reason=refusal,
            execution_time_ms=elapsed_ms,
            guardrail_triggered=False
        )
        return {"error": refusal, "status": "refused"}

    # GUARDRAIL 1: Stock Check
    current_stock = product.get("stock_qty", 0)
    if current_stock < quantity:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        refusal = f"REFUSAL: Insufficient stock for '{product.get('name')}'. Requested: {quantity}, Available stock: {current_stock}."
        log_audit_event(
            tool_name="create_order",
            buyer_agent_id=buyer_agent_id,
            inputs={"product_id": product_id, "quantity": quantity},
            status="REFUSED",
            refusal_reason=refusal,
            execution_time_ms=elapsed_ms,
            guardrail_triggered=True
        )
        return {
            "error": refusal,
            "status": "refused",
            "reason": "INSUFFICIENT_STOCK",
            "refusal_reason": refusal,
            "requested_qty": quantity,
            "available_stock": current_stock
        }

    # Reserve Stock and Save Order
    product["stock_qty"] -= quantity
    _save_catalog(catalog)

    unit_price = product.get("price", 0.0)
    total_amount = round(unit_price * quantity, 2)
    order_id = f"ord_{int(time.time())}_{uuid.uuid4().hex[:4]}"

    order_obj = {
        "order_id": order_id,
        "product_id": product_id,
        "product_name": product.get("name"),
        "quantity": quantity,
        "unit_price": unit_price,
        "total_amount": total_amount,
        "currency": config.MERCHANT_CURRENCY,
        "buyer_agent_id": buyer_agent_id,
        "status": "pending_payment",
        "razorpay_payment_link_id": None,
        "short_url": None,
        "refusal_reason": None,
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    orders = _load_orders()
    orders[order_id] = order_obj
    _save_orders(orders)

    elapsed_ms = (time.perf_counter() - start_time) * 1000
    log_audit_event(
        tool_name="create_order",
        buyer_agent_id=buyer_agent_id,
        inputs={"product_id": product_id, "quantity": quantity},
        status="SUCCESS",
        outputs=order_obj,
        execution_time_ms=elapsed_ms,
        guardrail_triggered=False
    )
    return order_obj


def execute_create_payment_link(
    order_id: str,
    buyer_agent_id: str = "unknown"
) -> Dict[str, Any]:
    start_time = time.perf_counter()
    orders = _load_orders()
    order = orders.get(order_id)

    if not order:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        refusal = f"REFUSAL: Order ID '{order_id}' not found."
        log_audit_event(
            tool_name="create_payment_link",
            buyer_agent_id=buyer_agent_id,
            inputs={"order_id": order_id},
            status="REFUSED",
            refusal_reason=refusal,
            execution_time_ms=elapsed_ms,
            guardrail_triggered=False
        )
        return {"error": refusal, "status": "refused"}

    total_amount = order.get("total_amount", 0.0)

    # GUARDRAIL 2: Merchant Maximum Order Value Check
    if total_amount > config.MERCHANT_MAX_ORDER_VALUE:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        refusal = (
            f"REFUSAL: Order total ₹{total_amount:.2f} exceeds merchant maximum automated checkout "
            f"threshold of ₹{config.MERCHANT_MAX_ORDER_VALUE:.2f}. High-value transactions require manual merchant approval."
        )
        order["status"] = "refused_exceeds_limit"
        order["refusal_reason"] = refusal
        orders[order_id] = order
        _save_orders(orders)

        log_audit_event(
            tool_name="create_payment_link",
            buyer_agent_id=buyer_agent_id,
            inputs={"order_id": order_id, "total_amount": total_amount},
            status="REFUSED",
            refusal_reason=refusal,
            execution_time_ms=elapsed_ms,
            guardrail_triggered=True
        )
        return {
            "error": refusal,
            "status": "refused",
            "reason": "MAX_ORDER_VALUE_EXCEEDED",
            "refusal_reason": refusal,
            "total_amount": total_amount,
            "merchant_limit": config.MERCHANT_MAX_ORDER_VALUE
        }

    # Call Razorpay Payment Link API
    try:
        rzp_response = razorpay_wrapper.create_payment_link(
            order_id=order_id,
            amount_inr=total_amount,
            product_name=order.get("product_name", "Coffee Product"),
            buyer_agent_id=buyer_agent_id
        )

        order["razorpay_payment_link_id"] = rzp_response.get("id")
        order["short_url"] = rzp_response.get("short_url")
        orders[order_id] = order
        _save_orders(orders)

        output_payload = {
            "order_id": order_id,
            "total_amount": total_amount,
            "currency": config.MERCHANT_CURRENCY,
            "payment_link": rzp_response.get("short_url"),
            "razorpay_payment_link_id": rzp_response.get("id"),
            "status": "pending_payment",
            "is_mock": rzp_response.get("is_mock", False)
        }

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        log_audit_event(
            tool_name="create_payment_link",
            buyer_agent_id=buyer_agent_id,
            inputs={"order_id": order_id},
            status="SUCCESS",
            outputs=output_payload,
            execution_time_ms=elapsed_ms,
            guardrail_triggered=False
        )
        return output_payload

    except Exception as e:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        err_msg = f"ERROR: Failed to generate payment link via Razorpay: {str(e)}"
        log_audit_event(
            tool_name="create_payment_link",
            buyer_agent_id=buyer_agent_id,
            inputs={"order_id": order_id},
            status="ERROR",
            refusal_reason=err_msg,
            execution_time_ms=elapsed_ms,
            guardrail_triggered=False
        )
        return {"error": err_msg, "status": "error"}


def execute_get_order_status(
    order_id: str,
    buyer_agent_id: str = "unknown"
) -> Dict[str, Any]:
    start_time = time.perf_counter()
    orders = _load_orders()
    order = orders.get(order_id)

    if not order:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        refusal = f"REFUSAL: Order ID '{order_id}' not found."
        log_audit_event(
            tool_name="get_order_status",
            buyer_agent_id=buyer_agent_id,
            inputs={"order_id": order_id},
            status="REFUSED",
            refusal_reason=refusal,
            execution_time_ms=elapsed_ms,
            guardrail_triggered=False
        )
        return {"error": refusal, "status": "refused"}

    rzp_link_id = order.get("razorpay_payment_link_id")
    if rzp_link_id:
        current_rzp_status = razorpay_wrapper.fetch_payment_link_status(rzp_link_id)
        if current_rzp_status in ["paid", "partially_paid"]:
            order["status"] = "paid"
        elif current_rzp_status == "expired":
            order["status"] = "expired"
        orders[order_id] = order
        _save_orders(orders)

    result_payload = {
        "order_id": order_id,
        "status": order.get("status"),
        "total_amount": order.get("total_amount"),
        "payment_link": order.get("short_url"),
        "paid": order.get("status") == "paid",
        "refusal_reason": order.get("refusal_reason")
    }

    elapsed_ms = (time.perf_counter() - start_time) * 1000
    log_audit_event(
        tool_name="get_order_status",
        buyer_agent_id=buyer_agent_id,
        inputs={"order_id": order_id},
        status="SUCCESS",
        outputs=result_payload,
        execution_time_ms=elapsed_ms,
        guardrail_triggered=False
    )
    return result_payload


# Register Tools with FastMCP Interface

@mcp.tool(
    name="search_products",
    description=(
        "Search the merchant's catalog by query keyword, maximum price limit, or category. "
        "Returns a list of matching products with live stock availability and pricing in INR."
    )
)
def search_products(
    query: str = "",
    max_price: Optional[float] = None,
    category: Optional[str] = None,
    buyer_agent_id: str = "unknown"
) -> List[Dict[str, Any]]:
    return execute_search_products(query, max_price, category, buyer_agent_id)


@mcp.tool(
    name="get_product",
    description=(
        "Get detailed information for a specific product by product_id, including live stock quantity."
    )
)
def get_product(
    product_id: str,
    buyer_agent_id: str = "unknown"
) -> Dict[str, Any]:
    return execute_get_product(product_id, buyer_agent_id)


@mcp.tool(
    name="create_order",
    description=(
        "Create a pending order for a specific product and quantity on behalf of a buyer agent. "
        "Enforces stock availability guardrails. Returns an order object with status 'pending_payment'."
    )
)
def create_order(
    product_id: str,
    quantity: int,
    buyer_agent_id: str
) -> Dict[str, Any]:
    return execute_create_order(product_id, quantity, buyer_agent_id)


@mcp.tool(
    name="create_payment_link",
    description=(
        "Generate a real Razorpay Test Mode Payment Link for an existing order. "
        "Enforces the MERCHANT_MAX_ORDER_VALUE guardrail limit (e.g. ₹5,000 INR max). "
        "Returns a checkout URL and Razorpay payment link ID."
    )
)
def create_payment_link(
    order_id: str,
    buyer_agent_id: str = "unknown"
) -> Dict[str, Any]:
    return execute_create_payment_link(order_id, buyer_agent_id)


@mcp.tool(
    name="get_order_status",
    description=(
        "Poll status of an order. Queries Razorpay API if payment link exists to verify "
        "whether the order has been paid, pending, failed, or expired."
    )
)
def get_order_status(
    order_id: str,
    buyer_agent_id: str = "unknown"
) -> Dict[str, Any]:
    return execute_get_order_status(order_id, buyer_agent_id)


if __name__ == "__main__":
    # Ensure catalog/orders exist on startup
    _ensure_files()
    print(f"🚀 Starting {config.MERCHANT_NAME} MCP Server...")
    print(f"🛡️ Guardrail Threshold: Max Order Value = ₹{config.MERCHANT_MAX_ORDER_VALUE}")
    print(f"📋 Audit Log Target: {config.AUDIT_LOG_PATH}")
    mcp.run()
