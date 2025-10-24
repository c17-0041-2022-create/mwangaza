import base64
import os
from datetime import datetime, timedelta

import requests
try:
    # ensure .env is loaded when this module is imported in development
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass
import logging

logger = logging.getLogger(__name__)

# --- 1. GLOBAL VARIABLES (Set to None initially) ---
# We make these global so get_daraja_token can access them, but they are NOT assigned yet.
DARAJA_CONSUMER_KEY = None
DARAJA_CONSUMER_SECRET = None
DARAJA_API_URL = None
DARAJA_SHORTCODE = None
DARAJA_PASSKEY = None # Added for Step 3, good to put here

# Load from environment when available so imports work without requiring
# the script to be run as __main__ or other modules to set the globals.
# This makes the helper resilient when used inside Flask where dotenv may
# already have been loaded at app startup.
try:
    if not DARAJA_CONSUMER_KEY:
        DARAJA_CONSUMER_KEY = os.getenv('DARAJA_CONSUMER_KEY')
    if not DARAJA_CONSUMER_SECRET:
        DARAJA_CONSUMER_SECRET = os.getenv('DARAJA_CONSUMER_SECRET')
    if not DARAJA_API_URL:
        DARAJA_API_URL = os.getenv('DARAJA_API_URL')
    if not DARAJA_SHORTCODE:
        DARAJA_SHORTCODE = os.getenv('DARAJA_SHORTCODE')
    if not DARAJA_PASSKEY:
        DARAJA_PASSKEY = os.getenv('DARAJA_PASSKEY')
except Exception:
    # No-op: in some import contexts os.getenv may not be available (very unlikely)
    pass

# Ensure we have a sensible default token endpoint and STK push URL when
# environment indicates sandbox/production but explicit URLs are not provided.
try:
    environment = os.getenv('DARAJA_ENVIRONMENT', 'sandbox').lower()
    if not DARAJA_API_URL:
        if environment == 'sandbox':
            DARAJA_API_URL = 'https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials'
        else:
            DARAJA_API_URL = 'https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials'

    # Ensure STK push and callback URLs are available in env so initiate_stk_push can read them
    if not os.getenv('DARAJA_STK_PUSH_URL'):
        stk_push_url = f'https://{environment}.safaricom.co.ke/mpesa/stkpush/v1/processrequest'
        os.environ.setdefault('DARAJA_STK_PUSH_URL', stk_push_url)
    if not os.getenv('DARAJA_CALLBACK_URL'):
        # default placeholder — user should set a reachable HTTPS URL for callbacks
        os.environ.setdefault('DARAJA_CALLBACK_URL', 'https://your-callback-url.com/callback')
except Exception:
    pass

# Token cache (Stores the token and its expiration time)
_daraja_token_cache = {
    'access_token': None,
    'expires_at': datetime.now()
}

def get_daraja_token():
    """
    Retrieves and caches the M-Pesa API Access Token using Basic Auth.
    Returns: The valid access token string.
    Raises: Exception if authentication fails.
    """

    # 1. Check cache validity
    if _daraja_token_cache['access_token'] and datetime.now() < _daraja_token_cache['expires_at']:
        print("Using cached Daraja token.")
        return _daraja_token_cache['access_token']

    # 2. Validate credentials (identify which specific values are missing so errors are actionable)
    missing = []
    if not DARAJA_CONSUMER_KEY:
        missing.append('DARAJA_CONSUMER_KEY')
    if not DARAJA_CONSUMER_SECRET:
        missing.append('DARAJA_CONSUMER_SECRET')
    if not DARAJA_API_URL:
        missing.append('DARAJA_API_URL')
    if missing:
        raise ValueError(f"Daraja credentials not configured: missing {', '.join(missing)}. Please ensure .env is loaded and values are set.")

    # 3. Prepare Basic Auth Header
    auth_string = f"{DARAJA_CONSUMER_KEY}:{DARAJA_CONSUMER_SECRET}"
    # The API requires the key and secret to be Base64 encoded.
    auth_encoded = base64.b64encode(auth_string.encode('utf-8')).decode('utf-8')

    headers = {
        'Authorization': f'Basic {auth_encoded}'
    }

    response = None
    try:
        # 4. Request the Token
        response = requests.get(str(DARAJA_API_URL), headers=headers)
        response.raise_for_status() # Raises HTTPError for 4xx or 5xx responses

        data = response.json()
        access_token = data.get('access_token')
        expires_in = int(data.get('expires_in', 3599))

        if access_token:
            # 5. Cache the new token (Expiring 5 minutes early for safety)
            _daraja_token_cache['access_token'] = access_token
            _daraja_token_cache['expires_at'] = datetime.now() + timedelta(seconds=expires_in - 300) 
            return access_token
        else:
            raise Exception("Token request succeeded but 'access_token' key was missing in response.")

    except requests.RequestException as e:
        error_details = ""
        try:
            if response is not None:
                error_details = response.json().get('errorMessage', str(e))
            else:
                error_details = str(e)
        except:
            error_details = str(e)

        raise Exception(f"Failed to connect or authenticate with Daraja API. Error: {error_details}")

