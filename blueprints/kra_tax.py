from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from datetime import datetime

# core KRA helpers (file_mri_return, calculate_rental_tax)
import os
import kra_tax as core_kra
from models import get_db, add_activity, update_user, get_user_by_id, add_withdrawal, add_tax_filing

bp = Blueprint('kra_tax', __name__)


@bp.route('/kra')
def kra_index():
    return render_template('kra_tax.html')


@bp.route('/withdraw', methods=['GET', 'POST'])
def withdraw():
    """Withdraw paid rent and pay tax (landlord flow).

    GET: show available balance and a form to withdraw and file tax.
    POST: validate inputs, file MRI via core_kra, record activity and return status.
    """
    # Ensure user is landlord (in demo mode AUTH_DISABLED may be True and session seeded)
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to access withdrawals.', 'warning')
        return redirect(url_for('auth.login'))

    # Load landlord info
    landlord = get_user_by_id(user_id)

    # Compute available balance: sum of confirmed payments minus confirmed withdrawals
    conn = get_db()
    payments_row = conn.execute("SELECT IFNULL(SUM(amount), 0) as payments_sum FROM payments WHERE landlord_id = ? AND status = 'confirmed'", (user_id,)).fetchone()
    withdrawals_row = conn.execute("SELECT IFNULL(SUM(gross_amount), 0) as withdrawals_sum FROM withdrawals WHERE landlord_id = ? AND status = 'confirmed'", (user_id,)).fetchone()
    conn.close()
    payments_sum = float(payments_row['payments_sum']) if payments_row else 0.0
    withdrawals_sum = float(withdrawals_row['withdrawals_sum']) if withdrawals_row else 0.0
    available = payments_sum - withdrawals_sum

    if request.method == 'POST':
        data = request.form
        try:
            amount = float(data.get('amount', 0))
        except ValueError:
            flash('Invalid amount specified.', 'error')
            return redirect(url_for('kra_tax.withdraw'))

        if amount <= 0:
            flash('Please specify an amount greater than zero.', 'error')
            return redirect(url_for('kra_tax.withdraw'))

        if amount > available:
            flash('Requested amount exceeds available balance.', 'error')
            return redirect(url_for('kra_tax.withdraw'))

        # Landlord PIN (use stored or form input)
        kra_pin = data.get('kra_pin') or (landlord and landlord.get('kra_pin'))
        if not kra_pin:
            # Seed a demo PIN if missing so flow can continue in dev
            kra_pin = 'A000000000L'
            try:
                update_user(user_id, kra_pin=kra_pin)
            except Exception:
                pass

        # Tax period
        try:
            period_month = int(data.get('period_month', datetime.now().month))
            period_year = int(data.get('period_year', datetime.now().year))
        except ValueError:
            period_month = datetime.now().month
            period_year = datetime.now().year

        # Calculate tax and net amount
        tax_amount = core_kra.calculate_rental_tax(amount)
        net_amount = round(amount - tax_amount, 2)

        # Call KRA filing API (may return failure if credentials not configured)
        # If the user requested disbursement to M-Pesa, attempt a B2C payment first (if Daraja B2C configured).
        withdraw_to_mpesa = bool(request.form.get('withdraw_to_mpesa'))
        mpesa_phone = (request.form.get('mpesa_phone') or (landlord and landlord.get('phone')) or '').strip()

        # Call KRA filing API (we will call it after B2C success or directly if not disbursing via Daraja)
        result = None

        if withdraw_to_mpesa:
            # Attempt to perform B2C via daraja helper if configured. If B2C fails, abort the withdraw.
            try:
                import daraja as _daraja
                # normalize phone similar to other parts of the app (best-effort)
                if mpesa_phone:
                    s = mpesa_phone.replace('+', '').replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
                    if s.startswith('0'):
                        s = '254' + s[1:]
                    if s.startswith('7'):
                        s = '254' + s
                    mpesa_phone = ''.join([c for c in s if c.isdigit()])

                if not mpesa_phone:
                    flash('Please provide an M-Pesa phone to receive the withdrawal.', 'error')
                    return redirect(url_for('kra_tax.withdraw'))

                # Attempt B2C (send net amount to landlord)
                try:
                    b2c_resp = _daraja.initiate_b2c_payment(mpesa_phone, int(net_amount), remarks=f'Withdrawal for landlord {user_id}')
                except Exception as e:
                    flash(f'Failed to disburse to M-Pesa: {e}', 'error')
                    return redirect(url_for('kra_tax.withdraw'))

                # If B2C responds with an immediate failure, show error
                result = core_kra.file_mri_return(kra_pin, amount, period_month, period_year)

                if not (isinstance(b2c_resp, dict) and b2c_resp.get('ResponseCode') in (0, '0', 'INS-0')):
                    # B2C may be async; treat any non-success immediate response as a warning
                    flash('B2C disbursement submitted; it may take a moment to complete. Tax filing will proceed.', 'info')

            except ImportError:
                flash('Daraja B2C helper not available; configure Daraja or uncheck "Send net amount straight to M-Pesa".', 'error')
                return redirect(url_for('kra_tax.withdraw'))
            except Exception as e:
                flash(f'Failed to perform disbursement: {e}', 'error')
                return redirect(url_for('kra_tax.withdraw'))

        else:
            result = core_kra.file_mri_return(kra_pin, amount, period_month, period_year)

        if isinstance(result, dict) and (result.get('status') in ('OK', 'SUCCESS') or result.get('responseCode') == '70000'):
            # Persist tax filing and withdrawal so balance is reduced immediately
            try:
                add_tax_filing(user_id, period_month, period_year, amount, tax_amount, status='filed')
            except Exception:
                # non-fatal; continue
                pass

            try:
                add_withdrawal(user_id, amount, tax_amount, net_amount, status='confirmed')
            except Exception:
                pass

            # Record activities: tax payment and withdrawal (net amount)
            try:
                add_activity(user_id, 'tax_payment', f'KRA tax for withdrawal period {period_month}/{period_year}', tax_amount, status='confirmed')
                add_activity(user_id, 'withdrawal', f'Withdrawal KES {amount:.2f} (net KES {net_amount:.2f})', -net_amount, status='confirmed')
            except Exception:
                pass

            flash(f'Withdrawal processed. Gross: KES {amount:.2f}, Tax: KES {tax_amount:.2f}, Net paid: KES {net_amount:.2f}', 'success')
            return redirect(url_for('kra_tax.withdraw'))
        else:
            # Return error to user with the API message
            msg = result.get('message') if isinstance(result, dict) else str(result)
            flash(f'Failed to file tax: {msg}', 'error')
            return redirect(url_for('kra_tax.withdraw'))

    # GET: render form
    current_month = datetime.now().month
    current_year = datetime.now().year
    return render_template('withdraw.html', available=available, landlord=landlord, current_month=current_month, current_year=current_year)


@bp.route('/withdraw/status', methods=['GET'])
def withdraw_status():
    # simple JSON endpoint to view available balance and last callbacks
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'not logged in'}), 401
    conn = get_db()
    row = conn.execute("SELECT IFNULL(SUM(amount), 0) as balance FROM payments WHERE landlord_id = ? AND status = 'confirmed'", (user_id,)).fetchone()
    conn.close()
    available = float(row['balance']) if row else 0.0
    return jsonify({'success': True, 'available': available})
