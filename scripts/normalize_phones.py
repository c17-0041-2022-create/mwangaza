#!/usr/bin/env python
"""Normalize phone numbers stored in the users table to the '2547XXXXXXXX' format.

Run this once to clean existing demo or migrated data.
"""
from models import get_db


def normalize(msisdn: str) -> str:
    if not msisdn:
        return ''
    s = msisdn.strip()
    for ch in [' ', '+', '-', '(', ')']:
        s = s.replace(ch, '')
    if s.startswith('0'):
        s = '254' + s[1:]
    if s.startswith('7'):
        s = '254' + s
    if not s.isdigit():
        s = ''.join([c for c in s if c.isdigit()])
    return s


def main():
    conn = get_db()
    rows = conn.execute('SELECT id, phone FROM users').fetchall()
    updated = 0
    for r in rows:
        old = r['phone'] or ''
        new = normalize(old)
        if new != old:
            conn.execute('UPDATE users SET phone = ? WHERE id = ?', (new, r['id']))
            updated += 1
            print(f"Updated user id={r['id']}: '{old}' -> '{new}'")
    conn.commit()
    conn.close()
    print(f"Done. {updated} rows updated.")


if __name__ == '__main__':
    main()
