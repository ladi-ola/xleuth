from fastapi.testclient import TestClient


def test_websocket_connect(client: TestClient):
    with client.websocket_connect("/ws/price/TOP20-JULY") as ws:
        ws.close()


def test_websocket_ping_pong(client: TestClient):
    with client.websocket_connect("/ws/price/TOP20-JULY") as ws:
        ws.send_json({"action": "ping"})
        pong = ws.receive_json()
        assert pong["type"] == "pong"
        ws.close()
    print("WebSocket: ping-pong works")


def test_websocket_subscribe(client: TestClient):
    with client.websocket_connect("/ws/price/TOP20-JULY") as ws:
        ws.send_json({"action": "subscribe", "basket_name": "TOP20-AUGUST"})
        sub = ws.receive_json()
        assert sub["type"] == "subscribed"
        assert sub["basket_name"] == "TOP20-AUGUST"
        ws.close()
    print("WebSocket: subscribe message works")


def test_websocket_invalid_message(client: TestClient):
    with client.websocket_connect("/ws/price/TOP20-JULY") as ws:
        ws.send_text("not json")
        err = ws.receive_json()
        assert err["type"] == "error"
        assert err["message"] == "Invalid message format"
        ws.close()
    print("WebSocket: invalid message handling works")


def test_orderbook_websocket_connect(client: TestClient):
    with client.websocket_connect("/ws/orderbook/TOP20-AUGUST") as ws:
        ws.close()


def test_orderbook_websocket_ping_pong(client: TestClient):
    with client.websocket_connect("/ws/orderbook/TOP20-AUGUST") as ws:
        ws.send_json({"action": "ping"})
        pong = ws.receive_json()
        assert pong["type"] == "pong"
        ws.close()
    print("WebSocket: order book ping-pong works")


def test_orderbook_websocket_subscribe(client: TestClient):
    with client.websocket_connect("/ws/orderbook/TOP20-AUGUST") as ws:
        ws.send_json({"action": "subscribe", "basket_name": "TOP20-AUGUST"})
        sub = ws.receive_json()
        assert sub["type"] == "subscribed"
        assert sub["basket_name"] == "TOP20-AUGUST"
        ws.close()
    print("WebSocket: order book subscribe message works")


def test_orderbook_websocket_invalid_message(client: TestClient):
    with client.websocket_connect("/ws/orderbook/TOP20-AUGUST") as ws:
        ws.send_text("not json")
        err = ws.receive_json()
        assert err["type"] == "error"
        assert err["message"] == "Invalid message format"
        ws.close()
    print("WebSocket: order book invalid message handling works")
