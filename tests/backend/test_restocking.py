"""
Tests for restocking API endpoints.
"""
import pytest


class TestRestockRecommendationsEndpoint:
    """Test suite for the GET /api/restocking/recommendations endpoint."""

    def test_get_recommendations_basic(self, client):
        """Test getting recommendations with a reasonable budget."""
        response = client.get("/api/restocking/recommendations?budget=5000")
        assert response.status_code == 200

        data = response.json()
        assert "recommendations" in data
        assert "budget" in data
        assert "total_cost" in data
        assert "remaining_budget" in data
        assert "items_covered" in data
        assert "total_eligible_items" in data
        assert "lead_time_days" in data

        assert isinstance(data["recommendations"], list)
        assert data["lead_time_days"] == 14
        assert data["items_covered"] == len(data["recommendations"])
        assert data["total_cost"] <= data["budget"]

    def test_recommendation_item_structure(self, client):
        """Test that each recommended item has the expected fields."""
        response = client.get("/api/restocking/recommendations?budget=5000")
        data = response.json()
        assert len(data["recommendations"]) > 0

        required_fields = [
            "sku", "item_name", "category", "warehouse", "unit_cost",
            "current_demand", "forecasted_demand", "trend",
            "recommended_quantity", "line_total"
        ]
        for item in data["recommendations"]:
            for field in required_fields:
                assert field in item, f"Missing field: {field}"
            assert item["recommended_quantity"] > 0
            assert item["line_total"] == round(item["recommended_quantity"] * item["unit_cost"], 2)

    def test_recommendations_sorted_by_cost_ascending(self, client):
        """Test that recommendations are ordered cheapest-to-cover first."""
        response = client.get("/api/restocking/recommendations?budget=5000")
        data = response.json()

        totals = [item["line_total"] for item in data["recommendations"]]
        assert totals == sorted(totals)

    def test_recommendations_respect_budget(self, client):
        """Test that total cost never exceeds the given budget across several budgets."""
        for budget in [50, 200, 1000, 3000, 8000]:
            response = client.get(f"/api/restocking/recommendations?budget={budget}")
            assert response.status_code == 200

            data = response.json()
            assert data["total_cost"] <= budget
            assert data["remaining_budget"] == round(budget - data["total_cost"], 2)

    def test_zero_budget_returns_no_recommendations(self, client):
        """Test that a zero budget produces no recommendations."""
        response = client.get("/api/restocking/recommendations?budget=0")
        assert response.status_code == 200

        data = response.json()
        assert data["recommendations"] == []
        assert data["items_covered"] == 0
        assert data["total_cost"] == 0

    def test_negative_budget_returns_400(self, client):
        """Test that a negative budget is rejected."""
        response = client.get("/api/restocking/recommendations?budget=-100")
        assert response.status_code == 400

        data = response.json()
        assert "detail" in data

    def test_recommendations_filtered_by_warehouse(self, client):
        """Test that a warehouse filter narrows recommendations to that warehouse."""
        response = client.get("/api/restocking/recommendations?budget=10000&warehouse=Tokyo")
        assert response.status_code == 200

        data = response.json()
        for item in data["recommendations"]:
            assert item["warehouse"] == "Tokyo"

    def test_recommendations_filtered_by_category(self, client):
        """Test that a category filter narrows recommendations to that category."""
        response = client.get("/api/restocking/recommendations?budget=10000&category=Actuators")
        assert response.status_code == 200

        data = response.json()
        for item in data["recommendations"]:
            assert item["category"].lower() == "actuators"

    def test_recommendations_exclude_items_with_no_restock_need(self, client):
        """Test that items whose forecasted demand is not above current demand
        (e.g. a decreasing trend) never appear, regardless of budget."""
        response = client.get("/api/restocking/recommendations?budget=1000000")
        data = response.json()

        skus = [item["sku"] for item in data["recommendations"]]
        assert "MTR-304" not in skus

    def test_items_covered_matches_recommendations_length(self, client):
        """Test that items_covered is consistent with the recommendations list."""
        response = client.get("/api/restocking/recommendations?budget=2500")
        data = response.json()
        assert data["items_covered"] == len(data["recommendations"])
        assert data["total_eligible_items"] >= data["items_covered"]


class TestRestockOrderCreation:
    """Test suite for the POST /api/orders/restock endpoint."""

    def test_create_restock_order_success(self, client):
        """Test successfully placing a restock order."""
        response = client.post("/api/orders/restock", json={"budget": 5000})
        assert response.status_code == 200

        order = response.json()
        assert order["source"] == "restocking"
        assert order["status"] == "Processing"
        assert order["lead_time_days"] == 14
        assert order["order_number"].startswith("RST-")
        assert len(order["items"]) > 0
        assert order["total_value"] > 0

    def test_create_restock_order_appears_in_orders_list(self, client):
        """Test that a newly created restock order shows up via GET /api/orders."""
        before = client.get("/api/orders").json()
        before_count = len(before)

        create_response = client.post("/api/orders/restock", json={"budget": 3000})
        assert create_response.status_code == 200
        new_order_id = create_response.json()["id"]

        after = client.get("/api/orders").json()
        assert len(after) == before_count + 1
        assert any(o["id"] == new_order_id for o in after)

    def test_create_restock_order_zero_budget_returns_400(self, client):
        """Test that a zero budget (no items fit) is rejected."""
        response = client.post("/api/orders/restock", json={"budget": 0})
        assert response.status_code == 400

        data = response.json()
        assert "detail" in data

    def test_create_restock_order_negative_budget_returns_400(self, client):
        """Test that a negative budget is rejected."""
        response = client.post("/api/orders/restock", json={"budget": -50})
        assert response.status_code == 400

    def test_create_restock_order_respects_filters(self, client):
        """Test that a restock order created with a category filter only
        contains items from that category."""
        response = client.post(
            "/api/orders/restock",
            json={"budget": 10000, "category": "Actuators"}
        )
        assert response.status_code == 200

        order = response.json()
        assert order["category"] == "Actuators"

        # Cross-check each item's category against inventory
        inventory = client.get("/api/inventory").json()
        inv_by_sku = {item["sku"]: item for item in inventory}
        for item in order["items"]:
            assert inv_by_sku[item["sku"]]["category"] == "Actuators"

    def test_expected_delivery_is_lead_time_days_after_order_date(self, client):
        """Test that expected_delivery is exactly 14 days after order_date."""
        from datetime import datetime

        response = client.post("/api/orders/restock", json={"budget": 4000})
        order = response.json()

        order_date = datetime.fromisoformat(order["order_date"])
        expected_delivery = datetime.fromisoformat(order["expected_delivery"])
        assert (expected_delivery - order_date).days == 14

    def test_total_value_matches_items_sum(self, client):
        """Test that total_value matches the sum of the order's line items."""
        response = client.post("/api/orders/restock", json={"budget": 6000})
        order = response.json()

        calculated_total = sum(
            item["quantity"] * item["unit_price"] for item in order["items"]
        )
        assert abs(order["total_value"] - calculated_total) < 0.01
