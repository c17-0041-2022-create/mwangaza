import base64
import os
import time
from datetime import datetime, timedelta
import requests
from flask import Blueprint, jsonify, request

bp = Blueprint('kra_tax', __name__)

# --- Environment Variables ---
KRA_TOKEN_ENDPOINT = os.getenv("KRA_TOKEN_ENDPOINT", "")
KRA_ERITS_ENDPOINT = os.getenv("KRA_ERITS_ENDPOINT", "")
KRA_CLIENT_ID = os.getenv("KRA_CLIENT_ID", "")
KRA_CLIENT_SECRET = os.getenv("KRA_CLIENT_SECRET", "")

# Token cache with expiration
_token_cache = {
    'access_token': None,
    'expires_at': datetime.now()
}

def get_kra_token():
    """Get the Authorization Bearer Token from KRA GavaConnect API."""
    
    # Check if we have a valid cached token
    if _token_cache['access_token'] and _token_cache['expires_at']:
        if datetime.now() < _token_cache['expires_at']:
            return _token_cache['access_token']
    
    # Validate credentials
    if not all([KRA_TOKEN_ENDPOINT, KRA_CLIENT_ID, KRA_CLIENT_SECRET]):
        raise ValueError("KRA credentials not configured. Please set KRA_TOKEN_ENDPOINT, KRA_CLIENT_ID, and KRA_CLIENT_SECRET")
    
    # Prepare Basic Auth header
    auth_string = f"{KRA_CLIENT_ID}:{KRA_CLIENT_SECRET}"
    auth_encoded = base64.b64encode(auth_string.encode()).decode()
    
    headers = {
        'Authorization': f'Basic {auth_encoded}'
    }
    params = {'grant_type': 'client_credentials'}
    
    try:
        response = requests.get(KRA_TOKEN_ENDPOINT, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        access_token = data.get('access_token')
        expires_in = data.get('expires_in', 3600)
        
        # Cache the token with expiration
        _token_cache['access_token'] = access_token
        _token_cache['expires_at'] = datetime.now() + timedelta(seconds=expires_in - 60)
        
        return access_token
        
    except requests.RequestException as e:
        raise Exception(f"Error getting KRA token: {str(e)}")

def calculate_rental_tax(gross_rent_kes):
    """Calculate tax on rental income using the 7.5% rate."""
    TAX_RATE = 0.075
    return gross_rent_kes * TAX_RATE

def file_mri_return(landlord_pin, gross_rent_kes, period_month, period_year):
    """
    File the Monthly Rental Income (MRI) return using the eRITS API.
    
    Args:
        landlord_pin: Taxpayer PIN number
        gross_rent_kes: Gross rental amount in KES
        period_month: Month (1-12)
        period_year: Year (e.g., 2025)
    
    Returns:
        dict: API response with status and message
    """
    
    # Ensure we have a valid endpoint
    if not KRA_ERITS_ENDPOINT:
        return {"status": "NOK", "message": "KRA eRITS endpoint not configured"}
    
    # Get authentication token
    try:
        access_token = get_kra_token()
    except Exception as e:
        return {"status": "NOK", "message": f"Authentication failed: {str(e)}"}
    
    # Calculate tax
    tax_amount = calculate_rental_tax(gross_rent_kes)
    
    # Build payload for eRITS/MRI filing
    payload = {
        "TaxpayerPIN": landlord_pin,
        "GrossAmount": gross_rent_kes,
        "TaxAmount": tax_amount,
        "TaxPeriodFrom": f"{period_year}-{period_month:02d}-01T00:00:00",
        "TaxPeriodTo": f"{period_year}-{period_month:02d}-28T23:59:59"
    }
    
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    
    try:
        response = requests.post(KRA_ERITS_ENDPOINT, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()
        
    except requests.RequestException as e:
        error_message = str(e)
        try:
            if 'response' in locals() and hasattr(response, 'json'):
                error_data = response.json()
                error_message = error_data.get('errorMessage', error_message)
        except:
            pass
        return {"status": "NOK", "message": f"API call failed: {error_message}"}

@bp.route("/file_rental_tax", methods=["POST"])
def file_rental_tax():
    """Endpoint to file rental tax return with KRA."""
    
    if not all([KRA_TOKEN_ENDPOINT, KRA_ERITS_ENDPOINT, KRA_CLIENT_ID, KRA_CLIENT_SECRET]):
        return jsonify({
            "success": False,
            "error": "KRA credentials not configured. Please set up your KRA API keys."
        }), 500
    
    try:
        data = request.get_json() or {}
        
        # Validate required fields
        required_fields = ['landlord_pin', 'gross_rent', 'period_month', 'period_year']
        missing = [f for f in required_fields if f not in data]
        
        if missing:
            return jsonify({
                "success": False,
                "error": f"Missing required fields: {', '.join(missing)}"
            }), 400
        
        landlord_pin = data['landlord_pin']
        gross_rent = float(data['gross_rent'])
        period_month = int(data['period_month'])
        period_year = int(data['period_year'])
        
        # Validate inputs
        if not (1 <= period_month <= 12):
            return jsonify({
                "success": False,
                "error": "Invalid month. Must be between 1 and 12."
            }), 400
        
        if gross_rent <= 0:
            return jsonify({
                "success": False,
                "error": "Gross rent must be greater than 0."
            }), 400
        
        # File the return
        result = file_mri_return(landlord_pin, gross_rent, period_month, period_year)
        
        if result.get("status") == "SUCCESS" or result.get("status") == "OK":
            return jsonify({
                "success": True,
                "message": "Rental tax filed successfully",
                "data": result
            })
        else:
            return jsonify({
                "success": False,
                "error": result.get("message", "Failed to file tax return"),
                "data": result
            }), 400
            
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": f"Invalid input: {str(e)}"
        }), 400
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@bp.route("/calculate_tax", methods=["POST"])
def calculate_tax():
    """Calculate tax on rental income without filing."""
    
    try:
        data = request.get_json() or {}
        gross_rent = float(data.get('gross_rent', 0))
        
        if gross_rent <= 0:
            return jsonify({
                "success": False,
                "error": "Gross rent must be greater than 0."
            }), 400
        
        tax_amount = calculate_rental_tax(gross_rent)
        net_rent = gross_rent - tax_amount
        
        return jsonify({
            "success": True,
            "gross_rent": gross_rent,
            "tax_amount": tax_amount,
            "tax_rate": 7.5,
            "net_rent": net_rent,
            "currency": "KES"
        })
        
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": f"Invalid input: {str(e)}"
        }), 400
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500



