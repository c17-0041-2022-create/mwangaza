import time
import hmac
import hashlib
import json
import os
import requests
from flask import Blueprint, jsonify, request

bp = Blueprint('payments', __name__)

BINANCE_API_KEY = os.environ.get("BINANCE_API_KEY", "")
BINANCE_SECRET_KEY = os.environ.get("BINANCE_SECRET_KEY", "")
BINANCE_MERCHANT_ID = os.environ.get("BINANCE_MERCHANT_ID", "")
BINANCE_BASE_URL = "https://bpay.binanceapi.com"

@bp.route("/create_binance_order", methods=["POST"])
def create_binance_order():
    if not all([BINANCE_API_KEY, BINANCE_SECRET_KEY, BINANCE_MERCHANT_ID]):
        return jsonify({
            "error": "Binance Pay credentials not configured. Please set up your API keys."
        }), 500
    
    try:
        data = request.get_json() or {}
        amount = float(data.get('amount', 10.00))
        description = data.get('description', 'Service Payment')
        
        payload = {
            "merchantId": BINANCE_MERCHANT_ID,
            "merchantTradeNo": f"ORDER_{int(time.time())}",
            "orderAmount": amount,
            "currency": "USDT",
            "goods": {
                "goodsType": "01",
                "goodsCategory": "D000",
                "referenceGoodsId": "SKU-001",
                "goodsName": description
            }
        }

        json_payload = json.dumps(payload)
        timestamp = str(int(time.time() * 1000))
        
        nonce_str = f"{timestamp}{json_payload}"
        sign = hmac.new(
            BINANCE_SECRET_KEY.encode(), 
            nonce_str.encode(), 
            hashlib.sha512
        ).hexdigest().upper()

        headers = {
            "Content-Type": "application/json",
            "BinancePay-Timestamp": timestamp,
            "BinancePay-Nonce": nonce_str,
            "BinancePay-Certificate-SN": BINANCE_API_KEY,
            "BinancePay-Signature": sign
        }

        response = requests.post(
            f"{BINANCE_BASE_URL}/binancepay/openapi/v2/order",
            data=json_payload,
            headers=headers,
            timeout=10
        )
        
        response_data = response.json()
        
        if response_data.get("status") == "SUCCESS":
            data = response_data.get("data", {})
            return jsonify({
                "success": True,
                "qrcodeLink": data.get("qrcodeLink"),
                "checkoutUrl": data.get("checkoutUrl"),
                "prepayId": data.get("prepayId")
            })
        else:
            return jsonify({
                "success": False,
                "error": response_data.get("errorMessage", "Failed to create order")
            }), 400
            
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@bp.route("/check_order_status/<order_id>", methods=["GET"])
def check_order_status(order_id):
    if not all([BINANCE_API_KEY, BINANCE_SECRET_KEY, BINANCE_MERCHANT_ID]):
        return jsonify({
            "error": "Binance Pay credentials not configured"
        }), 500
    
    try:
        payload = {
            "merchantId": BINANCE_MERCHANT_ID,
            "prepayId": order_id
        }
        
        json_payload = json.dumps(payload)
        timestamp = str(int(time.time() * 1000))
        
        nonce_str = f"{timestamp}{json_payload}"
        sign = hmac.new(
            BINANCE_SECRET_KEY.encode(),
            nonce_str.encode(),
            hashlib.sha512
        ).hexdigest().upper()

        headers = {
            "Content-Type": "application/json",
            "BinancePay-Timestamp": timestamp,
            "BinancePay-Nonce": nonce_str,
            "BinancePay-Certificate-SN": BINANCE_API_KEY,
            "BinancePay-Signature": sign
        }

        response = requests.post(
            f"{BINANCE_BASE_URL}/binancepay/openapi/v2/order/query",
            data=json_payload,
            headers=headers,
            timeout=10
        )
        
        response_data = response.json()
        
        if response_data.get("status") == "SUCCESS":
            return jsonify({
                "success": True,
                "data": response_data.get("data", {})
            })
        else:
            return jsonify({
                "success": False,
                "error": response_data.get("errorMessage", "Failed to query order")
            }), 400
            
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