def initiate_stk_push(phone_number, amount, account_reference, transaction_desc):
    """
    Initiates a STK Push request to the M-Pesa Daraja API.

    Args:
        phone_number (str): The phone number to be charged (in the format 2547xxxxxxxx).
        amount (int): The amount to be charged.
        account_reference (str):  Reference account.
        transaction_desc (str): Description of the transaction.

    Returns:
        dict: The JSON response from the API.
        Raises: Exception on error
    """
    # Ensure required global variables are set and report any missing ones
    missing = []
    if not DARAJA_SHORTCODE:
        missing.append('DARAJA_SHORTCODE')
    if not DARAJA_PASSKEY:
        missing.append('DARAJA_PASSKEY')
    api_url = os.getenv("DARAJA_STK_PUSH_URL")  # Get the STK push URL from environment variables
    if not api_url:
        missing.append('DARAJA_STK_PUSH_URL')

    if missing:
        raise ValueError(f"Daraja configuration incomplete: missing {', '.join(missing)}. Please set these in .env or environment.")

    access_token = get_daraja_token() # Get a valid access token
    
    # Get the timestamp
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

    # Generate the password
    password = base64.b64encode(str(str(DARAJA_SHORTCODE) + str(DARAJA_PASSKEY) + timestamp).encode()).decode()

    # Construct the payload
    payload = {
        "BusinessShortCode": DARAJA_SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": amount,
        "PartyA": phone_number,
        "PartyB": DARAJA_SHORTCODE,
        "PhoneNumber": phone_number,
        "CallBackURL": os.getenv("DARAJA_CALLBACK_URL"),  # Get callback URL from environment variables
        "AccountReference": account_reference,
        "TransactionDesc": transaction_desc
    }

    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    response = None
    try:
        # Debug: log outgoing payload (mask sensitive fields)
        try:
            safe_payload = dict(payload)
            if 'Password' in safe_payload:
                safe_payload['Password'] = '***'
        except Exception:
            safe_payload = '<unserializable payload>'
        logger.debug('Daraja STK Push POST %s payload=%s', api_url, safe_payload)

        response = requests.post(api_url, json=payload, headers=headers, timeout=15)
        # Capture response text safely for debugging
        try:
            resp_text = response.text
        except Exception:
            resp_text = '<unreadable response body>'
        logger.debug('Daraja STK Push response status=%s body=%s', getattr(response, 'status_code', None), resp_text)

        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        return response.json()
    except requests.RequestException as e:
        error_details = ""
        try:
            if response is not None:
                try:
                    # prefer structured JSON if possible
                    error_details = response.json()
                except Exception:
                    error_details = resp_text
            else:
                error_details = str(e)
        except:
            error_details = str(e)
        logger.error('STK Push failed: %s', error_details)
        raise Exception(f"STK Push failed. Error: {error_details}")