# =========================================================================
# === CORRECTED TEST BLOCK (Run this file directly to test endpoints) ======
# =========================================================================
if __name__ == '__main__':
    from dotenv import load_dotenv
    load_dotenv()

    print("--- 1. Testing GavaConnect Authentication (get_kra_token) ---")

    # Correct way to reset the token cache before testing
    _token_cache['access_token'] = None
    _token_cache['expires_at'] = datetime.now()

    try:
        token = get_kra_token()
    except Exception as e:
        print(f"❌ CRITICAL FAILURE: Could not retrieve access token. Error: {e}")
        print("\n**Action:** Verify KRA_CLIENT_ID and KRA_CLIENT_SECRET in your .env file and ensure the KRA_TOKEN_ENDPOINT is correct.")
        token = None # Set token to None for the next check

    if token:
        print("✅ SUCCESS: Token retrieved!")
        print(f"Token: {token[:10]}...{token[-10:]}") 

        # --- 2. Testing MRI Filing Endpoint (file_mri_return) ---
        print("\n--- 2. Testing MRI Filing Endpoint (file_mri_return) ---")

        # Define test data (MUST use KRA Sandbox PINs and valid structure)
        TEST_LANDLORD_PIN = "A000000000L"  # Use a valid KRA sandbox PIN
        TEST_GROSS_RENT = 10000.00

        # Calculate month/year as integers for the function
        now = datetime.now()
        TEST_MONTH = now.month 
        TEST_YEAR = now.year

        filing_result = file_mri_return(
            landlord_pin=TEST_LANDLORD_PIN,
            gross_rent_kes=TEST_GROSS_RENT,
            period_month=TEST_MONTH,
            period_year=TEST_YEAR
        )

        # 3. Analyze the filing result
        if filing_result.get('status') == 'OK' or filing_result.get('responseCode') == '70000':
            print("✅ SUCCESS: MRI Filing API call succeeded (received OK status or code 70000).")
            print("KRA Reference/eSlip ID:", filing_result.get('eSlip_ID', 'N/A'))
            print("Full Response:", filing_result)
        else:
            print("❌ FAILURE: MRI Filing API call FAILED or returned an error status.")
            print("Error Details:", filing_result)
            print("\n**Action:** Check the request payload against KRA documentation for errors (PIN, format, dates, etc.).")
    else:
         # This block will now only run if the token retrieval failed in the try/except block
         pass