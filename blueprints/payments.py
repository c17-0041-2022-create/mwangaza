from flask import Blueprint, render_template, request, jsonify, session
import os
import json
from dotenv import load_dotenv

from models import (
    add_mpesa_request,
    add_mpesa_callback,
    get_mpesa_request_by_merchant_request_id,
    update_mpesa_request_status,
    add_payment,
    get_db
)

load_dotenv()

bp = Blueprint('payments', __name__)


@bp.route('/payments')
def payments_index():
    # Placeholder route
    return render_template('payments.html')


# MPESA STK Push endpoint (development/demo friendly)
@bp.route('/mpesa_pay', methods=['POST'])
def mpesa_pay():
    """Initiate an M-Pesa STK Push using the local daraja helper.

    Expects JSON: { phone: string, amount: number, account_reference?: string, description?: string }
    Returns JSON with Daraja response or error message.
    """
    try:
        data = request.get_json() or {}
        phone = data.get('phone')
        amount = data.get('amount')
        account_ref = data.get('account_reference') or data.get('accountRef') or 'RentPayment'
        description = data.get('description') or data.get('transaction_desc') or 'Rent payment'

        if not phone or not amount:
            return jsonify({"success": False, "error": "phone and amount are required"}), 400

        # Normalize phone number into Daraja friendly format e.g. 2547XXXXXXXX
        def normalize_phone(msisdn: str) -> str:
            # Normalize common phone formats into E.164-like '2547XXXXXXXX' used by Daraja.
            if not msisdn:
                return ''
            s = msisdn.strip()
            # remove spaces, dashes and parentheses
            for ch in [' ', '+', '-', '(', ')']:
                s = s.replace(ch, '')

            # If starts with 0 -> replace leading 0 with 254
            if s.startswith('0'):
                s = '254' + s[1:]

            # If starts with '7' (07XXXXXXXX without leading 0) add 254
            if s.startswith('7'):
                s = '254' + s

            # If starts with country code without + (e.g., 2547...) keep as-is
            # Ensure only digits remain
            if not s.isdigit():
                # strip any non-digits
                s = ''.join([c for c in s if c.isdigit()])

            return s

        phone_norm = normalize_phone(phone)

        # Basic validation: ensure phone is digits and has Kenyan country code (254)
        if not phone_norm or not phone_norm.isdigit():
            return jsonify({"success": False, "error": "Phone number invalid. Please enter a Kenyan phone number like 2547XXXXXXXX."}), 400

        # Accept only numbers with country code (254) and 12 digits total (e.g., 2547XXXXXXXX)
        if len(phone_norm) == 9 and phone_norm.startswith('7'):
            # unlikely since we normalize earlier, but handle defensively
            phone_norm = '254' + phone_norm

        if not (phone_norm.startswith('254') and len(phone_norm) == 12):
            return jsonify({"success": False, "error": "Phone number must include country code (e.g. 2547XXXXXXXX)."}), 400

        # Basic network check: STK Push requires a mobile number. Common Safaricom mobile numbers start with 2547
        if not phone_norm.startswith('2547'):
            # Not guaranteed to be non-Safaricom, but warn users that some networks won't work for STK Push
            return jsonify({
                "success": False,
                "error": "STK Push typically requires a Safaricom mobile number (e.g. 2547XXXXXXXX). If the user has a different network, please choose an alternate payment method or update the number."
            }), 400

        # Configure daraja module from env (safe no-op if not configured)
        try:
            import daraja
            daraja.DARAJA_CONSUMER_KEY = os.environ.get('DARAJA_CONSUMER_KEY')
            daraja.DARAJA_CONSUMER_SECRET = os.environ.get('DARAJA_CONSUMER_SECRET')
            daraja.DARAJA_API_URL = os.environ.get('DARAJA_API_URL')
            daraja.DARAJA_SHORTCODE = os.environ.get('DARAJA_SHORTCODE')
            daraja.DARAJA_PASSKEY = os.environ.get('DARAJA_PASSKEY')
        except Exception as e:
            return jsonify({"success": False, "error": f"Daraja module load failed: {str(e)}"}), 500

        # Support optional payments count (e.g., number of months to pay at once)
        count = int(float(data.get('count', 1))) if data.get('count') is not None else 1
        if count < 1:
            count = 1

        # Compute total amount to charge (Daraja expects integer KES amounts)
        try:
            unit_amount = int(float(amount))
        except Exception:
            return jsonify({"success": False, "error": "Invalid amount"}), 400

        total_amount = unit_amount * count

        # Call Daraja STK Push
        try:
            resp = daraja.initiate_stk_push(phone_norm, total_amount, account_ref, description)

            # Extract IDs (Daraja may return keys at top level)
            merchant_request_id = resp.get('MerchantRequestID') or resp.get('merchantRequestID')
            checkout_request_id = resp.get('CheckoutRequestID') or resp.get('checkoutRequestID')

            # Determine tenant/landlord context if available
            tenant_id = session.get('user_id')
            tenancy_id = None
            landlord_id = None
            # If account_ref was a tenancy id (we passed tenancy.id earlier), try to use it
            try:
                if account_ref and str(account_ref).isdigit():
                    tenancy_id = int(account_ref)
                    conn = get_db()
                    t = conn.execute('SELECT * FROM tenancies WHERE id = ?', (tenancy_id,)).fetchone()
                    conn.close()
                    if t:
                        landlord_id = t['landlord_id']
            except Exception:
                pass

            # Persist outgoing request for later reconciliation
            try:
                # Persist total_amount so reconciliation and callbacks reflect the charged amount
                add_mpesa_request(tenant_id, landlord_id, tenancy_id, phone_norm, float(total_amount), account_ref, merchant_request_id, checkout_request_id, status='initiated', response_json=json.dumps(resp))
            except Exception as e:
                # best-effort: don't fail the MPesa initiation if we cannot persist
                print('Warning: failed to persist mpesa_request:', e)

            return jsonify({"success": True, "data": resp})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route('/mpesa_callback', methods=['POST'])