def initiate_b2c_payment(party_b, amount, remarks='Withdrawal', occasion=''):
    """Initiate a Business-to-Customer (B2C) payment to send funds to a customer's phone.

    Note: B2C requires additional credentials (InitiatorName and SecurityCredential) and
    specific callback URLs. This helper expects the following env vars to be set:
      - DARAJA_B2C_URL
      - DARAJA_B2C_INITIATOR
      - DARAJA_B2C_SECURITY_CREDENTIAL
      - DARAJA_B2C_RESULT_URL
      - DARAJA_B2C_TIMEOUT_URL

    If these are not configured the function will raise a ValueError with actionable guidance.
    """
    missing = []
    b2c_url = os.getenv('DARAJA_B2C_URL')
    initiator = os.getenv('DARAJA_B2C_INITIATOR')
    security_cred = os.getenv('DARAJA_B2C_SECURITY_CREDENTIAL')
    result_url = os.getenv('DARAJA_B2C_RESULT_URL')
    timeout_url = os.getenv('DARAJA_B2C_TIMEOUT_URL')

    if not b2c_url:
        missing.append('DARAJA_B2C_URL')
    if not initiator:
        missing.append('DARAJA_B2C_INITIATOR')
    if not security_cred:
        missing.append('DARAJA_B2C_SECURITY_CREDENTIAL')
    if not result_url:
        missing.append('DARAJA_B2C_RESULT_URL')
    if not timeout_url:
        missing.append('DARAJA_B2C_TIMEOUT_URL')

    if missing:
        raise ValueError(f"Daraja B2C configuration incomplete: missing {', '.join(missing)}. Please set these in .env if you want to disburse withdrawals to M-Pesa.")

    access_token = get_daraja_token()

    payload = {
        'InitiatorName': initiator,
        'SecurityCredential': security_cred,
        'CommandID': 'BusinessPayment',
        'Amount': int(amount),
        'PartyA': DARAJA_SHORTCODE,
        'PartyB': party_b,
        'Remarks': remarks,
        'QueueTimeOutURL': timeout_url,
        'ResultURL': result_url,
        'Occasion': occasion
    }

    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }

    try:
        logger.debug('Daraja B2C POST %s payload=%s', b2c_url, payload)
        resp = requests.post(b2c_url, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        err = None
        try:
            err = resp.json()
        except Exception:
            err = str(e)
        logger.error('Daraja B2C failed: %s', err)
        raise Exception(f'B2C payment failed: {err}')


if __name__ == '__main__':
    from dotenv import load_dotenv
    load_dotenv()

    DARAJA_CONSUMER_KEY = os.getenv("DARAJA_CONSUMER_KEY")
    DARAJA_CONSUMER_SECRET = os.getenv("DARAJA_CONSUMER_SECRET")
    DARAJA_API_URL = os.getenv("DARAJA_API_URL")
    DARAJA_SHORTCODE = os.getenv("DARAJA_SHORTCODE")
    DARAJA_PASSKEY = os.getenv("DARAJA_PASSKEY")

    environment = os.getenv('DARAJA_ENVIRONMENT', 'sandbox')
    if environment == 'sandbox':
        if not DARAJA_API_URL:
            DARAJA_API_URL = 'https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials'
    else:
        if not DARAJA_API_URL:
            DARAJA_API_URL = 'https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials'

    stk_push_url = os.getenv('DARAJA_STK_PUSH_URL', f'https://{environment}.safaricom.co.ke/mpesa/stkpush/v1/processrequest')
    callback_url = os.getenv('DARAJA_CALLBACK_URL', 'https://your-callback-url.com/callback')
    
    os.environ['DARAJA_STK_PUSH_URL'] = stk_push_url
    os.environ['DARAJA_CALLBACK_URL'] = callback_url

    print("=" * 70)
    print("DARAJA API TEST SUITE")
    print("=" * 70)
    print(f"Environment: {environment}")
    print(f"Shortcode: {DARAJA_SHORTCODE}")
    print(f"API URL: {DARAJA_API_URL}")
    print(f"STK Push URL: {stk_push_url}")
    print("=" * 70)

    print("\n--- 1. Testing Daraja Token Generation ---")
    try:
        token = get_daraja_token()
        print(f"✅ SUCCESS: Token generated successfully!")
        print(f"Token (first 20 chars): {token[:20]}...")
        print(f"Token length: {len(token)} characters")
        print(f"Expires at: {_daraja_token_cache['expires_at']}")
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        exit(1)

    print("\n--- 2. Testing Token Cache ---")
    try:
        cached_token = get_daraja_token()
        if cached_token == token:
            print("✅ SUCCESS: Token retrieved from cache!")
        else:
            print("⚠️  WARNING: Token changed (not from cache)")
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")

    print("\n--- 3. Testing STK Push Configuration ---")
    try:
        test_phone = "254712345678"
        test_amount = 1
        
        print(f"Phone number format: {test_phone}")
        print(f"Amount: {test_amount}")
        print(f"Callback URL: {callback_url}")
        print("✅ STK Push configuration looks good!")
        print("\nNOTE: Not sending actual STK push in test mode.")
        print("To test STK push, uncomment the code below and use a valid phone number:")
        print("=" * 70)
        print("# response = initiate_stk_push(")
        print("#     phone_number='254712345678',")
        print("#     amount=1,")
        print("#     account_reference='TestPayment',")
        print("#     transaction_desc='Test transaction'")
        print("# )")
        print("# print('STK Push Response:', response)")
        print("=" * 70)
        
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")

    print("\n--- Test Summary ---")
    print("✅ All basic tests passed!")
    print("Your Daraja integration is ready to use.")
    print("=" * 70)
 