def mpesa_callback():
    """Endpoint to receive Daraja STK Push callbacks (as configured in DARAJA_CALLBACK_URL).

    This will store the raw callback, update the mpesa_requests row, and create a payment
    record when ResultCode == 0 (success).
    """
    try:
        payload = request.get_json() or {}

        # Daraja pushes under Body.stkCallback normally
        cb = payload.get('Body', {}).get('stkCallback') or payload.get('stkCallback') or {}

        merchant_request_id = cb.get('MerchantRequestID')
        checkout_request_id = cb.get('CheckoutRequestID')
        result_code = cb.get('ResultCode')
        result_desc = cb.get('ResultDesc')

        # Persist raw callback
        try:
            add_mpesa_callback(merchant_request_id, checkout_request_id, int(result_code) if result_code is not None else None, result_desc, json.dumps(payload))
        except Exception as e:
            print('Warning: failed to persist mpesa_callback:', e)

        # Update request status and optionally create a payment record
        if merchant_request_id:
            status = 'confirmed' if int(result_code or 1) == 0 else 'failed'
            try:
                update_mpesa_request_status(merchant_request_id, status, response_json=json.dumps(cb), checkout_request_id=checkout_request_id)
            except Exception as e:
                print('Warning: failed to update mpesa_request status:', e)

            # On success, attempt to find the original request and create a payment
            if int(result_code or 1) == 0:
                try:
                    req = get_mpesa_request_by_merchant_request_id(merchant_request_id)
                    if req:
                        tenant_id = req['tenant_id']
                        landlord_id = req['landlord_id']
                        tenancy_id = req['tenancy_id']
                        amount = req['amount']

                        # If landlord missing but tenancy present, try to resolve landlord
                        if (not landlord_id) and tenancy_id:
                            try:
                                conn = get_db()
                                t = conn.execute('SELECT landlord_id FROM tenancies WHERE id = ?', (tenancy_id,)).fetchone()
                                conn.close()
                                if t:
                                    landlord_id = t['landlord_id']
                            except Exception:
                                pass

                        # Idempotency check: avoid creating a duplicate payment if one already exists
                        try:
                            conn = get_db()
                            existing = conn.execute('SELECT id FROM payments WHERE merchant_request_id = ? LIMIT 1', (merchant_request_id,)).fetchone()
                            conn.close()
                        except Exception:
                            existing = None

                        if existing:
                            # payment already created earlier — skip
                            print(f'Info: payment already exists for MerchantRequestID={merchant_request_id}, skipping creation')
                        else:
                            if tenant_id and amount:
                                try:
                                    # create a payments row and save merchant_request_id for idempotency
                                    add_payment(tenant_id, landlord_id or 0, amount, description=f'M-Pesa STK Push ({merchant_request_id})', status='confirmed', tenacy_id=tenancy_id, merchant_request_id=merchant_request_id)
                                except Exception as e:
                                    print('Warning: failed to create payment from callback:', e)
                except Exception as e:
                    print('Warning: processing callback failed:', e)
            else:
                # Non-zero ResultCode: create a failed payment/activity record so landlord is aware and for audit
                try:
                    req = get_mpesa_request_by_merchant_request_id(merchant_request_id)
                    tenant_id = req['tenant_id'] if req else None
                    landlord_id = req['landlord_id'] if req else None
                    # create a failed payment record for audit (do not mark as confirmed)
                    if tenant_id and req:
                        try:
                            add_payment(tenant_id, landlord_id or 0, req['amount'] or 0, description=f'M-Pesa failed STK Push ({merchant_request_id}) - {result_desc}', status='failed', tenacy_id=req.get('tenancy_id'), merchant_request_id=merchant_request_id)
                        except Exception as e:
                            print('Warning: failed to create failed payment record:', e)
                except Exception:
                    pass

        # Return 200 OK to Daraja
        return jsonify({'success': True}), 200
    except Exception as e:
        # Always respond 200 to avoid retries if we have recorded the callback; but return error info for local debugging
        print('Error in mpesa_callback:', e)
        return jsonify({'success': False, 'error': str(e)}), 200


@bp.route('/debug/mpesa_last')
def debug_mpesa_last():
    """Return the last few mpesa_requests and mpesa_callbacks for debugging.

    Useful when testing callbacks via ngrok to verify the callback was persisted.
    """
    try:
        conn = get_db()
        reqs = conn.execute('SELECT * FROM mpesa_requests ORDER BY created_at DESC LIMIT 10').fetchall()
        cbs = conn.execute('SELECT * FROM mpesa_callbacks ORDER BY created_at DESC LIMIT 10').fetchall()
        conn.close()

        def row_to_dict(r):
            return {k: r[k] for k in r.keys()} if r else None

        return jsonify({
            'mpesa_requests': [row_to_dict(r) for r in reqs],
            'mpesa_callbacks': [row_to_dict(r) for r in cbs]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
